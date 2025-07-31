import json
import requests
import os
import boto3
import re

# Secure GPT Config
SECURE_GPT_URL = "https://tis.accure.ai:9001/query"
SECURE_GPT_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoic2Fuc2FyaSIsImV4cCI6MTc5NjMxMDQ0NH0.FgFpk64W54Uoai0mEv8rZdQtOgaBC7j_pa2Bd7VLJjE"
SECURE_GPT_ORG = "1741108458120__CyberVision"

# SSL Cert Config
CERT_S3_BUCKET = "secure-gpt-cert-bucket"
CERT_FILE_NAME = "full_secure_gpt_cert.pem"
CERT_PATH = "/tmp/full_secure_gpt_cert.pem"

s3 = boto3.client("s3")

def classify_user_role(text):
    technical_keywords = ["engineer", "developer", "analyst", "security", "system", "network", "infra", "sre", "it", "data", "backend"]
    nontechnical_keywords = ["ceo", "manager", "director", "lead", "finance", "marketing", "sales", "customer", "executive", "auditor"]
    text = text.lower()
    tech_score = sum(1 for w in technical_keywords if w in text)
    nontech_score = sum(1 for w in nontechnical_keywords if w in text)
    return "technical" if tech_score > nontech_score else "nontechnical"

def clean_html_content(html):
    clean = re.sub(r"<script[\s\S]*?</script>", "", html)
    clean = re.sub(r"<style[\s\S]*?</style>", "", clean)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()

def lambda_handler(event, context):
    try:
        s3.download_file(CERT_S3_BUCKET, CERT_FILE_NAME, CERT_PATH)

        user_query = event.get("user_query") or json.loads(event.get("body", "{}")).get("user_query")
        html_content = event.get("dashboard_html") or json.loads(event.get("body", "{}")).get("dashboard_html")

        if not user_query or not html_content:
            return {"statusCode": 400, "body": json.dumps({"error": "Both 'user_query' and 'dashboard_html' are required."})}

        role_type = classify_user_role(user_query)
        dashboard_text = clean_html_content(html_content)

        prompt = f"""
You are a highly skilled AI cybersecurity analyst. Your task is to generate a professional, executive-level summary of a cybersecurity dashboard for a {role_type.upper()} audience.

DO NOT describe or mention chart types, layout, labels, or styling.
DO NOT fabricate percentages or numbers — only use exact values visible in the data.

Structure your output into:
1. **Executive Summary** – A brief overview of the cyber threat landscape.
2. **Key Findings** – Bullet points summarizing threat trends, spikes, top categories, or severity.
3. **Risk Assessment** – Short analysis of key risks based on anomalies.
4. **Actionable Recommendations** – Strategic advice based on observed data.

Here is the user query:
'''{user_query}'''

Here is the full dashboard content:
'''{dashboard_text}'''

Respond concisely and accurately. Do NOT include unsupported claims or hallucinated statistics.
"""

        headers = {"Authorization": f"Bearer {SECURE_GPT_API_KEY}", "Content-Type": "application/json"}
        payload = {"org": SECURE_GPT_ORG, "question": prompt.strip()}

        response = requests.post(SECURE_GPT_URL, headers=headers, json=payload, timeout=30, verify=CERT_PATH)

        if response.status_code != 200:
            return {"statusCode": 500, "body": json.dumps({"error": f"Secure GPT failed: {response.text}"})}

        result = response.json()
        return {"statusCode": 200, "body": json.dumps({"summary": result.get("generated_text", "No summary returned.")})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
