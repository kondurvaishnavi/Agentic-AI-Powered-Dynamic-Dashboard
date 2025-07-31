import json
import boto3
import os
import time
import io
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from dateutil.parser import parse as dateparse
from difflib import get_close_matches
import logging

# AWS S3 Setup
s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
OUTPUT_BUCKET_NAME = "samplebucket45poit"
INPUT_S3_BUCKET = "daen690-output-bucket"
SUMMARY_LAMBDA_NAME = "summarytesting"
TEMP_DIR = "/tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

folder_map = {
    "anomaly_logs": "anomaly_logs/",
    "network_anomaly_logs": "network_anomaly_logs/",
    "stored_alerts": "stored_alerts/",
    "task_database": "task_database/"
}

color_palette = [
    "#FF5733", "#F39C12", "#2ECC71", "#3498DB", "#9B59B6",
    "#1ABC9C", "#E67E22", "#BDC3C7", "#F1C40F", "#C0392B",
    "#8E44AD", "#2980B9", "#27AE60", "#E74C3C", "#D35400"
]
import re

def classify_text_category(text):
    text = str(text).lower()

    # First check detailed patterns (regex-based, specific for SLA and others)
    pattern_map = {
        r"open and resolution time has not started": "Open - Not Started",
        r"not compliant.*still open": "Non-Compliant - Open",
        r"opened within.*estimated resolution": "Compliant - On Time",
        r"not compliant.*status of open": "Non-Compliant - Open Status",
        r"not been resolved.*estimated": "Non-Compliant - Overdue",
        r"resolved within.*2 hours": "Compliant - Resolved"
    }
    for pattern, label in pattern_map.items():
        if re.search(pattern, text):
            return label

    # Then fallback to simple keyword checks
    keyword_map = {
        "login": "Brute Force",
        "failed": "Brute Force",
        "ddos": "DDoS",
        "scan": "Port Scan",
        "outbound": "Data Exfiltration",
        "sla": "SLA",
        "compliant": "Compliant",
        "non-compliant": "Non-Compliant",
        "malware": "Malware"
    }
    for keyword, label in keyword_map.items():
        if keyword in text:
            return label

    return "Other"
def remove_inner_titles(fig):
    fig.update_layout(title_text=None)
    if hasattr(fig, "data"):
        # Only show legend if more than one series has a unique name
        legend_names = [trace.name for trace in fig.data if hasattr(trace, "name") and trace.name]
        fig.update_layout(showlegend=(len(set(legend_names)) > 1))
def parse_date(s: str):
    if not s:
        return None
    try:
        return dateparse(s, fuzzy=True)
    except:
        return None

def parse_time_range(user_query: str):
    range_pattern = r"from\s+(.+?)\s+to\s+(.+?)($|\s)"
    match = re.search(range_pattern, user_query, re.IGNORECASE)
    if match:
        start_date = parse_date(match.group(1).strip())
        end_date = parse_date(match.group(2).strip())
        if start_date and end_date and start_date < end_date:
            return (start_date, end_date)

    single_pattern = r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]?\d{0,4}?\b"
    match = re.search(single_pattern, user_query, re.IGNORECASE)
    if match:
        dt = parse_date(match.group(0))
        if dt:
            start_date = datetime(dt.year, dt.month, 1)
            end_date = datetime(dt.year + 1, 1, 1) if dt.month == 12 else datetime(dt.year, dt.month + 1, 1)
            return (start_date, end_date)

    return None

def list_s3_files(bucket_name, prefix=""):
    try:
        resp = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", []) if obj["Key"].endswith(".csv")]
    except Exception as e:
        return {"error": str(e)}

def get_latest_file(bucket, prefix):
    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        files = response.get("Contents", [])
        csv_files = [f for f in files if f["Key"].endswith(".csv")]
        if not csv_files:
            logger.warning(f"⚠️ No CSV files found in prefix '{prefix}'")
            return None
        latest_file = max(csv_files, key=lambda x: x["LastModified"])
        logger.info(f"📄 Latest file for prefix '{prefix}': {latest_file['Key']}")
        return latest_file["Key"]
    except Exception as e:
        logger.error(f"🚨 Error fetching latest file for prefix '{prefix}': {e}")
        return None

def apply_filters(df, filters):
    for key, value in filters.items():
        key = key.lower()
        if key in df.columns:
            df = df[df[key].astype(str).str.contains(str(value), case=False, na=False)]
    return df

def match_columns(df, expected_cols):
    actual = df.columns.tolist()
    actual_lower_map = {col.lower(): col for col in actual}  # lowercase → actual

    matched = []
    for col in expected_cols:
        col_lower = col.strip().lower()

        # 1. Try fuzzy match
        match = get_close_matches(col_lower, list(actual_lower_map.keys()), n=1, cutoff=0.6)
        if match:
            matched.append(actual_lower_map[match[0]])
        # 2. Try exact match as fallback
        elif col_lower in actual_lower_map:
            matched.append(actual_lower_map[col_lower])
        else:
            matched.append(None)

    logger.info(f"🔍 Requested: {expected_cols}, Actual: {actual}, Matched: {matched}")
    return matched if all(matched) else None

