"""
Tool: Web Search — 只在中国主流电商平台搜索商品。

搜索源(全部并行,结果域名硬过滤,保证不返回外网链接):
  1. 苏宁易购站内搜索 (search.suning.com)     — 商品名 + 商品链接
  2. 当当站内搜索 (search.dangdang.com)       — 商品名 + 商品链接
  每个源默认抓取前 2 页(SEARCH_PAGES_PER_SOURCE)。

为什么只有这两个源?实测国内可直抓的站内搜索:
  - 苏宁易购 / 当当:服务端渲染(SSR),可直接解析 ✓
  - 京东 / 淘宝 / 天猫 / 拼多多 / 唯品会 / 华为 / 小米有品 / 国美 / 1688 / 网易严选
    等:全部有强反爬(空壳页面、JS 渲染、验证码、加密接口),直抓不可行 ✗
  - DuckDuckGo / Bing / 搜狗 / 360 等搜索引擎对中国电商商品页几乎无索引
    (实测 site:jd.com 返回空,搜狗/360 只有京东联盟广告),不适合做商品源 ✗
"""
import json
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from agent.tools.cache_util import TTLCache, RateLimiter


# Cache search results for a short while so repeated/identical queries don't
# re-hit the search sources, and rate-limit outbound calls to avoid being
# blocked by the sites.
_SEARCH_TTL = float(os.environ.get("SEARCH_CACHE_TTL", "300"))      # 5 minutes
_SEARCH_MAX_CALLS = int(os.environ.get("SEARCH_RATE_MAX_CALLS", "8"))
_SEARCH_PERIOD = float(os.environ.get("SEARCH_RATE_PERIOD", "60"))   # per 60s
# 单次搜索请求超时(秒),防止某个源卡死拖慢整体搜索。
_SEARCH_TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "8"))
# 每个源最多解析出的原始结果条数(避免页面解析出过多条目)。
_SEARCH_MAX_RAW_PER_SOURCE = int(os.environ.get("SEARCH_MAX_RAW_PER_SOURCE", "12"))
# 每个来源最多进入最终结果的数量(保证多平台结果多样性)。
_SEARCH_PER_SOURCE_MAX = int(os.environ.get("SEARCH_PER_SOURCE_MAX", "6"))
# 每个源抓取的搜索页数(翻页增加结果量)。
_SEARCH_PAGES_PER_SOURCE = int(os.environ.get("SEARCH_PAGES_PER_SOURCE", "2"))
# 最大下载字节数,防止异常响应撑爆内存。
_SEARCH_MAX_BYTES = 2 * 1024 * 1024

_search_cache = TTLCache(ttl=_SEARCH_TTL, max_entries=256)
_rate_limiter = RateLimiter(max_calls=_SEARCH_MAX_CALLS, period=_SEARCH_PERIOD)

# 统一的浏览器请求头(站内搜索页要求像浏览器)。
_HTTP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# Chinese e-commerce sites to search
ECOMMERCE_SITES = [
    {"name": "京东", "domain": "jd.com", "icon": "jd"},
    {"name": "淘宝", "domain": "taobao.com", "icon": "taobao"},
    {"name": "天猫", "domain": "tmall.com", "icon": "tmall"},
    {"name": "拼多多", "domain": "pinduoduo.com", "icon": "pdd"},
    {"name": "苏宁易购", "domain": "suning.com", "icon": "suning"},
    {"name": "什么值得买", "domain": "smzdm.com", "icon": "smzdm"},
    {"name": "唯品会", "domain": "vip.com", "icon": "vip"},
    {"name": "当当", "domain": "dangdang.com", "icon": "dangdang"},
]

# 全部国内电商域名 —— 结果硬过滤白名单,非白名单域名一律丢弃。
_CN_DOMAINS = tuple(site["domain"] for site in ECOMMERCE_SITES)

