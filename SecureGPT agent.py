import json
import requests
import boto3
import os
import csv
import re
import time
from difflib import get_close_matches

# AWS S3 Configuration
INPUT_S3_BUCKET = "projecttaskdatset"
CERT_S3_BUCKET = "secure-gpt-cert-bucket"
CERT_FILE_NAME = "full_secure_gpt_cert.pem"
CERT_PATH = "/tmp/full_secure_gpt_cert.pem"

# Secure GPT API Configuration
SECURE_GPT_URL = "https://tis.accure.ai:9001/query"
SECURE_GPT_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoic2Fuc2FyaSIsImV4cCI6MTc5NjMxMDQ0NH0.FgFpk64W54Uoai0mEv8rZdQtOgaBC7j_pa2Bd7VLJjE"

s3 = boto3.client("s3")

def list_s3_files(bucket_name):
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        files = [obj["Key"] for obj in response.get("Contents", []) if obj["Key"].endswith(".csv")]
        return files
    except Exception as e:
        return {"error": f"Failed to list datasets from S3: {str(e)}"}

def get_dataset_metadata(bucket_name, file_name, num_rows=1):
    try:
        obj = s3.get_object(Bucket=bucket_name, Key=file_name)
        body = obj["Body"].read().decode("utf-8").splitlines()
        csv_reader = csv.reader(body)
        header = [col.strip().lstrip('\ufeff') for col in next(csv_reader)]
        sample_rows = [dict(zip(header, row)) for row, _ in zip(csv_reader, range(num_rows))]
        return {
            "dataset_name": file_name,
            "columns": header,
            "sample_rows": sample_rows
        }
    except Exception as e:
        return {"error": f"Failed to fetch metadata from {file_name}: {str(e)}"}

def extract_json_from_text(response_text):
    try:
        response_text = response_text.encode('utf-8').decode('unicode_escape')
        pattern = r'BEGIN_JSON\s*(\{.*?\})\s*END_JSON'
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
        else:
            return None
    except Exception:
        return None

def classify_user_role(user_text):
    technical_keywords = [
        "engineer", "developer", "analyst", "data", "scientist", "architect", "technician",
        "admin", "security", "infra", "system", "devops", "sre", "operations", "code", "backend",
        "it", "platform", "network"
    ]
    nontechnical_keywords = [
        "ceo", "cfo", "coo", "manager", "director", "lead", "owner", "vp", "president",
        "executive", "business", "finance", "compliance", "marketing", "sales", "customer",
        "strategist", "auditor", "stakeholder", "user", "client", "head", "team"
    ]
    user_text = user_text.lower()
    tech_score = sum(1 for word in technical_keywords if word in user_text)
    nontech_score = sum(1 for word in nontechnical_keywords if word in user_text)
    if tech_score > nontech_score:
        return "technical"
    elif nontech_score > tech_score:
        return "nontechnical"
    else:
        return "nontechnical"

def auto_fix_chart_columns(chart, valid_columns):
    dataset = chart["dataset"]
    actual_cols = valid_columns.get(dataset, [])
    corrected_cols = []
    for col in chart["columns"]:
        match = get_close_matches(col, actual_cols, n=1, cutoff=0.6)
        corrected_cols.append(match[0] if match else col)
    chart["columns"] = corrected_cols
    return chart
def remove_duplicate_charts(charts):
    seen = set()
    unique = []
    for chart in charts:
        # Compare chart type, dataset, and sorted column names — NOT the title
        key = (chart['type'].lower(), chart['dataset'].lower(), tuple(sorted([col.lower() for col in chart['columns']])))
        if key not in seen:
            seen.add(key)
            unique.append(chart)
    return unique

def validate_and_fix_dashboard(json_data, valid_columns, auto_retry=False):
    fixed_charts = []
    for chart in json_data.get("dashboard_data", {}).get("dashboard", []):
        dataset = chart.get("dataset")
        columns = chart.get("columns", [])

        # Remove SQL-style and unsupported expressions
        columns = [col for col in columns if not re.search(r'\b(count|avg|min|max|sum)\s*\(|\*', col.lower())]
        chart["columns"] = columns

        # Remove unsupported chart types
        if chart.get("type", "").lower() in ["word_cloud", "map", "bubble"]:
            continue

        actual_cols = [c.lower() for c in valid_columns.get(dataset, [])]
        is_valid = all(col.lower() in actual_cols for col in columns)

        if not is_valid and auto_retry:
            chart = auto_fix_chart_columns(chart, valid_columns)
            # Check again after auto-fix
            if not all(col.lower() in actual_cols for col in chart["columns"]):
                continue  # skip if still invalid

        elif not is_valid:
            continue  # skip invalid charts if not retrying

        fixed_charts.append(chart)

    return remove_duplicate_charts(fixed_charts)



