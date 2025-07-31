
# Agentic AI for Dynamic Dashboards and Real-Time Cybersecurity Insights

## 🧠 Overview

In today’s fast-paced digital landscape, organizations struggle to monitor and interpret cybersecurity events across diverse data sources. This project introduces an AI-powered real-time dashboard that transforms natural language prompts into dynamic cybersecurity insights, making threat detection and monitoring accessible to both technical and non-technical users.

Built with SecureGPT, AWS Lambda, and Plotly, the system automatically processes logs, alerts, and task data to deliver instant visual reports and summaries without manual queries or complex data wrangling.

## 📌 Problem Statement

Organizations often struggle to unify and interpret complex security data from diverse sources such as anomaly logs, network events, and compliance alerts. Static dashboards fall short in delivering real-time, role-specific insights, leading to delayed responses, compliance violations, and increased risk exposure.

This project aims to solve that with:
- A **multi-agent AI system** that interprets user queries.
- **Real-time dashboards** tailored to stakeholder roles.
- **Dynamic visualizations** that eliminate manual effort.

## 🛠 Features

- 🔍 **Natural Language Query Support** (via SecureGPT)
- 📊 **Role-Based Dashboards** (for Technical Teams and Business Leaders)
- 📈 **Interactive Charts** (line, bar, pie, heatmaps, sankey charts, etc.)
- 🧠 **Auto-Summarized Insights** (executive-level summaries, etc.)
- 🔐 **Secure Cloud Architecture** (AWS S3, Lambda, API Gateway)
- ⚙️ **Serverless Deployment** for scalable performance

## 🧰 Tech Stack

| Component              | Technology Used           |
|------------------------|---------------------------|
| Frontend               | React, HTML, CSS          |
| Backend                | AWS Lambda                |
| AI Integration         | SecureGPT (via API)       |
| Visualizations         | Plotly                    |
| Storage                | Amazon S3                 |
| CI/CD & Testing        | Postman, React Testing    |
| Security               | API Gateway, API Keys     |

## 📐 Architecture Diagram