def load_dataset_from_s3(dataset_name, user_query):
    try:
        dataset_key = dataset_name.strip().lower().replace(".csv", "")
        prefix = folder_map.get(dataset_key)
        if not prefix:
            logger.warning(f"⚠️ Dataset '{dataset_name}' not recognized.")
            return None

        files = list_s3_files(INPUT_S3_BUCKET, prefix)
        if isinstance(files, dict):
            logger.error(files["error"])
            return None

        merge_all_by_default = True  # Smart toggle
        is_timeseries_like = len(files) > 1
        time_range = parse_time_range(user_query)

        if time_range:
            selected_files = []
            for f in files:
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", f)
                if date_match:
                    file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                    if time_range[0] <= file_date <= time_range[1]:
                        selected_files.append(f)
            logger.info(f"📂 Merging {len(selected_files)} files for dataset '{dataset_name}' between {time_range[0].date()} and {time_range[1].date()}")
            for file in selected_files:
                logger.info(f"📁 Included file: {file}")

        elif merge_all_by_default and is_timeseries_like:
            # ⏱️ No date mentioned → fallback to previous quarter
            now = datetime.utcnow()
            current_quarter = (now.month - 1) // 3 + 1
            if current_quarter == 1:
                quarter_start = datetime(now.year - 1, 10, 1)
                quarter_end = datetime(now.year, 1, 1)
            else:
                quarter_start_month = 3 * (current_quarter - 2) + 1
                quarter_start = datetime(now.year, quarter_start_month, 1)
                quarter_end = datetime(now.year, quarter_start_month + 3, 1)

            selected_files = []
            for f in files:
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", f)
                if date_match:
                    file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                    if quarter_start <= file_date < quarter_end:
                        selected_files.append(f)

            if not selected_files:
                # 🔁 If no files found in previous quarter, fallback to current + previous month
                from dateutil.relativedelta import relativedelta
                first_day_of_current_month = datetime(now.year, now.month, 1)
                first_day_of_prev_month = first_day_of_current_month - relativedelta(months=1)

                fallback_start = first_day_of_prev_month
                fallback_end = now

                for f in files:
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", f)
                    if date_match:
                        file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                        if fallback_start <= file_date <= fallback_end:
                            selected_files.append(f)

                logger.info(f"🔄 No data in previous quarter → merging {len(selected_files)} files from current and previous month ({fallback_start.date()} to {fallback_end.date()})")
            else:
                logger.info(f"📦 No date in query → merging {len(selected_files)} files from previous quarter ({quarter_start.date()} to {quarter_end.date()})")

        else:
            latest_key = get_latest_file(INPUT_S3_BUCKET, prefix)
            if not latest_key:
                return None
            logger.info(f"📁 Using latest file for '{dataset_name}': {latest_key}")
            obj = s3.get_object(Bucket=INPUT_S3_BUCKET, Key=latest_key)
            df = pd.read_csv(io.BytesIO(obj["Body"].read()))
            if df.empty:
                logger.warning(f"⚠️ DataFrame is empty after loading latest file for '{dataset_name}'")
                return None
            df.columns = df.columns.astype(str).str.strip().str.lower()
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df[df["timestamp"].notnull()]
                df["month"] = df["timestamp"].dt.strftime("%Y-%m")
            if "count" not in df.columns:
                df["count"] = 1
            return df

        dfs = [pd.read_csv(io.BytesIO(s3.get_object(Bucket=INPUT_S3_BUCKET, Key=key)["Body"].read())) for key in selected_files]
        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

        if df.empty:
            logger.warning(f"⚠️ DataFrame is empty after merging selected files for '{dataset_name}'")
            return None

        df.columns = df.columns.astype(str).str.strip().str.lower()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df[df["timestamp"].notnull()]
            df["month"] = df["timestamp"].dt.strftime("%Y-%m")

        if "count" not in df.columns:
            df["count"] = 1

        return df

    except Exception as e:
        logger.error(f"🚨 Load error: {e}")
        return None


    except Exception as e:
        logger.error(f"🚨 Load error: {e}")
        return None