def create_structured_prompt(user_question, columns_per_dataset, role_type="nontechnical"):
    return f"""
You are a visual analytics expert and an AI JSON assistant.

Below are actual CSV datasets and their column names:
{json.dumps(columns_per_dataset, indent=2)}

---

User Query:
'''{user_question}'''

---

User Type Detected: {role_type.upper()}

Chart Style Instructions:
- If NONTECHNICAL: Focus on simple, high-level charts. Prefer line charts for trends over time. Use bar, pie, and summary tables for comparisons and proportions. Also, Sankey charts to show flow or relationships between two fields (e.g., system → assignee).
- If TECHNICAL: Use more detailed, complex charts like heatmaps, scatter plots, histograms, or stacked bars.

Other Instructions:
1. Only use real columns from the datasets.
2. Do not use SQL expressions like "count(*)", "avg()", "sum()", etc. These are forbidden and will break the dashboard.
3. DO NOT mix columns from different datasets.
4. Output must be 3–6 valid charts in JSON.
5. Wrap final output between BEGIN_JSON and END_JSON.
6. DO NOT use unsupported chart types like "word_cloud", "map", or "bubble".

Before finalizing the JSON:
- Re-read the user query and confirm the chart answers it.
- Double-check that each chart is visually helpful and relevant.
- Avoid redundant charts or overly complex visuals (especially for nontechnical roles).
- Ensure time-based charts (like line, timeline, or histogram) only use timestamp/date fields on the X-axis.
- Choose a good mix of chart types to make the dashboard engaging.

BEGIN_JSON
{{
  "dashboard_data": {{
    "dashboard": [
      {{
        "title": "Example Chart",
        "type": "bar_chart",
        "dataset": "Alert Dataset.csv",
        "columns": ["TicketID", "Timestamp"]
      }}
    ]
  }}
}}
END_JSON
"""
def lambda_handler(event, context):
    try:
        s3.download_file(CERT_S3_BUCKET, CERT_FILE_NAME, CERT_PATH)
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to download SSL certificate: {str(e)}"})}

    if not os.path.exists(CERT_PATH):
        return {"statusCode": 500, "body": json.dumps({"error": "SSL certificate file missing in /tmp/."})}

    try:
        if "query" in event:
            user_question = event["query"]
        elif "user_query" in event:
            user_question = event["user_query"]
        else:
            body = json.loads(event.get("body", "{}"))
            user_question = body.get("query") or body.get("user_query", "")
        user_question = user_question.strip()
        if not user_question:
            return {"statusCode": 400, "body": json.dumps({"error": "User query is missing."})}
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid input format: {str(e)}"})}

    dataset_files = list_s3_files(INPUT_S3_BUCKET)
    if "error" in dataset_files:
        return {"statusCode": 500, "body": json.dumps(dataset_files)}

    dataset_metadata = {}
    for file_name in dataset_files:
        meta = get_dataset_metadata(INPUT_S3_BUCKET, file_name, num_rows=5)
        dataset_metadata[file_name] = meta if "error" not in meta else "Error fetching metadata"

    columns_per_dataset = {
        ds: meta["columns"] for ds, meta in dataset_metadata.items()
        if isinstance(meta, dict) and "columns" in meta
    }

    role_type = classify_user_role(user_question)
    prompt = create_structured_prompt(user_question, columns_per_dataset, role_type)
    secure_gpt_payload = {"org": "1741108458120__CyberVision", "question": prompt.strip()}
    headers = {"Authorization": f"Bearer {SECURE_GPT_API_KEY}", "Content-Type": "application/json"}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                SECURE_GPT_URL,
                json=secure_gpt_payload,
                headers=headers,
                verify=CERT_PATH,
                timeout=30
            )
            raw_text = response.text.strip()
            response_json = extract_json_from_text(raw_text)
            if response_json:
                invalid_charts = validate_and_fix_dashboard(response_json, columns_per_dataset, auto_retry=False)
                if invalid_charts:
                    fixed_charts = validate_and_fix_dashboard(response_json, columns_per_dataset, auto_retry=True)
                    response_json["dashboard_data"]["dashboard"] = fixed_charts
                response_json["dashboard_data"]["dashboard"] = remove_duplicate_charts(response_json["dashboard_data"]["dashboard"])
                return {"statusCode": 200, "body": json.dumps(response_json)}
        except Exception as e:
            if attempt == max_retries - 1:
                return {"statusCode": 500, "body": json.dumps({"error": f"Secure GPT failed after retries: {str(e)}"})}
        time.sleep(1)

    return {"statusCode": 500, "body": json.dumps({"error": "Secure GPT returned invalid JSON after 3 attempts."})}
