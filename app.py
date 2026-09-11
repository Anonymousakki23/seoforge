import aiohttp, asyncio, json, os, re, sys, time, urllib.request
from html import unescape
from collections import Counter
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.units import inch

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
PORT = int(os.environ.get("SEOFORGE_PORT", 8888))
HOST = "0.0.0.0"
SCANS_DIR = Path("/root/Documents/Codex/seoforge/scans")
SCANS_DIR.mkdir(exist_ok=True)
SCHEDULE_FILE = Path("/root/Documents/Codex/seoforge/schedule.json")

# ============================================================
# AI
# ============================================================
async def ask_gemini(prompt, temperature=0.3, max_tokens=2048):
    payload = {"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"temperature":temperature,"maxOutputTokens":max_tokens}}
    req = urllib.request.Request(GEMINI_URL+"?key="+GEMINI_KEY, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Error: {e}"

async def ai_json(prompt):
    reply = await ask_gemini(prompt, 0.3, 2048)
    match = re.search(r'```json\s*([\s\S]*?)```', reply)
    if match: return json.loads(match.group(1))
    match = re.search(r'\{[\s\S]*\}', reply)
    if match: return json.loads(match.group())
    return {"raw": reply}

# ============================================================
# CRAWLER
# ============================================================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

async def fetch_url(url, session):
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15), ssl=False, allow_redirects=True) as resp:
            return resp.status, await resp.text(), dict(resp.headers), str(resp.url)
    except Exception as e:
        return 0, str(e), {}, url

