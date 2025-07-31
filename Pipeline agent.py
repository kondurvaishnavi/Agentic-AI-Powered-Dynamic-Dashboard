import boto3
import json
import time
from urllib.parse import urlparse

lambda_client = boto3.client("lambda")
s3 = boto3.client("s3")

SECURE_GPT_FUNCTION = "latest_code"
DASHBOARD_GENERATOR_FUNCTION = "layerstesting"

def lambda_handler(event, context):
    print("📥 Incoming event:", event)

    # ✅ Step 1: Parse input (user_query or query)
    try:
        user_query = ""
        if "query" in event:
            user_query = event["query"]
        elif "user_query" in event:
            user_query = event["user_query"]
        else:
            body = json.loads(event.get("body", "{}"))
            user_query = body.get("query") or body.get("user_query", "")

        user_query = user_query.strip()
        if not user_query:
            return {
                "statusCode": 400,
                "body": json.dumps({ "error": "Missing user_query or query" })
            }

    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({ "error": f"Invalid input format: {str(e)}" })
        }

    # 🔄 Step 2: Call Secure GPT up to 3 times if dashboard_data is missing
    dashboard_data = None
    last_response = None
    max_retries = 3

    for attempt in range(max_retries):
        try:
            print(f"🔁 Secure GPT Try #{attempt + 1}")
            response1 = lambda_client.invoke(
                FunctionName=SECURE_GPT_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps({ "query": user_query })
            )

            raw_result = json.load(response1["Payload"])
            print("🔍 Raw result from Secure GPT:", raw_result)

            if "body" in raw_result:
                body_json = json.loads(raw_result["body"]) if isinstance(raw_result["body"], str) else raw_result["body"]
            else:
                body_json = raw_result

            last_response = body_json
            dashboard_data = body_json.get("dashboard_data")

            if dashboard_data:
                break  # ✅ Stop retry loop if valid

        except Exception as e:
            print(f"❌ Error from Secure GPT: {str(e)}")

        time.sleep(1)

    if not dashboard_data:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Secure GPT did not return dashboard_data after retries.",
                "last_response": last_response
            })
        }

    # ✅ Step 3: Call Dashboard Generator Lambda
    try:
        response2 = lambda_client.invoke(
            FunctionName=DASHBOARD_GENERATOR_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps({
                "user_query": user_query,
                "dashboard_data": dashboard_data
            })
        )

        result2 = json.load(response2["Payload"])
        print("✅ Final Dashboard Response:", result2)

        # 🔄 Extract dashboard_url from returned payload
        body_data = result2.get("body")
        if isinstance(body_data, str):
            body_data = json.loads(body_data)

        dashboard_url = body_data.get("dashboard_url")
        if not dashboard_url:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Dashboard URL not returned."})
            }

        parsed_url = urlparse(dashboard_url)
        bucket_name = parsed_url.netloc.split('.')[0]
        key = parsed_url.path.lstrip('/')

        s3_object = s3.get_object(Bucket=bucket_name, Key=key)
        html_content = s3_object['Body'].read().decode('utf-8')

        return {
            "statusCode": 200,
            "body": json.dumps({
                "dashboard_html": html_content
                # To return both HTML and URL, you could also add:
                # "dashboard_url": dashboard_url
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({ "error": f"Dashboard Lambda failed: {str(e)}" })
        }