def render_sankey_chart(df, matched_cols, title="Sankey Diagram"):
    import random

    if len(matched_cols) < 2:
        raise ValueError("Sankey chart requires at least two columns (source and target).")
    
    source_col = matched_cols[0]
    target_col = matched_cols[1]
    value_col = matched_cols[2] if len(matched_cols) > 2 else None
    for col in [source_col, target_col]:
        if pd.api.types.is_datetime64_any_dtype(df[col]) or "timestamp" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df[col] = df[col].dt.strftime('%Y-%m')
    # Aggregate flows
    def truncate_label(label, max_length=30):
        return label if len(label) <= max_length else label[:max_length] + "..."
    if value_col and value_col in df.columns:
        grouped = df.groupby([source_col, target_col])[value_col].sum().reset_index()
        grouped.rename(columns={value_col: "Value"}, inplace=True)
    else:
        grouped = df.groupby([source_col, target_col]).size().reset_index(name="Value")
    top_n = 25
    grouped = grouped.sort_values(by="Value", ascending=False).head(top_n)

    # 🧼 Truncate long labels
    grouped[source_col] = grouped[source_col].astype(str).apply(truncate_label)
    grouped[target_col] = grouped[target_col].astype(str).apply(truncate_label)


    # Unique labels
    source_labels = list(grouped[source_col].unique())
    target_labels = list(grouped[target_col].unique())
    all_labels = list(dict.fromkeys(source_labels + target_labels))

    label_map = {label: idx for idx, label in enumerate(all_labels)}
    source_indices = grouped[source_col].map(label_map)
    target_indices = grouped[target_col].map(label_map)

    # Color mapping for each source node
    color_palette = px.colors.qualitative.Plotly  # You can also use your custom palette
    source_color_map = {label: color_palette[i % len(color_palette)] for i, label in enumerate(source_labels)}
    link_colors = grouped[source_col].map(source_color_map)

    # Sankey figure
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=20,
            thickness=35,
            line=dict(color="rgba(0,0,0,0.2)", width=0.3),
            label=all_labels
        ),
        link=dict(
            source=source_indices,
            target=target_indices,
            value=grouped["Value"],
            color=link_colors
        )
    )])

    fig.update_layout(title_text=title, font_size=10, margin=dict(l=20, r=20, t=40, b=20))
    return fig

def invoke_summary_lambda(user_query, html_content):
    payload = {
        "user_query": user_query,
        "dashboard_html": html_content
    }
    response = lambda_client.invoke(
        FunctionName=SUMMARY_LAMBDA_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload)
    )
    result = json.load(response["Payload"])
    body = json.loads(result.get("body", "{}"))
    return body.get("summary", "No summary available.")

def format_summary_text(markdown_text):
    # Fix encoding issues
    markdown_text = (
        markdown_text.replace("â€¢", "•")
        .replace("â€™", "'")
        .replace("â€“", "–")
        .replace("â€œ", '"')
        .replace("â€", '"')
    )

    header_emojis = {
        "Executive Summary": "📝",
        "Key Findings": "📊",
        "Risk Assessment": "⚠️",
        "Actionable Recommendations": "✅"}

    for heading, emoji in header_emojis.items():
        markdown_text = re.sub(
            rf"(?<!\w)(\*?\s*{heading}\*?:?)",
            rf"<strong>{emoji} {heading}</strong>",
            markdown_text,
            flags=re.IGNORECASE)

    # Convert **bold** and *italic*
    markdown_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", markdown_text)
    markdown_text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", markdown_text)

    lines = markdown_text.splitlines()
    formatted = []
    bullets = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue  # skip blank lines

        if re.match(r"^\d+\.\s+", stripped):
            if bullets:
                formatted.append("<ul>" + "".join(bullets) + "</ul>")
                bullets.clear()
            formatted.append(f"<strong>{stripped}</strong>")

        elif stripped.startswith(("•", "+", "* ")):
            bullets.append(f"<li>{stripped[1:].strip()}</li>")

        else:
            if bullets:
                formatted.append("<ul>" + "".join(bullets) + "</ul>")
                bullets.clear()
            formatted.append(stripped)

    if bullets:
        formatted.append("<ul>" + "".join(bullets) + "</ul>")

    # Final HTML
    html_text = "<br>".join(formatted)
    html_text = re.sub(r"(<br>\s*){2,}", "<br>", html_text)
    html_text = re.sub(r"(<br><ul>)", "<ul>", html_text)
    html_text = re.sub(r"(</ul><br>)", "</ul>", html_text)

    return html_text