# ============================================================
# SEO ANALYZER
# ============================================================
def analyze_seo(url, status, html, headers, elapsed, final_url=""):
    soup = BeautifulSoup(html, "lxml") if html and status == 200 else None
    r = {"url":url,"final_url":final_url,"status_code":status,"response_time_ms":round(elapsed*1000),"content_length":len(html) if html else 0,"checks":[],"score":0,"meta":{},"timestamp":datetime.now().isoformat()}
    if not soup:
        r["checks"].append({"name":"Connection","status":"error","message":f"Failed: {html[:200]}","score":0,"max":10}); return r

    title = soup.find("title"); r["meta"]["title"] = title.get_text(strip=True) if title else ""
    md = soup.find("meta", attrs={"name":re.compile("description",re.I)}); r["meta"]["description"] = md.get("content","") if md else ""
    r["meta"]["canonical"] = (soup.find("link",rel="canonical") or {}).get("href","")
    html_tag = soup.find("html"); r["meta"]["lang"] = html_tag.get("lang","") if html_tag else ""
    og_tags = {t.get("property",""):t.get("content","") for t in soup.find_all("meta",property=re.compile("^og:"))}
    r["meta"]["og"] = og_tags
    tw_tags = {t.get("name",""):t.get("content","") for t in soup.find_all("meta",attrs={"name":re.compile("^twitter:",re.I)})}
    r["meta"]["twitter"] = tw_tags
    jsonld = soup.find_all("script",type="application/ld+json")
    r["meta"]["jsonld_count"] = len(jsonld)
    r["meta"]["jsonld"] = [j.string for j in jsonld if j.string]
    h1s = soup.find_all("h1")
    h_tags = {f"h{i}":len(soup.find_all(f"h{i}")) for i in range(1,7)}
    imgs = soup.find_all("img")
    no_alt = [i for i in imgs if not i.get("alt","").strip()]
    links = soup.find_all("a",href=True)
    base = "/".join(url.split("/")[:3])
    internal = [l for l in links if (l.get("href","") or "").startswith("/") or base in (l.get("href","") or "")]
    external = [l for l in links if (l.get("href","") or "").startswith("http") and base not in (l.get("href","") or "")]
    word_count = len(soup.get_text().split())
    r["meta"].update({"word_count":word_count,"h1_count":len(h1s),"h1_text":h1s[0].get_text(strip=True)[:100] if h1s else "","heading_structure":{k:v for k,v in h_tags.items() if v>0},"total_images":len(imgs),"images_no_alt":len(no_alt),"total_links":len(links),"internal_links":len(internal),"external_links":len(external)})

    def add(name, status, msg, score, mx=10):
        r["checks"].append({"name":name,"status":status,"message":msg,"score":score,"max":mx})

    t = r["meta"]["title"]
    if not t: add("Title Tag","error","Missing",0)
    elif len(t)<30: add("Title Tag","warning",f"Too short ({len(t)} chars). Aim 50-60.",5)
    elif len(t)>60: add("Title Tag","warning",f"Too long ({len(t)} chars).",7)
    else: add("Title Tag","pass",f"Good ({len(t)} chars)",10)
    d = r["meta"]["description"]
    if not d: add("Meta Description","error","Missing",0)
    elif len(d)<70: add("Meta Description","warning",f"Too short ({len(d)}). Aim 120-160.",5)
    elif len(d)>160: add("Meta Description","warning",f"Too long ({len(d)}).",7)
    else: add("Meta Description","pass",f"Good ({len(d)} chars)",10)
    if not r["meta"]["canonical"]: add("Canonical URL","warning","Missing",3)
    else: add("Canonical URL","pass","Set",10)
    if len(h1s)==0: add("H1 Tag","error","No H1",0)
    elif len(h1s)>1: add("H1 Tag","warning",f"Multiple H1 ({len(h1s)})",5)
    else: add("H1 Tag","pass",f"H1: \"{h1s[0].get_text(strip=True)[:80]}\"",10)
    og_needed=["og:title","og:description","og:image","og:url"]
    og_found=[o for o in og_needed if o in og_tags]
    if len(og_found)<4: add("Open Graph","warning",f"Missing: {', '.join([o for o in og_needed if o not in og_tags])}",max(0,10-len(og_needed)*3))
    else: add("Open Graph","pass","All OG present",10)
    if not tw_tags: add("Twitter Card","warning","Missing",2)
    else: add("Twitter Card","pass",f"Present ({len(tw_tags)})",10)
    if r["meta"]["jsonld_count"]==0: add("JSON-LD Schema","warning","No structured data",0)
    else: add("JSON-LD Schema","pass",f"Found ({r['meta']['jsonld_count']})",10)
    if not r["meta"]["lang"] or r["meta"]["lang"]=="zxx": add("HTML Lang","error",f"Invalid: \"{r['meta']['lang']}\"",0)
    else: add("HTML Lang","pass",f"Lang: {r['meta']['lang']}",10)
    if imgs:
        alt_pct = round((len(imgs)-len(no_alt))/len(imgs)*100)
        if no_alt: add("Image Alt","warning",f"{len(no_alt)}/{len(imgs)} missing ({100-alt_pct}%)",max(0,10-len(no_alt)*2))
        else: add("Image Alt","pass",f"All {len(imgs)} have alt",10)
    total_h = sum(h_tags.values())
    if total_h<3: add("Heading Structure","warning",f"Only {total_h} headings",4)
    else: add("Heading Structure","pass",f"Good: {' > '.join([f'{k}({v})' for k,v in h_tags.items() if v>0])}",10)
    if len(links)==0: add("Links","warning","No links",2)
    else: add("Links","pass",f"{len(links)}: {len(internal)} int, {len(external)} ext",8)
    if not r["meta"].get("viewport"): add("Viewport","warning","Missing",0)
    else: add("Viewport","pass","Present",10)
    if url.startswith("https://"): add("HTTPS","pass","Yes",10)
    else: add("HTTPS","error","No HTTPS!",0)
    rt = elapsed*1000
    if rt>3000: add("Speed","error",f"{round(rt)}ms",2)
    elif rt>1000: add("Speed","warning",f"{round(rt)}ms",6)
    else: add("Speed","pass",f"{round(rt)}ms",10)
    if word_count<300: add("Content","warning",f"{word_count} words. Aim 1000+.",4)
    elif word_count<1000: add("Content","warning",f"{word_count} words. Aim 1000+.",7)
    else: add("Content","pass",f"{word_count} words",10)

    total_score = sum(c.get("score",0) for c in r["checks"])
    total_max = sum(c.get("max",10) for c in r["checks"])
    r["score"] = round(total_score/total_max*100) if total_max>0 else 0
    return r

