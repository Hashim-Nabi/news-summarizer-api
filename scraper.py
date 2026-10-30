"""Selenium + Chrome scraper for Ars Technica.

Finds the first search result for a keyword and returns the article text.
Strategy (first one that works wins):
  1. Ars Technica's own search page          (https://arstechnica.com/search/)
  2. DuckDuckGo  restricted with  site:arstechnica.com
  3. Bing        restricted with  site:arstechnica.com
  4. Ars Technica RSS feed (keyword match)    - last resort
"""
import base64
import html
import logging
import os
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

log = logging.getLogger("scraper")

SITE = "arstechnica.com"
FEED_URL = "https://feeds.arstechnica.com/arstechnica/index"
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
CHROMEDRIVER = os.getenv("CHROMEDRIVER", "/usr/local/bin/chromedriver")
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "40"))
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Only allow two Chrome instances at a time (keeps small servers healthy).
_gate = threading.BoundedSemaphore(int(os.getenv("MAX_BROWSERS", "2")))

ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?arstechnica\.com/[a-z0-9-]+/\d{4}/\d{2}/[a-z0-9\-_%.]+/?$", re.I
)


class ScrapeError(Exception):
    """Raised when no article could be found or read."""


# --------------------------------------------------------------------------- helpers
def is_article_url(url: str) -> bool:
    clean = (url or "").split("#")[0].split("?")[0]
    return bool(ARTICLE_RE.match(clean))


def first_article_url(urls):
    for url in urls:
        if is_article_url(url):
            return url.split("#")[0].split("?")[0]
    return None


def decode_ddg(href: str) -> str:
    """DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded url>."""
    if "uddg=" in href:
        target = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        return unquote(target)
    return "https:" + href if href.startswith("//") else href


def decode_bing(href: str) -> str:
    """Bing wraps results as bing.com/ck/a?...&u=a1<base64 url>."""
    if "bing.com/ck/a" in href:
        encoded = parse_qs(urlparse(href).query).get("u", [""])[0]
        if encoded.startswith("a1"):
            payload = encoded[2:]
            payload += "=" * (-len(payload) % 4)
            try:
                return base64.urlsafe_b64decode(payload).decode("utf-8")
            except Exception:  # noqa: BLE001
                return href
    return href


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))).strip()


# --------------------------------------------------------------------------- browser
def build_driver():
    options = Options()
    if os.path.exists(CHROME_BIN):
        options.binary_location = CHROME_BIN
    for arg in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1366,900",
        "--lang=en-US",
        "--disable-blink-features=AutomationControlled",
        f"--user-agent={USER_AGENT}",
    ):
        options.add_argument(arg)
    options.page_load_strategy = "eager"
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    service = Service(CHROMEDRIVER) if os.path.exists(CHROMEDRIVER) else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


def _open(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        log.warning("page load timed out for %s (continuing with what loaded)", url)


def _wait_links(driver, css, seconds, mapper=lambda h: h):
    """Poll the page until links matching `css` that look like articles appear."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        hrefs = driver.execute_script(
            "return Array.from(document.querySelectorAll(arguments[0])).map(a => a.href).filter(Boolean);", css
        )
        found = first_article_url(mapper(h) for h in hrefs)
        if found:
            return found
        time.sleep(1)
    return None


# --------------------------------------------------------------------------- search strategies
def _site_search(driver, keyword):
    _open(driver, f"https://{SITE}/search/?ie=UTF-8&q={quote_plus(keyword)}")
    return _wait_links(driver, "a.gs-title, .gsc-results a, [class*='search'] a, [class*='result'] a", 20)


def _ddg_search(driver, keyword):
    _open(driver, "https://html.duckduckgo.com/html/?q=" + quote_plus(f"site:{SITE} {keyword}"))
    return _wait_links(driver, "a.result__a", 8, decode_ddg)


def _bing_search(driver, keyword):
    _open(driver, "https://www.bing.com/search?q=" + quote_plus(f"site:{SITE} {keyword}"))
    return _wait_links(driver, "li.b_algo h2 a", 8, decode_bing)


def _rss_items():
    request = urllib.request.Request(FEED_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    content_tag = "{http://purl.org/rss/1.0/modules/content/}encoded"
    items = []
    for item in root.iter("item"):
        body = item.findtext(content_tag) or item.findtext("description") or ""
        items.append(
            {
                "title": item.findtext("title") or "",
                "url": (item.findtext("link") or "").strip(),
                "text": _strip_html(body),
            }
        )
    return items


def _rss_lookup(keyword):
    words = [w for w in re.findall(r"\w+", keyword.lower()) if len(w) > 1]
    try:
        items = _rss_items()
    except Exception as exc:  # noqa: BLE001
        log.warning("RSS lookup failed: %s", exc)
        return None
    for item in items:
        haystack = (item["title"] + " " + item["text"]).lower()
        if words and all(w in haystack for w in words):
            return item
    for item in items:
        haystack = (item["title"] + " " + item["text"]).lower()
        if any(w in haystack for w in words):
            return item
    return None


# --------------------------------------------------------------------------- article reading
_ARTICLE_JS = """
const selectors = ['article .article-content p', '.article-content p', 'article p', 'main p'];
const clean = nodes => nodes.map(p => p.innerText.trim())
    .filter(t => t.length > 40 && !/^Listing image/i.test(t));
const title = (document.querySelector('h1') || {}).innerText || document.title;
for (const s of selectors) {
  const paras = clean(Array.from(document.querySelectorAll(s)));
  if (paras.length >= 3) return {title: title, paras: paras};
}
return {title: title, paras: clean(Array.from(document.querySelectorAll('p')))};
"""


def _read_article(driver, url):
    _open(driver, url)
    deadline = time.time() + 12
    result = {"title": "", "paras": []}
    while time.time() < deadline:
        result = driver.execute_script(_ARTICLE_JS)
        if len(result["paras"]) >= 3:
            break
        time.sleep(1)
    return (result.get("title") or "").strip(), " ".join(result["paras"])


# --------------------------------------------------------------------------- public API
def fetch_first_article(keyword: str):
    """Return {'url', 'title', 'text'} for the first Ars Technica result for `keyword`."""
    keyword = (keyword or "").strip()
    if not keyword:
        raise ScrapeError("keyword is empty")

    with _gate:
        driver = None
        try:
            driver = build_driver()
            url, rss_item = None, None
            for name, strategy in (("site-search", _site_search), ("duckduckgo", _ddg_search), ("bing", _bing_search)):
                try:
                    url = strategy(driver, keyword)
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s failed: %s", name, exc)
                if url:
                    log.info("first result found via %s: %s", name, url)
                    break
            if not url:
                rss_item = _rss_lookup(keyword)
                if rss_item:
                    url = rss_item["url"]
                    log.info("first result found via rss: %s", url)
            if not url:
                raise ScrapeError(f"No Ars Technica result found for '{keyword}'")

            title, text = _read_article(driver, url)
            if len(text) < 300:  # page blocked / paywalled / not rendered: fall back to the feed text
                rss_item = rss_item or next((i for i in _safe_rss_items() if i["url"].rstrip("/") == url.rstrip("/")), None)
                if rss_item and len(rss_item["text"]) > len(text):
                    title, text = title or rss_item["title"], rss_item["text"]
            if len(text) < 80:
                raise ScrapeError(f"Could not read the article text at {url}")
            return {"url": url, "title": title, "text": text}
        except ScrapeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ScrapeError(f"Browser error: {exc}") from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    pass


def _safe_rss_items():
    try:
        return _rss_items()
    except Exception:  # noqa: BLE001
        return []