# Snippets to filter out (useless descriptions)
_BAD_SNIPPETS = [
    "we cannot provide a description for this page right now",
    "we can't provide a description for this page right now",
    "không thể cung cấp mô tả cho trang này",
]


def _clean_title(title: str) -> str:
    """Clean up product title from search results."""
    removals = [
        r'\s*[-|–]\s*京东\s*.*$',
        r'\s*[-|–]\s*淘宝\s*.*$',
        r'\s*[-|–]\s*天猫\s*.*$',
        r'\s*[-|–]\s*拼多多\s*.*$',
        r'\s*[-|–]\s*苏宁\s*.*$',
        r'\s*[-|–]\s*什么值得买\s*.*$',
        r'\s*[-|–]\s*唯品会\s*.*$',
        r'\s*[-|–]\s*当当\s*.*$',
        r'^\s*买\s+',
        r'\s*正品\s*$',
        r'\s*官方\s*$',
        r'\s*旗舰店\s*$',
        r'\s*好价\s*$',
        r'\s*优惠\s*$',
        r'\s*特价\s*$',
        r'\s*包邮\s*$',
        r'\s*[-|–]\s*$',  # Remove trailing dash
    ]
    for pattern in removals:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    return title.strip().rstrip('-–|').strip()


def _clean_snippet(snippet: str) -> str:
    """Clean snippet, remove useless descriptions."""
    if not snippet:
        return ""
    snippet_lower = snippet.lower().strip()
    for bad in _BAD_SNIPPETS:
        if bad in snippet_lower:
            return ""
    return snippet.strip()


def _identify_source(url: str) -> str:
    """Identify the e-commerce source from URL."""
    for site in ECOMMERCE_SITES:
        if site["domain"] in url:
            return site["name"]
    return "Web"


# Path fragments that signal a non-product page (blog/news/help/promo listing).
# These pages have no price, so scraping them always fails — drop them early.
_NON_PRODUCT_PATTERNS = [
    "/bbs/", "/blog/", "/news/", "/wiki/",
    "/promotion/", "/promo/", "/activity/", "/huodong/",
    "/review/", "/pingce/", "/shiyong/", "/baike/",
    "/help/", "/faq/", "/about/", "/contact/",
    "/tag/", "/topic/", "/video/", "/live/",
]

# Positive signals that a URL is a real product page on Chinese e-commerce sites.
_PRODUCT_URL_HINTS = [
    re.compile(r"/item/"),             # JD: .../item/123456.html
    re.compile(r"/detail/"),           # Tmall/淘宝: .../detail/item...
    re.compile(r"\.html$"),            # Generic product pages
    re.compile(r"/products?/"),        # generic /product/ or /products/
    re.compile(r"/p/"),                # short /p/ product path
    re.compile(r"id="),                # taobao: ...?id=123456
]


def _is_product_url(url: str) -> bool:
    """
    Heuristic filter: keep likely product pages, drop blog/news/promo pages.

    Search engines often return articles which have no price.
    Scraping those always fails, so we exclude them here.
    """
    if not url:
        return False
    low = url.lower()

    # Reject obvious non-product sections.
    for bad in _NON_PRODUCT_PATTERNS:
        if bad in low:
            return False

    # If we recognise a positive product-URL signal, keep it.
    for pat in _PRODUCT_URL_HINTS:
        if pat.search(low):
            return True

    # Otherwise: keep only if the path looks like a product slug (has a path
    # segment beyond the domain root, e.g. a long hyphenated name).
    try:
        path = re.sub(r"^https?://[^/]+", "", low).strip("/")
    except Exception:
        path = ""
    # A bare domain or a single short segment is unlikely to be a product page.
    return bool(path) and ("-" in path or "/" in path) and len(path) > 8


def _is_cn_ecommerce_url(url: str) -> bool:
    """Return True only when the URL belongs to a known Chinese e-commerce domain.

    Hard filter: anything not on the domestic whitelist (foreign sites,
    wikipedia, blogs, etc.) is dropped, so search results never contain
    out-of-China links.
    """
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == d or host.endswith("." + d) for d in _CN_DOMAINS)


