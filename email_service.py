"""Email Report Service — SMTP-based SEO report emails with PDF attachments."""
import smtplib
import ssl
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime

CONFIG_FILE = Path("/root/Documents/Codex/seoforge/email_config.json")

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_pass": "", "from_name": "SEOForge", "from_email": "", "enabled": False}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def send_email(to, subject, html_body, pdf_bytes=None, pdf_name="seo-report.pdf"):
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("smtp_host"):
        return {"ok": False, "error": "Email not configured. Set SMTP settings first."}

    msg = MIMEMultipart("mixed")
    msg["From"] = f"{cfg.get('from_name','SEOForge')} <{cfg['from_email']}>"
    msg["To"] = to
    msg["Subject"] = subject

    # HTML body
    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(html_part)

    # PDF attachment
    if pdf_bytes:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={pdf_name}")
        msg.attach(part)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            if cfg.get("smtp_user") and cfg.get("smtp_pass"):
                server.login(cfg["smtp_user"], cfg["smtp_pass"])
            server.sendmail(cfg["from_email"], to, msg.as_string())
        return {"ok": True, "message": f"Email sent to {to}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def build_report_html(results, fixes=None):
    score = results.get("score", 0)
    color = "#22c55e" if score >= 80 else "#eab308" if score >= 50 else "#ef4444"
    meta = results.get("meta", {})
    checks = results.get("checks", [])
    passed = sum(1 for c in checks if c["status"] == "pass")
    warnings = sum(1 for c in checks if c["status"] == "warning")
    errors = sum(1 for c in checks if c["status"] == "error")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body style="margin:0;padding:0;background:#0f1117;font-family:-apple-system,sans-serif">
<div style="max-width:600px;margin:0 auto;background:#1a1d27;border-radius:12px;overflow:hidden">

<div style="background:linear-gradient(135deg,#00d4ff,#7c3aed);padding:24px;text-align:center">
<h1 style="color:#fff;margin:0;font-size:24px">🔍 SEO Audit Report</h1>
<p style="color:rgba(255,255,255,.8);margin:4px 0 0;font-size:14px">{results.get('url','')}</p>
</div>

<div style="padding:24px;text-align:center">
<div style="display:inline-block;width:100px;height:100px;border-radius:50%;border:4px solid {color};line-height:100px;font-size:40px;font-weight:800;color:{color}">{score}</div>
<p style="color:#71717a;margin:8px 0 0;font-size:12px">SEO Score out of 100</p>
</div>

<div style="padding:0 24px 16px">
<table style="width:100%;border-collapse:collapse">
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Status Code</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;font-weight:700;font-size:13px">{results.get('status_code','')}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Response Time</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;font-weight:700;font-size:13px">{results.get('response_time_ms',0)}ms</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Page Size</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;font-weight:700;font-size:13px">{round(results.get('content_length',0)/1024,1)}KB</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Word Count</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;font-weight:700;font-size:13px">{meta.get('word_count',0)}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Passed</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#22c55e;font-weight:700;font-size:13px">{passed}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Warnings</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#eab308;font-weight:700;font-size:13px">{warnings}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#71717a;font-size:13px">Errors</td><td style="padding:8px;border-bottom:1px solid #2a2d3a;color:#ef4444;font-weight:700;font-size:13px">{errors}</td></tr>
</table>
</div>

<div style="padding:0 24px 24px">
<h3 style="color:#00d4ff;font-size:14px;margin-bottom:8px">📋 Check Results</h3>
{"".join(f'<div style="padding:6px 0;border-bottom:1px solid #2a2d3a;font-size:12px"><span style="color:{"#22c55e" if c["status"]=="pass" else "#eab308" if c["status"]=="warning" else "#ef4444"};font-weight:600">{"✅" if c["status"]=="pass" else "⚠️" if c["status"]=="warning" else "❌"} {c["name"]}</span><br><span style="color:#71717a">{c["message"][:100]}</span></div>' for c in checks)}
</div>"""

    if fixes and fixes.get("fixes"):
        html += f"""<div style="padding:0 24px 24px">
<h3 style="color:#00d4ff;font-size:14px;margin-bottom:8px">🤖 AI Fixes</h3>
{"".join(f'<div style="padding:8px;margin-bottom:6px;background:#0f1117;border-radius:6px;border-left:3px solid {"#ef4444" if f.get("priority")=="high" else "#eab308"}"><b style="font-size:12px;color:#e4e4e7">{f.get("title","")}</b><br><span style="color:#71717a;font-size:11px">{f.get("description","")[:120]}</span></div>' for f in fixes["fixes"][:5])}
</div>"""

    if fixes and fixes.get("seo_report"):
        html += f"""<div style="padding:0 24px 24px">
<h3 style="color:#00d4ff;font-size:14px;margin-bottom:8px">📊 SEO Summary</h3>
<p style="color:#71717a;font-size:13px;line-height:1.6">{fixes["seo_report"]}</p>
</div>"""

    html += f"""<div style="padding:16px 24px;background:#0f1117;text-align:center;border-radius:0 0 12px 12px">
<p style="color:#71717a;font-size:11px;margin:0">Generated by SEOForge v2.0 • {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div></div></body></html>"""
    return html