# ============================================================
# PDF REPORT GENERATOR
# ============================================================
def generate_pdf_report(results, fixes=None):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []
    score = results.get("score", 0)
    color = colors.green if score >= 80 else colors.orange if score >= 50 else colors.red

    # Title
    story.append(Paragraph(f"SEO Audit Report", styles["Title"]))
    story.append(Paragraph(f"URL: {results.get('url','')} | Score: {score}/100", styles["Normal"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Tool: SEOForge v2.0", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#00d4ff")))
    story.append(Spacer(1, 12))

    # Score
    story.append(Paragraph(f"Overall Score: {score}/100", styles["Heading1"]))
    meta = results.get("meta", {})
    info_data = [
        ["Status Code", str(results.get("status_code",""))],
        ["Response Time", f"{results.get('response_time_ms',0)}ms"],
        ["Page Size", f"{round(results.get('content_length',0)/1024,1)}KB"],
        ["Word Count", str(meta.get("word_count",0))],
        ["Title", meta.get("title","N/A")[:80]],
        ["Description", meta.get("description","N/A")[:80]],
        ["H1", meta.get("h1_text","N/A")[:80]],
        ["Images", f"{meta.get('total_images',0)} ({meta.get('images_no_alt',0)} missing alt)"],
        ["Links", f"{meta.get('total_links',0)}: {meta.get('internal_links',0)} int, {meta.get('external_links',0)} ext"],
    ]
    t = Table(info_data, colWidths=[120, 380])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), colors.HexColor("#1a1d27")), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#00d4ff")), ("FONTSIZE", (0,0), (-1,-1), 9), ("PADDING", (0,0), (-1,-1), 6), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#2a2d3a"))]))
    story.append(t)
    story.append(Spacer(1, 16))

    # Checks
    story.append(Paragraph("SEO Checks", styles["Heading1"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#2a2d3a")))
    story.append(Spacer(1, 8))
    check_data = [["Check", "Status", "Score", "Message"]]
    for c in results.get("checks", []):
        s = c.get("status","")
        sc = f"{c.get('score',0)}/{c.get('max',10)}"
        msg = c.get("message","")[:60]
        check_data.append([c.get("name",""), s.upper(), sc, msg])
    t2 = Table(check_data, colWidths=[100, 60, 50, 290])
    t2.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#00d4ff")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTSIZE", (0,0), (-1,-1), 8), ("PADDING", (0,0), (-1,-1), 4), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#2a2d3a"))]))
    story.append(t2)
    story.append(Spacer(1, 16))

    # AI Fixes
    if fixes and fixes.get("fixes"):
        story.append(Paragraph("AI-Generated Fixes", styles["Heading1"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#00d4ff")))
        story.append(Spacer(1, 8))
        for fix in fixes["fixes"]:
            story.append(Paragraph(f"<b>[{fix.get('priority','').upper()}]</b> {fix.get('title','')}", styles["Normal"]))
            story.append(Paragraph(f"{fix.get('description','')}", styles["Normal"]))
            if fix.get("code_fix"):
                story.append(Paragraph(f"<font color='#00d4ff' size='7'>{fix['code_fix'][:200]}</font>", styles["Normal"]))
            story.append(Spacer(1, 6))
        story.append(Spacer(1, 12))

    # Report
    if fixes and fixes.get("seo_report"):
        story.append(Paragraph("SEO Summary", styles["Heading1"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#00d4ff")))
        story.append(Spacer(1, 8))
        story.append(Paragraph(fixes["seo_report"], styles["Normal"]))

    doc.build(story)
    return buf.getvalue()

# ============================================================
# DOMAIN AUTHORITY CHECKER
# ============================================================
async def check_domain_authority(url, session):
    base_domain = url.split("//")[-1].split("/")[0].lower()
    result = {"domain": base_domain, "url": url, "metrics": {}, "analysis": {}}
    # Fetch main page
    start = time.time()
    status, html, headers, final_url = await fetch_url(url, session)
    elapsed = time.time() - start
    result["metrics"]["response_time_ms"] = round(elapsed * 1000)
    result["metrics"]["status_code"] = status
    if status != 200 or not html:
        result["analysis"]["score"] = 0
        result["analysis"]["verdict"] = "Site unreachable"
        return result

    soup = BeautifulSoup(html, "lxml")
    # Count signals
    result["metrics"]["has_https"] = url.startswith("https://")
    result["metrics"]["title_length"] = len((soup.find("title") or {}).get_text(strip=True) if soup.find("title") else "")
    result["metrics"]["has_meta_desc"] = bool(soup.find("meta", attrs={"name": re.compile("description", re.I)}))
    result["metrics"]["has_canonical"] = bool(soup.find("link", rel="canonical"))
    result["metrics"]["has_og"] = bool(soup.find_all("meta", property=re.compile("^og:")))
    result["metrics"]["has_schema"] = bool(soup.find_all("script", type="application/ld+json"))
    result["metrics"]["has_viewport"] = bool(soup.find("meta", attrs={"name": "viewport"}))
    result["metrics"]["h1_count"] = len(soup.find_all("h1"))
    result["metrics"]["image_count"] = len(soup.find_all("img"))
    result["metrics"]["images_no_alt"] = len([i for i in soup.find_all("img") if not i.get("alt", "").strip()])
    result["metrics"]["link_count"] = len(soup.find_all("a", href=True))
    result["metrics"]["word_count"] = len(soup.get_text().split())
    result["metrics"]["page_size_kb"] = round(len(html) / 1024, 1)
    head_tags = soup.find_all(re.compile(r"^h\d$"))
    result["metrics"]["heading_depth"] = max((int(t.name[1]) for t in head_tags), default=0) if head_tags else 0

    # Compute trust/authority score
    score = 0
    signals = []
    if result["metrics"]["has_https"]: score += 10; signals.append("✓ HTTPS")
    else: signals.append("✗ No HTTPS")
    if result["metrics"]["has_meta_desc"]: score += 8; signals.append("✓ Meta description")
    else: signals.append("✗ No meta description")
    if result["metrics"]["has_canonical"]: score += 8; signals.append("✓ Canonical URL")
    else: signals.append("✗ No canonical")
    if result["metrics"]["has_og"]: score += 7; signals.append("✓ Open Graph")
    else: signals.append("✗ No Open Graph")
    if result["metrics"]["has_schema"]: score += 10; signals.append("✓ JSON-LD Schema")
    else: signals.append("✗ No structured data")
    if result["metrics"]["has_viewport"]: score += 7; signals.append("✓ Mobile viewport")
    else: signals.append("✗ No mobile viewport")
    if result["metrics"]["h1_count"] == 1: score += 8; signals.append("✓ Single H1")
    else: signals.append(f"✗ H1: {result['metrics']['h1_count']}")
    if result["metrics"]["word_count"] > 500: score += 10; signals.append(f"✓ Content: {result['metrics']['word_count']} words")
    else: signals.append(f"✗ Thin content: {result['metrics']['word_count']} words")
    if result["metrics"]["response_time_ms"] < 2000: score += 10; signals.append(f"✓ Speed: {result['metrics']['response_time_ms']}ms")
    else: signals.append(f"✗ Slow: {result['metrics']['response_time_ms']}ms")
    if result["metrics"]["images_no_alt"] == 0 and result["metrics"]["image_count"] > 0: score += 8; signals.append("✓ All images have alt")
    elif result["metrics"]["image_count"] > 0: score += 4; signals.append(f"✗ {result['metrics']['images_no_alt']} images missing alt")
    else: score += 5; signals.append("○ No images")
    if result["metrics"]["title_length"] >= 30 and result["metrics"]["title_length"] <= 60: score += 7; signals.append(f"✓ Title: {result['metrics']['title_length']} chars")
    else: signals.append(f"✗ Title: {result['metrics']['title_length']} chars")

    result["analysis"]["score"] = min(score, 100)
    result["analysis"]["signals"] = signals
    result["analysis"]["verdict"] = "Excellent" if score >= 80 else "Good" if score >= 60 else "Fair" if score >= 40 else "Poor" if score >= 20 else "Very Poor"
    return result

# ============================================================
# SCHEDULED SCANS
# ============================================================
def load_schedule():
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())
    return {"scans": []}

def save_schedule(data):
    SCHEDULE_FILE.write_text(json.dumps(data, indent=2))

async def run_scheduled_scan(url):
    start = time.time()
    async with aiohttp.ClientSession() as session:
        status, html, headers, final_url = await fetch_url(url, session)
    elapsed = time.time() - start
    results = analyze_seo(url, status, html, headers, elapsed, final_url)
    # Save scan
    scan_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    scan_file = SCANS_DIR / f"{url.split('//')[-1].replace('/', '_')}_{scan_id}.json"
    scan_file.write_text(json.dumps(results, indent=2))
    return results

# ============================================================
# HANDLERS
# ============================================================
from aiohttp import web

async def handle_index(request):
    return web.Response(text=Path("static/index.html").read_text(), content_type="text/html")

async def handle_analyze(request):
    data = await request.json()
    url = data.get("url","").strip()
    if not url: return web.json_response({"error":"URL required"})
    if not url.startswith("http"): url = "https://"+url
    start = time.time()
    async with aiohttp.ClientSession() as session:
        status, html, headers, final_url = await fetch_url(url, session)
    elapsed = time.time()-start
    return web.json_response(analyze_seo(url, status, html, headers, elapsed, final_url))

async def handle_ai_fixes(request):
    data = await request.json()
    url = data.get("url",""); results = data.get("results",{}); meta = results.get("meta",{})
    checks = "\n".join([f"- [{c['status'].upper()}] {c['name']}: {c['message']}" for c in results.get("checks",[])])
    prompt = f"""SEO fixes for {url}\nTitle: {meta.get('title','')}\nDesc: {meta.get('description','')}\nH1: {meta.get('h1_text','')}\nLang: {meta.get('lang','')}\nWords: {meta.get('word_count',0)}\nChecks:\n{checks}\nReturn JSON: {{"seo_report":"3 sentences","critical_issues":[""],"fixes":[{{"title":"","priority":"high|medium|low","category":"meta|content|structure|technical|schema","description":"","code_fix":""}}],"optimized_title":"","optimized_description":"","schema_markup":"JSON-LD code","keywords":["10"],"internal_link_suggestions":[""],"content_improvements":[""],"robots_txt":"proper robots.txt"}}"""
    return web.json_response(await ai_json(prompt))

async def handle_keyword_research(request):
    data = await request.json(); topic = data.get("topic","")
    prompt = f"""SEO keywords for: {topic}\nReturn JSON: {{"primary":["5 main"],"secondary":["10 supporting"],"long_tail":["10 phrases"],"local":["5 location-based"],"questions":["10 PAA questions"],"content_ideas":["5 titles"]}}"""
    return web.json_response(await ai_json(prompt))

async def handle_competitor(request):
    data = await request.json()
    u1,u2 = data.get("url1","").strip(), data.get("url2","").strip()
    if not u1.startswith("http"): u1 = "https://"+u1
    if not u2.startswith("http"): u2 = "https://"+u2
    results = {}
    async with aiohttp.ClientSession() as session:
        for label, u in [("site1",u1),("site2",u2)]:
            start = time.time()
            status, html, headers, final_url = await fetch_url(u, session)
            elapsed = time.time()-start
            results[label] = analyze_seo(u, status, html, headers, elapsed, final_url)
    prompt = f"""Compare SEO:\nSite 1: {u1} (Score {results['site1']['score']})\nSite 2: {u2} (Score {results['site2']['score']})\nReturn JSON: {{"winner":"url|tie","comparison":[{{"metric":"","site1":"","site2":"","winner":"site1|site2|tie"}}],"recommendations":["5 actions for weaker site"]}}"""
    comparison = await ai_json(prompt)
    comparison["site1"] = results["site1"]; comparison["site2"] = results["site2"]
    return web.json_response(comparison)

async def handle_content_optimize(request):
    data = await request.json()
    prompt = f"""Optimize content for: {data.get('url','')}\nContent:\n{data.get('html','')[:4000]}\nReturn JSON: {{"title_suggestions":["3"],"description_suggestions":["3"],"heading_suggestions":[""],"content_gaps":[""],"readability_score":"","improvement_priorities":["5"]}}"""
    return web.json_response(await ai_json(prompt))

async def handle_robots_generate(request):
    data = await request.json()
    result = await ask_gemini(f"Generate robots.txt for {data.get('url','')} (type: {data.get('type','general')}). Include sitemap. Return only robots.txt content.", 0.1, 1000)
    return web.json_response({"robots_txt": result.strip()})

async def handle_schema_generate(request):
    data = await request.json()
    prompt = f"""Generate JSON-LD for {data.get('url','')} type:{data.get('type','auto')}\nTitle: {data.get('meta',{}).get('title','')}\nReturn JSON: {{"schema_type":"","schema_jsonld":"code","explanation":"","additional_schemas":[""]}}"""
    return web.json_response(await ai_json(prompt))

async def handle_bulk_analyze(request):
    data = await request.json(); urls = data.get("urls",[]); results = []
    async with aiohttp.ClientSession() as session:
        for u in urls[:10]:
            u = u.strip()
            if not u.startswith("http"): u = "https://"+u
            start = time.time()
            status, html, headers, final_url = await fetch_url(u, session)
            elapsed = time.time()-start
            r = analyze_seo(u, status, html, headers, elapsed, final_url); r.pop("html",None); results.append(r)
    return web.json_response({"results": results})

async def handle_page_speed(request):
    data = await request.json(); url = data.get("url","").strip()
    if not url.startswith("http"): url = "https://"+url
    start = time.time()
    async with aiohttp.ClientSession() as session:
        status, html, headers, final_url = await fetch_url(url, session)
    elapsed = time.time()-start
    soup = BeautifulSoup(html,"lxml") if status==200 and html else None
    size = len(html) if html else 0
    r = {"url":url,"response_time_ms":round(elapsed*1000),"size_bytes":size,"size_kb":round(size/1024,1),"score":0,"metrics":[],"recommendations":[]}
    if not soup: return web.json_response(r)
    r["metrics"] = [
        {"name":"Response Time","value":f"{r['response_time_ms']}ms","status":"pass" if r['response_time_ms']<1000 else "warning" if r['response_time_ms']<3000 else "error"},
        {"name":"Page Size","value":f"{r['size_kb']}KB","status":"pass" if size<200000 else "warning" if size<500000 else "error"},
        {"name":"Scripts","value":str(len(soup.find_all("script"))),"status":"pass" if len(soup.find_all("script"))<10 else "warning"},
        {"name":"Stylesheets","value":str(len(soup.find_all("link",rel="stylesheet"))),"status":"pass"},
        {"name":"Images","value":str(len(soup.find_all("img"))),"status":"pass"},
        {"name":"Word Count","value":str(len(soup.get_text().split())),"status":"pass"},
    ]
    total = sum(1 for m in r["metrics"] if m["status"]=="pass")
    r["score"] = round(total/len(r["metrics"])*100) if r["metrics"] else 0
    return web.json_response(r)

async def handle_social_preview(request):
    data = await request.json(); meta = data.get("meta",{})
    og = meta.get("og",{}); tw = meta.get("twitter",{})
    return web.json_response({
        "google":{"title":meta.get("title","(no title)"),"description":meta.get("description","(no desc)"),"url":meta.get("canonical","")},
        "facebook":{"title":og.get("og:title",meta.get("title","")),"description":og.get("og:description",meta.get("description","")),"image":og.get("og:image","")},
        "twitter":{"title":tw.get("twitter:title",meta.get("title","")),"description":tw.get("twitter:description",meta.get("description","")),"image":tw.get("twitter:image","")}
    })

async def handle_pdf_report(request):
    data = await request.json()
    fixes = data.get("fixes", None)
    pdf_bytes = generate_pdf_report(data, fixes)
    return web.Response(body=pdf_bytes, content_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=seo-report-{data.get('url','').split('//')[-1][:30]}.pdf"})

async def handle_domain_authority(request):
    data = await request.json(); url = data.get("url","").strip()
    if not url.startswith("http"): url = "https://"+url
    async with aiohttp.ClientSession() as session:
        result = await check_domain_authority(url, session)
    return web.json_response(result)

async def handle_schedule_add(request):
    data = await request.json()
    sched = load_schedule()
    entry = {"url": data.get("url",""), "interval": data.get("interval","daily"), "created": datetime.now().isoformat(), "last_run": None, "enabled": True}
    sched["scans"].append(entry)
    save_schedule(sched)
    return web.json_response({"ok": True, "schedule": sched})

async def handle_schedule_list(request):
    return web.json_response(load_schedule())

async def handle_schedule_run(request):
    data = await request.json()
    url = data.get("url","").strip()
    if not url.startswith("http"): url = "https://"+url
    results = await run_scheduled_scan(url)
    return web.json_response(results)

async def handle_scan_history(request):
    scans = sorted(SCANS_DIR.glob("*.json"), reverse=True)[:20]
    history = []
    for s in scans:
        try:
            d = json.loads(s.read_text())
            history.append({"file": s.name, "url": d.get("url",""), "score": d.get("score",0), "timestamp": d.get("timestamp","")})
        except: pass
    return web.json_response({"scans": history})

async def handle_static(request):
    fp = Path("static") / request.match_info["filename"]
    if fp.exists(): return web.FileResponse(fp)
    return web.Response(status=404)


# ============================================================
# EMAIL + GSC SERVICES
# ============================================================
sys.path.insert(0, '/root/Documents/Codex/seoforge')
from email_service import load_config as email_cfg, save_config as email_save, send_email, build_report_html
from gsc_service import load_config as gsc_cfg, save_config as gsc_save, get_auth_url, exchange_code as gsc_exchange, get_site_summary, get_search_analytics, get_url_inspection, get_sitemaps

async def handle_email_config(request):
    data = await request.json()
    cfg = email_cfg()
    cfg.update({k: data[k] for k in ["smtp_host","smtp_port","smtp_user","smtp_pass","from_name","from_email"] if k in data})
    if data.get("test"):
        cfg["enabled"] = True
        email_save(cfg)
        test = send_email(cfg["from_email"], "SEOForge Test Email", "<h2 style='color:#00d4ff'>✅ Email configured!</h2><p>SMTP is working. Reports will be sent from this address.</p>")
        return web.json_response(test)
    cfg["enabled"] = bool(cfg.get("smtp_host"))
    email_save(cfg)
    return web.json_response({"ok": True, "config": cfg})

async def handle_email_get_config(request):
    cfg = email_cfg()
    safe = {k: v for k, v in cfg.items() if k != "smtp_pass"}
    safe["has_pass"] = bool(cfg.get("smtp_pass"))
    return web.json_response(safe)

async def handle_email_send_report(request):
    data = await request.json()
    to = data.get("to", "")
    results = data.get("results", {})
    fixes = data.get("fixes", None)
    if not to or not results:
        return web.json_response({"ok": False, "error": "Missing 'to' or 'results'"})
    html = build_report_html(results, fixes)
    # Generate PDF
    pdf_bytes = generate_pdf_report(results, fixes)
    subject = f"🔍 SEO Report: {results.get('url','')} — Score {results.get('score',0)}/100"
    result = send_email(to, subject, html, pdf_bytes, f"seo-report-{results.get('url','').split('//')[-1][:20]}.pdf")
    return web.json_response(result)

async def handle_email_schedule(request):
    data = await request.json()
    sched_file = Path("/root/Documents/Codex/seoforge/email_schedule.json")
    sched = json.loads(sched_file.read_text()) if sched_file.exists() else {"emails": []}
    sched["emails"].append({
        "to": data.get("to",""), "url": data.get("url",""),
        "interval": data.get("interval","weekly"),
        "created": datetime.now().isoformat(), "enabled": True
    })
    sched_file.write_text(json.dumps(sched, indent=2))
    return web.json_response({"ok": True, "schedule": sched})

# --- GSC ROUTES ---
async def handle_gsc_config(request):
    data = await request.json()
    cfg = gsc_cfg()
    cfg.update({k: data[k] for k in ["client_id","client_secret","redirect_uri","property_url"] if k in data})
    gsc_save(cfg)
    return web.json_response({"ok": True, "auth_url": get_auth_url()})

async def handle_gsc_get_config(request):
    cfg = gsc_cfg()
    token_file = Path("/root/Documents/Codex/seoforge/gsc_token.json")
    has_token = token_file.exists() and bool(json.loads(token_file.read_text()).get("access_token"))
    return web.json_response({"configured": cfg.get("configured", False) or bool(cfg.get("client_id")), "has_token": has_token, "property_url": cfg.get("property_url","")})

async def handle_gsc_callback(request):
    code = request.query.get("code")
    if not code:
        return web.Response(text="No code received", status=400)
    result = await gsc_exchange(code)
    if result.get("ok"):
        cfg = gsc_cfg()
        cfg["configured"] = True
        gsc_save(cfg)
        return web.Response(text="<h2 style='color:#22c55e'>✅ Google Search Console connected!</h2><p>You can close this tab and return to SEOForge.</p>", content_type="text/html")
    return web.Response(text=f"<h2>❌ Error: {result.get('error','Unknown')}</h2>", content_type="text/html")

async def handle_gsc_auth_url(request):
    url = get_auth_url()
    if not url:
        return web.json_response({"error": "GSC not configured. Set client_id and client_secret first."})
    return web.json_response({"auth_url": url})

async def handle_gsc_summary(request):
    result = await get_site_summary()
    return web.json_response(result)

async def handle_gsc_analytics(request):
    data = await request.json()
    days = data.get("days", 28)
    result = await get_search_analytics(days)
    return web.json_response(result)

async def handle_gsc_inspect(request):
    data = await request.json()
    url = data.get("url", "")
    result = await get_url_inspection(url)
    return web.json_response(result)

async def handle_gsc_sitemaps(request):
    result = await get_sitemaps()
    return web.json_response(result)

def main():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/analyze", handle_analyze)
    app.router.add_post("/api/ai-fixes", handle_ai_fixes)
    app.router.add_post("/api/keywords", handle_keyword_research)
    app.router.add_post("/api/competitor", handle_competitor)
    app.router.add_post("/api/content-optimize", handle_content_optimize)
    app.router.add_post("/api/robots-generate", handle_robots_generate)
    app.router.add_post("/api/schema-generate", handle_schema_generate)
    app.router.add_post("/api/bulk", handle_bulk_analyze)
    app.router.add_post("/api/page-speed", handle_page_speed)
    app.router.add_post("/api/social-preview", handle_social_preview)
    app.router.add_post("/api/pdf-report", handle_pdf_report)
    app.router.add_post("/api/domain-authority", handle_domain_authority)
    app.router.add_post("/api/schedule/add", handle_schedule_add)
    app.router.add_get("/api/schedule/list", handle_schedule_list)
    app.router.add_post("/api/schedule/run", handle_schedule_run)
    app.router.add_get("/api/scan-history", handle_scan_history)
    app.router.add_get("/static/{filename}", handle_static)

    app.router.add_post("/api/email/config", handle_email_config)
    app.router.add_get("/api/email/config", handle_email_get_config)
    app.router.add_post("/api/email/send-report", handle_email_send_report)
    app.router.add_post("/api/email/schedule", handle_email_schedule)
    app.router.add_get("/api/gsc/config", handle_gsc_get_config)
    app.router.add_post("/api/gsc/config", handle_gsc_config)
    app.router.add_get("/api/gsc/auth-url", handle_gsc_auth_url)
    app.router.add_get("/api/gsc/callback", handle_gsc_callback)
    app.router.add_post("/api/gsc/summary", handle_gsc_summary)
    app.router.add_post("/api/gsc/analytics", handle_gsc_analytics)
    app.router.add_post("/api/gsc/inspect", handle_gsc_inspect)
    app.router.add_get("/api/gsc/sitemaps", handle_gsc_sitemaps)
    print(f"\n{'='*60}\n  🔍 SEOForge v2.0 — Full SEO Platform\n  http://{HOST}:{PORT}\n  Gemini: {'✓' if GEMINI_KEY else '✗'}\n  PDF: ✓ | Scheduled: ✓ | Domain Auth: ✓\n  {len(app.router.routes())} routes\n{'='*60}\n")
    web.run_app(app, host=HOST, port=PORT, print=None)

if __name__ == "__main__":
    main()
