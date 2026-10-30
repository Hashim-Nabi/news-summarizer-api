"""REST API: GET /get?keyword=<text>  ->  first Ars Technica result, summarized.

Runs on port 7000. The home page (/) shows the student's registration number.
"""
import logging
import os
import time

from flask import Flask, jsonify, render_template_string, request

from scraper import ScrapeError, fetch_first_article
from summarizer import summarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

REGISTRATION = os.getenv("REGISTRATION", "FA23-BDS-057")
NEWS_SOURCE = os.getenv("NEWS_SOURCE", "Ars Technica")
STUDENT = os.getenv("STUDENT_NAME", "Hashim Nabi Sulehria")
CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))

app = Flask(__name__)
app.json.sort_keys = False  # keep the key order of the specification
_cache = {}  # keyword -> (timestamp, payload)

HOME = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>News Summarizer API - {{ reg }}</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;display:grid;place-items:center;min-height:100vh}
 main{background:#1e293b;border-radius:14px;padding:32px 40px;max-width:640px;box-shadow:0 10px 30px #0006}
 h1{margin:0 0 4px;font-size:1.5rem} .reg{font-size:2rem;font-weight:700;color:#38bdf8;margin:12px 0}
 code{background:#0f172a;padding:2px 8px;border-radius:6px;color:#fbbf24} form{margin-top:18px;display:flex;gap:8px}
 input{flex:1;padding:10px;border-radius:8px;border:1px solid #475569;background:#0f172a;color:#e2e8f0}
 button{padding:10px 18px;border:0;border-radius:8px;background:#38bdf8;color:#0f172a;font-weight:700;cursor:pointer}
 p{color:#94a3b8;line-height:1.5}
</style></head><body><main>
<h1>Selenium News Summarizer API</h1>
<div class="reg">{{ reg }}</div>
<p><b>{{ student }}</b><br>News source: <b>{{ news_source }}</b></p>
<p>Endpoint: <code>GET /get?keyword=&lt;keyword&gt;</code> &middot; Port <code>7000</code></p>
<form action="/get" method="get"><input name="keyword" placeholder="keyword, e.g. openai" required><button>Search</button></form>
</main></body></html>"""


def _payload(keyword="", url="", summary=""):
    return {
        "registration": REGISTRATION,
        "newssource": NEWS_SOURCE,
        "keyword": keyword,
        "url": url,
        "summary": summary,
    }


@app.get("/")
def home():
    return render_template_string(HOME, reg=REGISTRATION, student=STUDENT, news_source=NEWS_SOURCE)


@app.get("/health")
def health():
    return jsonify(status="ok", registration=REGISTRATION)


@app.get("/get")
def get_summary():
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        body = _payload()
        body["error"] = "query parameter 'keyword' is required"
        return jsonify(body), 400

    cached = _cache.get(keyword.lower())
    if cached and time.time() - cached[0] < CACHE_TTL:
        return jsonify(cached[1])

    try:
        article = fetch_first_article(keyword)
    except ScrapeError as exc:
        body = _payload(keyword)
        body["error"] = str(exc)
        return jsonify(body), 502

    body = _payload(keyword, article["url"], summarize(article["text"]))
    _cache[keyword.lower()] = (time.time(), body)
    return jsonify(body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "7000")))
