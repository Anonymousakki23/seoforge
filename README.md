# SEOForge v2.0 — AI-Powered SEO Platform

A full-featured SEO audit, optimization, and monitoring platform with AI-powered insights, email reports, and Google Search Console integration.

## Features

- **Full SEO Audit** — 15+ on-page checks with score and AI auto-fixes
- **AI Keywords** — 25+ keyword suggestions by intent
- **Competitor Comparison** — side-by-side analysis with recommendations
- **Content Optimizer** — title, description, and heading suggestions
- **Schema Generator** — 8 structured data types (Organization, Restaurant, FAQ, etc.)
- **Robots.txt Generator** — 3 site presets
- **Sitemap Generator** — crawls pages and builds XML sitemaps
- **Bulk Analyzer** — up to 10 URLs at once
- **Domain Authority Checker** — 11 trust signals scored 0-100
- **Scheduled Auto-Scans** — daily, weekly, or monthly
- **PDF Report Export** — branded PDF with audit results and AI fixes
- **Email Reports** — SMTP-based reports with PDF attachments
- **Google Search Console** — OAuth2, analytics, top queries, CTR/position data

## Quick Start

```bash
pip install -r requirements.txt
export OMNIROUTE_URL="http://localhost:20128/v1"   # local OmniRoute gateway (free routes)
python app.py
```

Open http://localhost:8888 in your browser.

## Configuration

### AI (OmniRoute, free)
Set the `OMNIROUTE_URL` environment variable to your OmniRoute gateway (e.g. `http://localhost:20128/v1`). Optional: `OMNIROUTE_MODEL` (default `auto`), `OMNIROUTE_API_KEY` if your gateway requires one. There is no paid-key fallback by design — if the gateway is unreachable, AI features return an error instead of billing anything. On Render, set `OMNIROUTE_URL` to a gateway reachable from Render's network.

### Data directory
Scans, configs, and schedules are stored in the data directory (`./data` by default, override with `SEOFORGE_DATA_DIR`). Note: Render's free tier has an ephemeral filesystem — data is lost on each redeploy/restart. The app listens on `PORT` (Render sets this automatically), falling back to `SEOFORGE_PORT` or `8888`.

### Email Reports
In the **Email** tab, configure your SMTP server:
- SMTP host and port (e.g., `smtp.gmail.com:587`)
- Username and password
- Sender name and email

### Google Search Console
1. Create OAuth2 credentials in [Google Cloud Console](https://console.cloud.google.com/)
2. Set the redirect URI to `http://localhost:8888/api/gsc/callback`
3. Enter your client ID, client secret, and property URL in the **GSC** tab

## Tech Stack

- **Backend:** Python 3.12+, aiohttp, BeautifulSoup4, ReportLab
- **Frontend:** Vanilla HTML/CSS/JS (single-file SPA)
- **AI:** OmniRoute gateway (free routes, OpenAI-compatible)
- **External APIs:** Google Search Console (OAuth2)