def _http_get_text(url: str, params=None) -> str:
    """GET a hard-coded trusted search endpoint and return its decoded text.

    Only used for fixed, known domains (Suning / Dangdang search endpoints),
    never for user-supplied URLs, so no SSRF concern here.
    Returns "" on any failure.
    """
    try:
        resp = requests.get(
            url, params=params, headers=_HTTP_HEADERS,
            timeout=_SEARCH_TIMEOUT, stream=True,
        )
        resp.raise_for_status()
        chunks = []
        total = 0
        for chunk in resp.iter_content(65536):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total > _SEARCH_MAX_BYTES:
                resp.close()
                return ""
        resp.close()
        raw = b"".join(chunks)
        # Prefer requests' own encoding detection (honours Content-Type charset).
        if resp.encoding and resp.encoding.lower() != "iso-8859-1":
            return raw.decode(resp.encoding, errors="ignore")
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _abs_url(url: str) -> str:
    """Fix protocol-relative URLs (//host/...) by prefixing https:."""
    if url.startswith("//"):
        return "https:" + url
    return url


# ── Source parsers ─────────────────────────────────────────────

def _parse_suning_html(html: str) -> list:
    """Parse search.suning.com SERP html into [(title, url, snippet)] tuples."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    out = []
    for li in soup.select("li.item-wrap"):
        box = li.select_one("div.product-box") or li
        a = box.find("a", href=re.compile(r"product\.suning\.com"))
        if a is None:
            continue
        url = _abs_url(a.get("href", ""))
        # 商品名在 title-selling-point 链接的文本里;a[title] 常是宣传语。
        tlink = box.select_one("div.title-selling-point a")
        title = tlink.get_text(" ", strip=True) if tlink else ""
        if not title:
            title = (a.get("title") or "").strip()
        if title:
            out.append((title, url, ""))
    return out


def _parse_dangdang_html(html: str) -> list:
    """Parse search.dangdang.com SERP html into [(title, url, snippet)] tuples."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    out = []
    for li in soup.select("ul.bigimg li"):
        a = li.find("a", href=re.compile(r"product\.dangdang\.com"))
        if a is None:
            continue
        url = _abs_url(a.get("href", ""))
        title = a.get("title") or a.get_text(" ", strip=True)
        snippet = ""
        price_el = li.select_one(".price, .search_now_price")
        if price_el:
            snippet = "价格: " + price_el.get_text(" ", strip=True)
        if title:
            out.append((title.strip(), url, snippet))
    return out


def _suning_search(query: str, page: int = 1) -> list:
    """Search Suning's own site search; return [(title, url, snippet)] tuples."""
    url = "https://search.suning.com/" + quote(query) + "/"
    params = {"page": page} if page > 1 else None
    html = _http_get_text(url, params=params)
    if not html:
        return []
    return _parse_suning_html(html)[:_SEARCH_MAX_RAW_PER_SOURCE]


def _dangdang_search(query: str, page: int = 1) -> list:
    """Search Dangdang's own site search; return [(title, url, snippet)] tuples."""
    params = {"key": query, "act": "input"}
    if page > 1:
        params["page_index"] = page
    html = _http_get_text("http://search.dangdang.com/", params=params)
    if not html:
        return []
    return _parse_dangdang_html(html)[:_SEARCH_MAX_RAW_PER_SOURCE]


# ── Public entry ───────────────────────────────────────────────