![System Architecture](https://github.com/user-attachments/assets/b4ac64d0-1d8b-4100-9fa8-4e77b5b5b066)

## 📂 Project Structure

```
Daen-690-Project/
├── SecureGPT agent.py             # SecureGPT interface for prompt interpretation
├── Dashboard rendering agent.py   # Chart rendering via Plotly
├── Pipeline agent.py              # Orchestrates flow between agents
├── Summary agent.py               # Executive-level narrative generation
├── Validation agent.mjs           # API key validation
├── User Interface/                # React-based UI
│   ├── public/                    # HTML and manifest
│   └── src/                       # Components, assets, logic
```

## ⚙️ Installation & Setup

This guide walks you through setting up a fully functional AI-powered dashboard pipeline using AWS Lambda, Secure GPT, S3, and API Gateway. It includes five interconnected Lambda functions, SecureGPT integration, and instructions for dependency setup using Klayers or Docker.

---

## ✅ Prerequisites

- AWS account with permissions for:
  - Lambda
  - S3
  - IAM
  - API Gateway
- Docker installed
- Secure GPT API key
- Sample CSV files for testing
- SSL .pem certificate for Secure GPT

---

## 🧩 Lambda Functions Overview

| Function Name         | Purpose                                         |
|-----------------------|--------------------------------------------------|
| securegpt_agent       | Parses user queries into dashboard configs       |
| validation_agent      | Validates the API Key                            |
| dashboard_rendering   | Converts JSON config to Plotly dashboard HTML    |
| summary_agent         | Creates executive-friendly narrative summaries   |
| pipeline_agent        | Orchestrates the full end-to-end pipeline        |

---

## 🛠 Setup Instructions

---

### 🔹 Step 1: Create Required S3 Buckets

| S3 Bucket Name                   | Purpose                                |
|----------------------------------|----------------------------------------|
| certificate-bucket               | Store the .pem certificate of SecureGPT|
| daen690-input-files              | Store all input CSVs                   |
| daen690-output-data              | Store generated dashboards             |
| dataset-schema                   | Stores the metadata of all datasets    |

Create four folders in daen690-input-files bucket as below and upload your input files into appropriate folders, such as:

- `network_anomaly_logs/network_anomalies.csv`
- `stored_alerts/alert_dataset.csv`
- `task_database/task_database.csv`
- `anomaly_logs/anomaly_logs.csv`

---

### 🔹 Step 2: Package and Upload Lambda Functions

Repeat the following process for each function folder:
`securegpt_agent`, `validation_agent`, `dashboard_rendering`, `summary_agent`, `pipeline_agent`

#### 🅰 Option A: Use Klayers (Preferred)

1. Visit [Klayers GitHub](https://github.com/keithrozario/Klayers)
2. Find the *latest ARN* for your AWS region and the needed library (e.g., pandas, plotly)
3. In AWS Lambda → *Layers → Add Layer*
   - Choose *Provide a layer version ARN*
   - Paste the ARN
   - Click *Add*

✅ This is faster and cleaner for standard packages.

---

#### 🅱 Option B: Use Docker (Fallback)

Use this when:
- A required package is *not available* in Klayers
- The *ARN is missing/outdated*

```bash
cd securegpt_agent
docker run --rm -v $(pwd):/app -w /app python:3.9 \
  pip install -r requirements.txt -t .
zip -r securegpt_agent.zip .
```

Then in AWS Lambda:

- Create function → Runtime: Python 3.9 or 3.11
- Upload the `.zip` file

---
### 🔹 Step 3: Configure Lambda Function Settings

After uploading your Lambda function zip, Under *Configuration → General settings*

- Set **Memory** to **1024 MB**
- Set **Timeout** to **15 minutes** 

---

### 🔹 Step 4: Upload SSL Certificate

- The Secure GPT endpoint requires SSL, So upload your `.pem` file to `certificate-bucket`

---
### 🔹 Step 5: Set Up API Gateway for the Pipeline

To expose `pipeline_agent` as an REST API:

1. Go to API Gateway → Create API
2. Choose REST API 
3. Add a ANY route linked to your `pipeline_agent` Lambda
4. Enable CORS
5. Add API key protection

---

### 🔹 Step 6: Deploy the API

- In the left sidebar, click **Actions → Deploy API**
- Deployment Stage: `prod` (or name it something like `v1`)
- Click **Deploy**

You’ll get a public URL like: `https://your-api-id.execute-api.region.amazonaws.com/prod/dashboard`

---

### 🔹 Step 7: Secure with an API Key

1. Go to **Usage Plans**
2. Create a **new usage plan**
3. Add a new **API key** (e.g., `dashboard-ui-key`)
4. Link the key to your deployed **POST /dashboard** method
5. Update your Lambda code or frontend to send the API key in request headers:
```http
x-api-key: your-api-key-value
```

---

### 🔹 Step 8: Add Environment Variables for `validation_agent`

To securely authenticate API calls from the `validation_agent`, store the required keys as environment variables in the Lambda configuration.

✅ **Example: Setting Environment Variables for `validation_agent`**

1. Open the **AWS Lambda Console**
2. Navigate to your **`validation_agent`** function
3. Click **Configuration → Environment variables → Edit**
4. Add the following key-value pair:

| Key              | Value                 |
|------------------|-----------------------|
| API_KEY          | your-secure-api-key   |

---

### Backend (AWS Lambda)
1. Create required Lambda functions (`SecureGPT`, `DashboardRenderer`, `SummaryAgent`, etc.)
2. Configure S3 buckets for input and output datasets.
3. Setup proper API-Gateway

### Frontend (React App)
```bash
cd User\ Interface
npm install
npm start
```
- Open `http://localhost:3000` to interact with the app.

## 📊 How to Use

1. Open the dashboard interface.
2. **Enter your API Key** to gain access.
   - The system validates the key via AWS API Gateway and Lambda.
   - If valid, the interface unlocks prompt entry.
3. Enter a **natural language prompt**, e.g., “Show anomaly trends for the last 30 days.”
4. The system:
   - Sends query to SecureGPT
   - Selects datasets
   - Renders charts
   - Generates narrative summary
5. View and download the dashboard.

## 📈 Example Use Case

- **Prompt**: "I’m a Network Engineer, Show me weekly threat counts, their severity levels, and whether the related alerts were SLA compliant.​"
- **Output**:
  - Line chart of threat frequency
  - Risk heatmap
  - Compliance status table
  - Executive Summary

## 🧪 Testing & Performance

- 📉 Load tested with **up to 4 million rows**
- ⏱ Avg. dashboard generation time: **<10 seconds**
- ✅ 92% accuracy in chart relevancy
- 📊 Precision: 92.72%, Recall: 84.53%, F1: 88.40%

## 👨‍💻 Team

- [Ravi Datta Rachuri](mailto:rrachuri@gmu.edu)  
- [Shuchi Nirav Shah](mailto:sshah59@gmu.edu)  
- [Akash Bejugam](mailto:abejuga2@gmu.edu)  
- [Datha Vaishnavi Kondur](mailto:dkondur@gmu.edu)  
- [Yashaswi Gurram](mailto:ygurram@gmu.edu)  
- [Vardhan Tharlapally](mailto:vtharlap@gmu.edu)