def generate_dashboard_html(dashboard_data, user_query):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.9.2/html2pdf.bundle.min.js"></script>
        <style>
            body { font-family: Arial; background: #E9FFDB; color: #2F4F4F; margin: 0; padding: 0; text-align: center; }
            h1 { color: #2F4F4F; margin-top: 20px; }
            .dashboard-container {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                padding: 20px;
                max-width: 1600px;
                margin: 0 auto;
            }
            .chart-container {
                background: #F8FFF1;
                padding: 15px;
                border-radius: 10px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }
            .chart-container:hover { transform: scale(1.03); }
            footer { background: #D0E8C2; color:#2F4F4F; padding: 10px; margin-top: 20px; }
            #toggle-menu {
                position: absolute;
                top: 20px;
                right: 30px;
                z-index: 10;
            }
            #summary-view {
                display: none;
                max-width: 1000px;
                margin: auto;
                padding: 30px;
                font-size: 16px;
                background-color:#F0FDE4;
                border-radius: 10px;
                text-align: left; 
                color: #2F4F4F;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            ul { padding-left: 20px; margin: 0; }
            li { margin: 4px 0; }
        </style>
        <div id="toggle-menu">
          <select onchange="toggleView(this.value)">
            <option value="dashboard">Dashboard</option>
            <option value="summary">Summary</option>
          </select>
          <button id="download-pdf" onclick="downloadPDF()">Download PDF</button>
          <button id="expand-button"> </button>
        </div>
        <script>
          function toggleView(view) {
            const dash = document.querySelector('.dashboard-container');
            const summary = document.getElementById('summary-view');
            if (view === 'summary') {
              dash.style.display = 'none';
              summary.style.display = 'block';
            } else {
              dash.style.display = 'grid';
              summary.style.display = 'none';
            }
          }
          function downloadPDF() {
            let element;
            const dash = document.querySelector('.dashboard-container');
            const summary = document.getElementById('summary-view');
            if (dash.style.display !== 'none') {
              element = dash;
            } else if (summary.style.display !== 'none') {
              element = summary;
            } else {
              element = document.body;
            }
            var opt = {
              margin: 0.5,
              filename: 'dashboard.pdf',
              image: { type: 'jpeg', quality: 0.98 },
              html2canvas: { scale: 2 },
              jsPDF: { unit: 'in', format: 'letter', orientation: 'landscape' }
            };
            html2pdf().set(opt).from(element).save();
          }
        </script>
    </head>
    <body>
        <h1>AI-Generated Dashboard</h1>
        <div class='dashboard-container'>
    """

    time_range = parse_time_range(user_query)
    filters = dashboard_data.get("filters", {})

    for chart in dashboard_data.get("dashboard", []):
        try:
            title = chart.get("title", "Untitled")
            chart_type = chart.get("type", "")
            normalized_type = chart_type.replace("_", "").replace(" ", "").lower()
            logger.info(f"\U0001f9ea Processing chart: {chart}")
            aliases = {
                "heatmap": "heat_map",
                "stackedbar": "stacked_bar_chart",
                "timeline_chart": "timeline",
                "sankeychart" : "sankey",
                "bubblechart": "bubble_chart"
            }
            chart_type = aliases.get(normalized_type, chart_type)

            dataset_name = chart.get("dataset", "")
            columns = chart.get("columns", [])
            columns = [col for col in chart.get("columns", []) if col.lower() != "count"]

            df = load_dataset_from_s3(dataset_name, user_query)
            logger.info(f"\U0001f4e5 Loaded dataset: {dataset_name}, shape: {df.shape if df is not None else 'None'}")
            if df is None:
                html_content += f"<div class='chart-container'><h3>❌ Dataset '{dataset_name}' not found</h3></div>"
                continue

            if time_range and "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df["timestamp"] = df["timestamp"].dt.tz_localize(None)  # 👈 make timezone-naive
                df = df[(df["timestamp"] >= time_range[0]) & (df["timestamp"] <= time_range[1])]
            df = apply_filters(df, filters)

            matched_cols = match_columns(df, columns)
            logger.info(f"\U0001f50d Requested columns: {columns}, Matched columns: {matched_cols}")
            if not matched_cols:
                html_content += f"<div class='chart-container'><h3>⚠️ Columns {columns} not found</h3></div>"
                continue
            logger.info(f"\U0001f4ca Chart type detected: {chart_type}")
            fig = None

            if chart_type == "line_chart":
                timestamp_col = next(
                    (col for col in matched_cols if any(t in col.lower() for t in ['timestamp', 'time', 'created', 'date'])),
                        None
                )
                category_col = next((col for col in matched_cols if col != timestamp_col), None)
                def is_description_column(col_name, df):
                    return (
                        "description" in col_name.lower()
                        or "message" in col_name.lower()
                        or "text" in col_name.lower()
                        or df[col_name].astype(str).str.len().mean() > 40
                    )

                if category_col and is_description_column(category_col, df):
                    logger.info(f"⚠️ '{category_col}' is descriptive. Applying NLP classification.")
                    df[category_col] = df[category_col].apply(classify_text_category)
            

                if not timestamp_col:
                    raise ValueError("No timestamp-like column found for line chart.")
                    chart_type = "bar_chart"
                else:
                    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
                    df = df[df[timestamp_col].notna()]

                    # Determine frequency
                    time_span = df[timestamp_col].max() - df[timestamp_col].min()
                    if time_span.days >= 60:
                        freq = "W"
                    elif time_span.days >= 7:
                        freq = "D"
                    else:
                        freq = "H"

                    df.set_index(timestamp_col, inplace=True)

                    if category_col:
                        top_categories = df[category_col].value_counts().nlargest(6).index
                        df = df[df[category_col].isin(top_categories)]
                        df_grouped = df.groupby([pd.Grouper(freq=freq), category_col]).size().reset_index(name="count")
                        df_grouped.rename(columns={df_grouped.columns[0]: timestamp_col}, inplace=True)
                        show_legend = df_grouped[category_col].nunique() > 1
                        fig = px.line(df_grouped, x=timestamp_col, y="count", color=category_col,
                                      title=title, markers=True, color_discrete_sequence=color_palette)
                    else:
                        df_grouped = df.resample(freq).size().reset_index(name="count")
                        show_legend = False
                        fig = px.line(df_grouped, x=timestamp_col, y="count", title=title, markers=True,
                                      color_discrete_sequence=color_palette)

                    fig.update_layout(
                        xaxis_title="Time",
                        yaxis_title="Count",
                        xaxis_tickformat="%b %d" if freq != "H" else "%H:%M\n%b %d",
                        hovermode="x unified",
                        xaxis_tickangle=-30,
                        showlegend=show_legend
                    )

            elif chart_type == "bar_chart":
                top_n = 10
                legend_limit = 5

                if len(matched_cols) >= 2:
                    col1, col2 = matched_cols[0], matched_cols[1]
                    if "timestamp" in col1.lower() or pd.api.types.is_datetime64_any_dtype(df[col1]):
                        time_col, category_col = col1, col2
                    elif "timestamp" in col2.lower() or pd.api.types.is_datetime64_any_dtype(df[col2]):
                        time_col, category_col = col2, col1
                    else:
                        # No timestamp — fallback to default
                        time_col, category_col = col1, col2
                        time_col = None
                    color_col = category_col
                    df[category_col] = df[category_col].astype(str).str.strip().str.title()
                    df[color_col] = df[color_col].astype(str).str.strip().str.title()

                    if time_col:
                        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
                        df = df[df[time_col].notnull()]
                        df["week"] = df[time_col].dt.to_period("W").apply(lambda r: r.start_time)
                        x_col = "week"
                    else:
                        x_col = col1  # fallback to first column if no timestamp


                    def is_description_column(col_name, df):
                        return (
                            "description" in col_name.lower()
                            or "message" in col_name.lower()
                            or "text" in col_name.lower()
                            or df[col_name].astype(str).str.len().mean() > 40
                        )
                    if is_description_column(x_col, df):
                        logger.info(f"⚠️ '{x_col}' is descriptive. Classifying to category.")
                        df[x_col] = df[x_col].apply(classify_text_category)
                    if is_description_column(color_col, df):
                        logger.info(f"⚠️ '{color_col}' is too descriptive. Classifying to category.")
                        df[color_col] = df[color_col].apply(classify_text_category)

                    top_x = df[x_col].value_counts().nlargest(top_n).index
                    df = df[df[x_col].isin(top_x)]

                    if color_col:
                        top_legends = df[color_col].value_counts().nlargest(legend_limit).index
                        df = df[df[color_col].isin(top_legends)]

                        df_grouped = df.groupby([x_col, color_col]).size().reset_index(name="count")
                        show_legend = df[color_col].nunique() > 1
                        fig = px.bar(df_grouped, x=x_col, y="count", color=color_col,
                                     title=title, color_discrete_sequence=color_palette)
                    else:
                        df_grouped = df.groupby(x_col).size().reset_index(name="count")
                        show_legend = False
                        fig = px.bar(df_grouped, x=x_col, y="count", title=title,
                                     color_discrete_sequence=color_palette)

                    fig.update_layout(
                        barmode="group",
                        xaxis_tickangle=-45,
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        legend=dict(orientation="v", x=1, y=1),
                        showlegend=show_legend
                    )

                else:
                    x_col = matched_cols[0]
                    top_x = df[x_col].value_counts().nlargest(top_n).index
                    df = df[df[x_col].isin(top_x)]
                    df_grouped = df.groupby(x_col).size().reset_index(name="count")
                    fig = px.bar(df_grouped, x=x_col, y="count", title=title,
                                 color_discrete_sequence=color_palette)
                    fig.update_layout(
                        xaxis_tickangle=-45,
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        legend=dict(orientation="v", x=1, y=1),
                        showlegend=False
                    )
            elif chart_type == "sankey":
                def is_description_column(col_name, df):
                    return (
                        "description" in col_name.lower()
                        or "message" in col_name.lower()
                        or "text" in col_name.lower()
                        or df[col_name].astype(str).str.len().mean() > 40
                    )
                for col in matched_cols:
                    if is_description_column(col, df):
                        logger.info(f"⚠️ '{col}' is descriptive. Classifying to category.")
                        df[col] = df[col].apply(classify_text_category)

                fig = render_sankey_chart(df, matched_cols, title=title)
            elif chart_type == "stacked_bar_chart":
                if len(matched_cols) >= 2:
                    x_col, color_col = matched_cols[0], matched_cols[1]

                    # ✅ Limit x-axis to top 10 categories to reduce clutter
                    top_x = df[x_col].value_counts().nlargest(10).index
                    df = df[df[x_col].isin(top_x)]

                    df_grouped = df.groupby([x_col, color_col]).size().reset_index(name="count")
                    show_legend = df[color_col].nunique() > 1
                    fig = px.bar(
                        df_grouped, x=x_col, y="count", color=color_col,
                        title=title, color_discrete_sequence=color_palette
                    )
                    fig.update_layout(
                        barmode="stack",
                        xaxis_tickangle=-45,
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        legend=dict(orientation="v", x=1, y=0.5),
                        showlegend=show_legend
                    )

            elif chart_type == "pie_chart":
                name_col = matched_cols[0]
                top_n = 5
                value_col = matched_cols[1] if len(matched_cols) > 1 else None
                if any(keyword in name_col.lower() for keyword in ["description", "message", "text"]):
                    df["__category__"] = df[name_col].apply(classify_text_category)
                    name_col = "__category__"
                df = df[df[name_col].notnull()]
                df = df[df[name_col].astype(str).str.lower() != 'nan']

                if value_col and pd.api.types.is_numeric_dtype(df[value_col]):
                    df_grouped = df.groupby(name_col)[value_col].sum().reset_index()
                else:
                    df[name_col] = df[name_col].astype(str)
                    df_grouped = df[name_col].value_counts().reset_index()
                    df_grouped.columns = [name_col, "count"]

                if len(df_grouped) > top_n:
                    top_categories = df_grouped[name_col].head(top_n).tolist()
                    df["__category__"] = df[name_col].apply(lambda x: x if x in top_categories else "Other")

                    if value_col and pd.api.types.is_numeric_dtype(df[value_col]):
                        df_final = df.groupby("__category__")[value_col].sum().reset_index()
                        df_final.columns = [name_col, value_col]
                    else:
                        df_final = df["__category__"].value_counts().reset_index()
                        df_final.columns = [name_col, "count"]

                    total = df_final[value_col if value_col else "count"].sum()
                    other_val = df_final[df_final[name_col] == "Other"][value_col if value_col else "count"].sum()

                    # ⚠️ If 'Other' is too large, skip grouping
                    if other_val / total > 0.3:
                        df_grouped = df_grouped.head(top_n)
                    else:
                        df_grouped = df_final
                value_col_final = value_col if value_col in df_grouped.columns else "count"
                fig = px.pie(
                    df_grouped,
                    names=name_col,
                    values= value_col_final,
                    title=title,
                    color_discrete_sequence=color_palette
                )
                fig.update_traces(textinfo="percent+label")
                fig.update_layout(
                    height=450,
                    width = 450,
                    margin=dict(l=40, r=40, t=40, b=40),
                    legend=dict(orientation="v", x=1, y=0.5)
                )

            elif chart_type == "table":
                grouped_df = df[matched_cols].value_counts().reset_index(name="count").head(10)
                fig = go.Figure(data=[go.Table(
                    header=dict(values=list(grouped_df.columns), fill_color='lightgrey', align='left', font=dict(size=12)),
                    cells=dict(
                        values=[grouped_df[col] for col in grouped_df.columns],
                        align='left',
                        height=28,
                        font=dict(size=11),
                        fill_color='white'
                    )
                )])
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=300,
                )

            elif chart_type == "summary_table":
                grouped_df = df[matched_cols].value_counts().reset_index(name="count")
                fig = go.Figure(data=[go.Table(
                    header=dict(values=list(grouped_df.columns), fill_color='lightgrey', align='left', font=dict(size=12)),
                    cells=dict(
                        values=[grouped_df[col] for col in grouped_df.columns],
                        align='left',
                        height=28,
                        font=dict(size=11),
                        fill_color='white'
                    )
                )])
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=300,
                )
            elif chart_type == "bubble_chart":
                if len(matched_cols) >= 3:
                    x_col, y_col, size_col = matched_cols[:3]

                    def is_description_column(col_name, df):
                        return (
                            "description" in col_name.lower()
                            or "message" in col_name.lower()
                            or "text" in col_name.lower()
                            or df[col_name].astype(str).str.len().mean() > 40
                        )

                    # Optional NLP classification
                    if is_description_column(x_col, df):
                        logger.info(f"⚠️ '{x_col}' is descriptive. Classifying to category.")
                        df[x_col] = df[x_col].apply(classify_text_category)
                    if is_description_column(y_col, df):
                        logger.info(f"⚠️ '{y_col}' is descriptive. Classifying to category.")
                        df[y_col] = df[y_col].apply(classify_text_category)

                    if not size_col or size_col not in df.columns:
                        # 🔁 Fallback to grouped count if size column is missing
                        df_grouped = df.groupby([x_col, y_col]).size().reset_index(name="count")
                        size_col = "count"
                    else:
                        df = df[[x_col, y_col, size_col]].dropna()
                        df[size_col] = pd.to_numeric(df[size_col], errors="coerce")
                        df[size_col].fillna(1, inplace=True)
                        df_grouped = df

                    fig = px.scatter(
                        df,
                        x=x_col,
                        y=y_col,
                        size=size_col,
                        color=y_col,
                        title=title,
                        size_max=60,
                        color_discrete_sequence=color_palette
                    )

                    fig.update_layout(
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        showlegend=True,
                        xaxis_tickangle=-30
                    )

            elif chart_type == "heat_map":
                if len(matched_cols) >= 2:
                    x, y = matched_cols[0], matched_cols[1]
                    df[x] = df[x].astype(str).str.strip().str.title()
                    df[y] = df[y].astype(str).str.strip().str.title()
                    def is_description_column(col_name, df):
                        return (
                            "description" in col_name.lower()
                            or "message" in col_name.lower()
                            or "text" in col_name.lower()
                            or df[col_name].astype(str).str.len().mean() > 40
                        )
                    if is_description_column(x, df):
                        logger.info(f"⚠️ '{x}' is descriptive. Classifying to category.")
                        df[x] = df[x].apply(classify_text_category)
                    if is_description_column(y, df):
                        logger.info(f"⚠️ '{y}' is descriptive. Classifying to category.")
                        df[y] = df[y].apply(classify_text_category)

                    top_x_values = df[x].value_counts().nlargest(15).index.tolist()
                    top_y_values = df[y].value_counts().nlargest(15).index.tolist()
                    df = df[df[x].isin(top_x_values) & df[y].isin(top_y_values)]
                    heat_df = df.groupby([x, y]).size().reset_index(name="count")
                    heat_df_pivot = heat_df.pivot(index=y, columns=x, values="count").fillna(0)
                    fig = go.Figure(data=go.Heatmap(
                        z=heat_df_pivot.values,
                        x=heat_df_pivot.columns,
                        y=heat_df_pivot.index,
                        colorscale='RdBu',
                        hoverongaps=False
                    ))
                    fig.update_layout(
                        title=title,
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        xaxis=dict(tickangle=45)
                    )

            elif chart_type == "scatter_plot":
                if len(matched_cols) >= 2:
                    x_col, y_col = matched_cols[0], matched_cols[1]

                    def is_description_column(col_name, df):
                        return (
                            "description" in col_name.lower()
                            or "message" in col_name.lower()
                            or "text" in col_name.lower()
                            or df[col_name].astype(str).str.len().mean() > 40
                        )

                    # 🧠 NLP classification for descriptive columns
                    if is_description_column(x_col, df):
                        logger.info(f"⚠️ '{x_col}' is descriptive. Classifying to category.")
                        df[x_col] = df[x_col].apply(classify_text_category)
                    if is_description_column(y_col, df):
                        logger.info(f"⚠️ '{y_col}' is descriptive. Classifying to category.")
                        df[y_col] = df[y_col].apply(classify_text_category)

                         # 🔢 Group and count for bubble size
                    df_grouped = df.groupby([x_col, y_col]).size().reset_index(name="count")

                    # 📊 Limit x and y cardinality to avoid clutter (optional)
                    top_x = df_grouped[x_col].value_counts().nlargest(15).index
                    top_y = df_grouped[y_col].value_counts().nlargest(15).index
                    df_grouped = df_grouped[df_grouped[x_col].isin(top_x) & df_grouped[y_col].isin(top_y)]

                    show_legend = False  # scatter legend is typically numeric or redundant

                    fig = px.scatter(
                        df_grouped,
                        x=x_col,
                        y=y_col,
                        size="count",
                        color="count",
                        title=title,
                        color_continuous_scale="Viridis"
                    )
                    fig.update_layout(
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40),
                        showlegend=show_legend,
                        xaxis_tickangle=-45
                    )

            elif chart_type == "box_plot":
                if len(matched_cols) >= 2:
                    fig = px.box(df, x=matched_cols[0], y=matched_cols[1], title=title)

            elif chart_type == "histogram":
                hist_col = matched_cols[0]
                def is_description_column(col_name, df):
                    return (
                        "description" in col_name.lower()
                        or "message" in col_name.lower()
                        or "text" in col_name.lower()
                        or df[col_name].astype(str).str.len().mean() > 40
                    )

                if is_description_column(hist_col, df):
                    logger.info(f"⚠️ '{hist_col}' is descriptive. Classifying to category.")
                    df[hist_col] = df[hist_col].apply(classify_text_category)
                    # Auto-detect if the column is datetime or numeric
                if "Other" in df[hist_col].values:
                    total = len(df)
                    other_count = (df[hist_col] == "Other").sum()
                    if other_count / total > 0.3:
                        logger.info("⚠️ 'Other' category dominates. Removing it from histogram.")
                        df = df[df[hist_col] != "Other"]
                if pd.api.types.is_datetime64_any_dtype(df[hist_col]):
                    df[hist_col] = pd.to_datetime(df[hist_col], errors="coerce")
                    fig = px.histogram(
                        df,
                        x=hist_col,
                        nbins=30,
                        title=title,
                        color_discrete_sequence=color_palette)
                    fig.update_layout(
                        xaxis_title=hist_col,
                        yaxis_title="Frequency",
                        xaxis_tickformat="%b %d",
                        xaxis_tickangle=-30,
                        bargap=0.1)
                else:
                    fig = px.histogram(
                        df,
                        x=hist_col,
                        nbins=30,
                        title=title,
                        color_discrete_sequence=color_palette)
                    fig.update_layout(
                        xaxis_title=hist_col,
                        yaxis_title="Frequency",
                        xaxis_tickangle=-45,
                        bargap=0.1)

            elif chart_type == "timeline":
                if len(matched_cols) >= 2:
                    # Convert to datetime and localize to naive (remove timezone)
                    df[matched_cols[0]] = pd.to_datetime(df[matched_cols[0]], errors='coerce').dt.tz_localize(None)
                    df[matched_cols[1]] = pd.to_datetime(df[matched_cols[1]], errors='coerce').dt.tz_localize(None)

                    # Remove rows with missing dates
                    df = df[df[matched_cols[0]].notna() & df[matched_cols[1]].notna()]
                    df = df[df[matched_cols[0]] > pd.Timestamp("2005-01-01")]

                    # Optional classification if a third column is long or descriptive
                    if len(matched_cols) > 2:
                        def is_description_column(col_name, df):
                            return (
                                "description" in col_name.lower()
                                or "message" in col_name.lower()
                                or "text" in col_name.lower()
                                or df[col_name].astype(str).str.len().mean() > 40
                            )
                        if is_description_column(matched_cols[2], df):
                            logger.info(f"⚠️ '{matched_cols[2]}' is too descriptive. Classifying to category.")
                            df[matched_cols[2]] = df[matched_cols[2]].apply(classify_text_category)

                    fig = px.timeline(
                        df,
                        x_start=matched_cols[0],
                        x_end=matched_cols[1],
                        y=matched_cols[2] if len(matched_cols) > 2 else None,
                        title=title
                    )

                    fig.update_layout(
                        xaxis_title="Time Range",
                        yaxis_title="Category" if len(matched_cols) > 2 else "",
                        height=400,
                        margin=dict(l=40, r=40, t=40, b=40)
                    )
            else:
                html_content += f"<div class='chart-container'><h3>⚠️ Chart type '{chart_type}' is not supported yet.</h3></div>"
                continue

            if fig:
                remove_inner_titles(fig)
                fig.update_layout(height=280, margin=dict(l=40, r=40, t=40, b=40),
                                  xaxis=dict(tickfont=dict(size=10)), yaxis=dict(tickfont=dict(size=10)))
                fig_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
                html_content += f"<div class='chart-container'><h2>{title}</h2>{fig_html}</div>"

        except Exception as e:
            logger.error(f"❌ Error generating chart '{title}': {str(e)}")
            continue
            
    html_content += """
        </div>
        <div id="summary-view">
            <h2>AI-Generated Summary</h2>
            <p>This summary will be injected dynamically based on the dashboard content.</p>
        </div>
        <footer>Generated by AI Dashboard System</footer>
    </body>
    </html>
    """
    return html_content


def lambda_handler(event, context):
    try:
        logger.info("Starting Lambda execution")

        # If event is a list, use the first element
        if isinstance(event, list):
            event = event[0]

        # Extract dashboard_data and user_query
        if "dashboard_data" in event:
            dashboard_data = event["dashboard_data"]
            user_query = event.get("user_query", "")
        else:
            body = json.loads(event.get("body", "{}"))
            dashboard_data = body.get("dashboard_data", {})
            user_query = body.get("user_query", "")

        # Convert dashboard_data to dict if it's a list
        if isinstance(dashboard_data, list):
            dashboard_data = {"dashboard": dashboard_data}

        if not dashboard_data:
            return {"statusCode": 400, "body": json.dumps({"error": "No dashboard data provided."})}

        html = generate_dashboard_html(dashboard_data, user_query)
        summary_text = invoke_summary_lambda(user_query, html)
        formatted_html = format_summary_text(summary_text)

        # Inject summary into the HTML
        html = html.replace(
            '<p>This summary will be injected dynamically based on the dashboard content.</p>',
            f'<div style="text-align:left; font-size: 16px; line-height: 1.6;">{formatted_html}</div>'
        )

        # Save HTML to temp file
        timestamp = int(time.time())
        filename = f"dashboard_{timestamp}.html"
        filepath = os.path.join(TEMP_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        # Upload dashboard to S3
        s3.upload_file(
            filepath,
            OUTPUT_BUCKET_NAME,
            f"dashboards/{filename}",
            ExtraArgs={"ContentType": "text/html; charset=utf-8"}
        )

        # Log input event to S3
        s3.put_object(
            Bucket=OUTPUT_BUCKET_NAME,
            Key=f"logs/input_{timestamp}.json",
            Body=json.dumps(event),
            ContentType="application/json"
        )

        url = f"https://{OUTPUT_BUCKET_NAME}.s3.amazonaws.com/dashboards/{filename}"
        return {"statusCode": 200, "body": json.dumps({"dashboard_url": url})}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}