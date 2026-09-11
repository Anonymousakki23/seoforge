"""Google Search Console Integration — OAuth2 + Analytics API."""
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_FILE = Path("/root/Documents/Codex/seoforge/gsc_config.json")
TOKEN_FILE = Path("/root/Documents/Codex/seoforge/gsc_token.json")

# Google OAuth2 URLs
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_API = "https://www.googleapis.com/webmasters/v3"
GSC_SEARCH_API = "https://searchconsole.googleapis.com/webmasters/v3"

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"client_id": "", "client_secret": "", "redirect_uri": "", "property_url": "", "configured": False}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def load_token():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}

def save_token(token):
    TOKEN_FILE.write_text(json.dumps(token, indent=2))

def get_auth_url():
    cfg = load_config()
    if not cfg.get("client_id"):
        return None
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg.get("redirect_uri", "http://localhost:8888/gsc-callback"),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)

async def exchange_code(code):
    cfg = load_config()
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg.get("redirect_uri", "http://localhost:8888/gsc-callback"),
        "grant_type": "authorization_code"
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            token = json.loads(resp.read())
        token["created_at"] = datetime.now().isoformat()
        save_token(token)
        return {"ok": True, "token": token}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def refresh_token():
    cfg = load_config()
    token = load_token()
    if not token.get("refresh_token"):
        return None
    data = urllib.parse.urlencode({
        "refresh_token": token["refresh_token"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type": "refresh_token"
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            new_token = json.loads(resp.read())
        new_token["refresh_token"] = token["refresh_token"]
        new_token["created_at"] = datetime.now().isoformat()
        save_token(new_token)
        return new_token
    except:
        return token

async def gsc_api_call(endpoint, params=None):
    cfg = load_config()
    token = load_token()
    if not token.get("access_token"):
        # Try refresh
        token = await refresh_token()
        if not token:
            return {"error": "Not authenticated. Connect to GSC first."}

    url = endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Token expired, refresh
            token = await refresh_token()
            if token:
                req.add_header("Authorization", f"Bearer {token['access_token']}")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
        return {"error": f"API error {e.code}: {e.read().decode()[:200]}"}

async def get_search_analytics(days=28):
    cfg = load_config()
    property_url = cfg.get("property_url", "")
    if not property_url:
        return {"error": "No property configured"}
    end_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days+3)).strftime("%Y-%m-%d")
    endpoint = f"{GSC_API}/sites/{urllib.parse.quote(property_url, safe='')}/searchAnalytics/query"
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query", "page"],
        "rowLimit": 25,
        "startRow": 0
    }
    token = load_token()
    if not token.get("access_token"):
        token = await refresh_token()
        if not token:
            return {"error": "Not authenticated"}

    body = json.dumps(payload).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data
    except urllib.error.HTTPError as e:
        try:
            token = await refresh_token()
            req.add_header("Authorization", f"Bearer {token['access_token']}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except:
            return {"error": f"GSC API error {e.code}"}

async def get_url_inspection(url):
    """URL Inspection via Indexing API (requires additional setup)."""
    token = load_token()
    if not token.get("access_token"):
        return {"error": "Not authenticated"}
    # Note: URL Inspection requires special API access
    # This is a simplified version using Search Analytics
    cfg = load_config()
    property_url = cfg.get("property_url", "")
    end_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    endpoint = f"{GSC_API}/sites/{urllib.parse.quote(property_url, safe='')}/searchAnalytics/query"
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["page"],
        "dimensionFilterGroups": [{"filters": [{"dimension": "page", "expression": url}]}],
        "rowLimit": 1
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token['access_token']}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)[:200]}

async def get_sitemaps():
    cfg = load_config()
    property_url = cfg.get("property_url", "")
    if not property_url:
        return {"error": "No property configured"}
    endpoint = f"{GSC_API}/sites/{urllib.parse.quote(property_url, safe='')}/sitemaps"
    return await gsc_api_call(endpoint)

async def get_site_summary():
    """Get overall site performance summary."""
    analytics = await get_search_analytics(28)
    sitemaps = await get_sitemaps()

    summary = {"period": "Last 28 days", "analytics": {}, "sitemaps": {}}

    if "rows" in analytics:
        total_clicks = sum(r.get("clicks", 0) for r in analytics["rows"])
        total_impressions = sum(r.get("impressions", 0) for r in analytics["rows"])
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        avg_position = sum(r.get("position", 0) for r in analytics["rows"]) / len(analytics["rows"]) if analytics["rows"] else 0

        summary["analytics"] = {
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "avg_ctr": round(avg_ctr, 2),
            "avg_position": round(avg_position, 1),
            "top_queries": [{"query": r["keys"][0], "clicks": r.get("clicks",0), "impressions": r.get("impressions",0), "position": round(r.get("position",0),1)} for r in analytics.get("rows", [])[:10]],
            "total_queries": len(analytics.get("rows", []))
        }
    elif "error" in analytics:
        summary["analytics"]["error"] = analytics["error"]

    if "sitemapEntries" in sitemaps:
        summary["sitemaps"] = {"count": len(sitemaps["sitemapEntries"]), "entries": sitemaps["sitemapEntries"][:5]}
    elif "error" in sitemaps:
        summary["sitemaps"]["error"] = sitemaps["error"]

    return summary