def search_product(query: str, max_results: int = 10) -> str:
    """
    在中国主流电商平台搜索商品(苏宁易购、当当站内搜索)。
    返回商品列表，包含名称、链接、来源。

    Args:
        query: 要搜索的商品名称 (例如: "iPhone 16 128GB")
        max_results: 最大结果数量

    Returns:
        包含搜索结果的 JSON 字符串
    """
    query = (query or "").strip()
    if not query:
        return json.dumps({
            "success": False,
            "message": "请输入搜索关键词。",
            "results": []
        }, ensure_ascii=False)

    # 1) Serve from cache when possible (keyed by normalized query + max_results).
    cache_key = f"{query.lower()}::{max_results}"
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    # 2) Rate-limit outbound search calls to avoid being blocked.
    if not _rate_limiter.acquire():
        retry_after = round(_rate_limiter.time_until_next(), 1)
        # If we have a stale cached entry, prefer returning it over an error.
        stale = _search_cache.get(cache_key, allow_stale=True)
        if stale is not None:
            return stale
        return json.dumps({
            "success": False,
            "query": query,
            "rate_limited": True,
            "message": f"搜索频率过快。请在 {retry_after} 秒后重试。",
            "results": []
        }, ensure_ascii=False)

    result_json = _do_search(query, max_results)

    # 3) Only cache successful, non-empty responses.
    try:
        parsed = json.loads(result_json)
        if parsed.get("success") and parsed.get("total_results", 0) > 0:
            _search_cache.set(cache_key, result_json)
    except (json.JSONDecodeError, TypeError):
        pass

    return result_json


def _do_search(query: str, max_results: int = 10) -> str:
    """Run every source (and its pages) in parallel, hard-filter domestically."""
    pages = max(1, _SEARCH_PAGES_PER_SOURCE)

    def _jobs():
        jobs = []
        for page in range(1, pages + 1):
            jobs.append(("suning", lambda p=page: _suning_search(query, p)))
            jobs.append(("dangdang", lambda p=page: _dangdang_search(query, p)))
        return jobs

    all_results = []
    seen_urls = set()
    source_counts = {}

    def _collect(items):
        for title, url, snippet in items:
            url = _abs_url(url)
            if not url or url in seen_urls:
                continue
            # 硬过滤:非国内电商域名一律丢弃,绝不返回外网链接。
            if not _is_cn_ecommerce_url(url):
                continue
            source = _identify_source(url)
            clean_name = _clean_title(title or "")
            clean_snip = _clean_snippet(snippet or "")
            # 只保留国内电商平台的真实商品页,且每来源限量保证平台多样。
            if clean_name and source != "Web" and _is_product_url(url):
                if source_counts.get(source, 0) >= _SEARCH_PER_SOURCE_MAX:
                    continue
                source_counts[source] = source_counts.get(source, 0) + 1
                seen_urls.add(url)
                all_results.append({
                    "product_name": clean_name,
                    "url": url,
                    "source": source,
                    "snippet": clean_snip[:160] if clean_snip else None,
                    "is_product": True,
                })

    jobs = _jobs()
    try:
        # 并行执行所有来源的所有页,显著缩短搜索时间。
        # 每页配额 = 每源上限 ÷ 页数:让翻页真正贡献结果,而不是被第一页占满。
        per_page_limit = max(1, _SEARCH_PER_SOURCE_MAX // pages)
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            for _name, items in zip(jobs, pool.map(lambda j: j[1](), jobs)):
                _collect(items[:per_page_limit])
    except Exception:
        traceback.print_exc()

    final_results = all_results[:max_results]

    if not final_results:
        return json.dumps({
            "success": True,
            "query": query,
            "total_results": 0,
            "results": [],
            "message": f"未找到 '{query}' 的搜索结果。请尝试其他关键词。"
        }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "query": query,
        "total_results": len(final_results),
        "sources_found": list(dict.fromkeys(r["source"] for r in final_results)),
        "results": final_results,
    }, ensure_ascii=False)


# Tool definition for LLM function calling
TOOL_DEFINITION = {
    "name": "search_product",
    "description": "只在京东、淘宝、天猫、拼多多、苏宁易购、什么值得买、唯品会、当当等国内电商平台搜索商品。返回商品列表，包含购买链接和来源。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "商品名称或搜索关键词"
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量（默认 10）"
            }
        },
        "required": ["query"]
    }
}
