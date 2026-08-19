#!/usr/bin/env python3
"""
Warren Task Scheduler - Runs market_scanner at 7 AM (ASX) and 7 PM (US)
Integrates dual-market scan results and manages daily reporting
"""

import subprocess
import json
import os
from datetime import datetime
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import webbrowser

# ============================================================================
# CONFIG
# ============================================================================

SCANNER_SCRIPT = "C:/Users/squat/OneDrive/Desktop/CLAUDE TRAINING/trading_scanner/market_scanner.py"
OUTPUT_DIR = "C:/Users/squat/OneDrive/Desktop/CLAUDE TRAINING/trading_scanner/scan_output"
LOG_FILE = "C:/Users/squat/OneDrive/Desktop/CLAUDE TRAINING/trading_scanner/warren_log.txt"

# Email config (optional)
SEND_EMAIL = False  # Set to True if you want email alerts
EMAIL_FROM = "your_email@gmail.com"
EMAIL_TO = "squatter_@hotmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # Use env var for security

# ============================================================================
# LOGGING
# ============================================================================

def log(message: str):
    """Log message to file and console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] {message}"
    print(msg)

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(msg + '\n')

# ============================================================================
# SCAN RUNNER
# ============================================================================

def run_market_scan():
    """Execute market_scanner.py and return results"""
    log(f"Starting market scan...")

    try:
        result = subprocess.run(
            ["python", SCANNER_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            log(f"❌ Scanner failed: {result.stderr}")
            return None

        log(f"✅ Scanner completed successfully")
        return result.stdout

    except Exception as e:
        log(f"❌ Error running scanner: {e}")
        return None

# ============================================================================
# REPORT AGGREGATION
# ============================================================================

def get_latest_reports():
    """Find and read latest scan reports"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    reports = {}
    try:
        files = sorted(Path(OUTPUT_DIR).glob("scan_*.html"), reverse=True)

        # Group by market_category (latest of each)
        for file in files[:8]:  # Last 8 files (4 combos × 2 runs)
            # Parse filename: scan_MARKET_CATEGORY_timestamp.html
            parts = file.stem.split('_')
            if len(parts) >= 3:
                market = parts[1]  # ASX or US
                category = parts[2]  # megacap or midcap
                key = f"{market}_{category}"

                if key not in reports:
                    reports[key] = str(file)

    except Exception as e:
        log(f"⚠️ Error reading reports: {e}")

    return reports

# ============================================================================
# EMAIL ALERT (Optional)
# ============================================================================

def send_email_alert(reports: dict):
    """Send email with top picks from each market"""
    if not SEND_EMAIL or not EMAIL_PASSWORD:
        return

    try:
        # Read reports and extract top scorecards
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Trading Scanner Alert - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        html_body = """<html><body>
<h2>📊 Daily Trading Scanner Results</h2>
<p>Click links below to review in BoxRunner Dashboard</p>
"""

        for key, filepath in reports.items():
            market, category = key.split('_')
            html_body += f"""
<h3>{market} {category.upper()}</h3>
<p><a href="file:///{filepath}">Open Report</a></p>
"""

        html_body += """</body></html>"""

        msg.attach(MIMEText(html_body, "html"))

        # Send via Gmail (requires app password)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

        log(f"✅ Email alert sent to {EMAIL_TO}")

    except Exception as e:
        log(f"⚠️ Email failed: {e}")

# ============================================================================
# REPORT DASHBOARD
# ============================================================================

def create_daily_dashboard(reports: dict) -> str:
    """Create unified dashboard showing all markets/categories"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    dashboard_file = f"{OUTPUT_DIR}/DASHBOARD_{timestamp}.html"

    html = """<!DOCTYPE html>
<html>
<head>
    <title>Trading Scanner Dashboard</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        .report-card {
            background: white;
            border: 2px solid #667eea;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .report-card:hover {
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transform: translateY(-5px);
        }
        .report-title {
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }
        .report-time {
            font-size: 12px;
            color: #999;
            margin-bottom: 15px;
        }
        .btn {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 600;
        }
        .btn:hover {
            background: #5568d3;
        }
        .footer {
            text-align: center;
            color: #999;
            font-size: 12px;
            margin-top: 40px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Daily Trading Scanner</h1>
        <p>Scorecards for BoxRunner - {datetime.now().strftime('%A, %B %d, %Y')}</p>
    </div>

    <div class="grid">
"""

    for key, filepath in reports.items():
        market, category = key.split('_')
        market_name = "🇦🇺 Australian" if market == "ASX" else "🇺🇸 US"

        html += f"""
        <div class="report-card">
            <div class="report-title">{market_name} {category.upper()}</div>
            <div class="report-time">Generated just now</div>
            <a href="file:///{filepath}" class="btn">Open Report</a>
        </div>
"""

    html += """
    </div>

    <div class="footer">
        <p>Scan results ready for BoxRunner review. Scores out of 50.</p>
        <p>Auto-generated by Warren Scanner</p>
    </div>
</body>
</html>
"""

    with open(dashboard_file, 'w') as f:
        f.write(html)

    log(f"✅ Dashboard created: {dashboard_file}")
    return dashboard_file

# ============================================================================
# MAIN TASK RUNNER
# ============================================================================

def run_warren_task():
    """
    Main task executed by Warren at 7 AM and 7 PM
    Runs scanner, aggregates reports, sends alerts
    """
    log(f"\n{'='*80}")
    log(f"WARREN TASK: Dual-Market Scanner")
    log(f"{'='*80}")

    # Run scanner
    output = run_market_scan()
    if not output:
        log("❌ Scanner failed - aborting")
        return False

    # Get reports
    reports = get_latest_reports()
    log(f"✅ Found {len(reports)} report(s)")

    if reports:
        # Create dashboard
        dashboard = create_daily_dashboard(reports)

        # Send email alert
        if SEND_EMAIL:
            send_email_alert(reports)

        # Open first report in browser (for visual confirmation)
        if reports:
            first_report = list(reports.values())[0]
            try:
                webbrowser.open(f"file:///{first_report}")
                log(f"✅ Opened report in browser")
            except:
                log(f"⚠️ Could not open browser")

    log(f"{'='*80}")
    log(f"✅ Task completed successfully")
    log(f"{'='*80}\n")

    return True

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Running in TEST mode (single scan)...")
        run_warren_task()
    else:
        print("Use: python warren_scheduler.py [--test]")
        print("  (no args) = run as scheduled task")
        print("  --test    = run single scan immediately")
        run_warren_task()
