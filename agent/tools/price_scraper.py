"""
Tool: Price Scraper — 从产品 URL 提取价格。

价格提取策略（按优先级顺序，停在第一个有结果的方法）：
  1. 平台官方 API 适配器（如京东）—— 对于 JS 渲染页面最可靠。
  2. JSON-LD（schema.org Product）—— 标准，许多平台支持。
  3. Meta 标签（Open Graph / product:price）。
  4. <script> 中嵌入的 JSON —— 拯救使用 JavaScript 渲染的页面。
  5. 特定站点的 CSS 选择器。
  6. 通用 CSS 选择器。
"""
import json
import re
import traceback
from agent.tools import safe_http as requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2  # 总尝试次数 = 1 + MAX_RETRIES

# Reasonable bounds for a CNY product price. Anything outside is treated as noise
# (e.g. installment months, percentages, product codes, ratings).
MIN_VALID_PRICE = 0.01
MAX_VALID_PRICE = 9_999_999  # 约 1000 万人民币

# Site-specific price selectors (checked before generic ones).
# Note: Chinese e-commerce sites heavily use JS rendering, these selectors
# work on server-rendered sections. JSON-LD / embedded JSON are more reliable.
SITE_SELECTORS = {
    "jd.com": [".p-price", ".price", ".summary-price"],
    "suning.com": [".price-wrap", ".mainprice"],
    "smzdm.com": [".price", ".item_name"],
    "dangdang.com": [".price_l", ".price_d"],
}

# JSON keys that commonly hold a product's selling price across Chinese e-commerce
# embedded state. Ordered by preference (current/sale price before list price).
_PRICE_JSON_KEYS = [
    "price_min", "salePrice", "sale_price", "finalPrice", "final_price",
    "current_price", "currentPrice", "special_price", "specialPrice",
    "displayPrice", "display_price", "price", "lowPrice", "list_price",
    "price_max",
    "real_time_sale_price", "priceText", "price_info",
    "sku_price", "tradePrice", "itemPrice",
    "actual_price", "promotion_price",
]


def _parse_price(raw) -> float | None:
    """
    从字符串/数字中解析人民币金额，并验证合理范围。

    处理 '99.00', '1,234.56', '1.234' 等格式。
    注意：人民币使用 '.' 作为小数分隔符。
    """
    if raw is None:
        return None

    # Numeric input (from embedded JSON / API) — use directly.
    if isinstance(raw, (int, float)):
        price = float(raw)
        return price if MIN_VALID_PRICE <= price <= MAX_VALID_PRICE else None

    text = str(raw).strip()

    # Remove currency symbols and common suffixes
    text = re.sub(r'[¥￥]', '', text)
    text = re.sub(r'\s*元\s*', '', text)

    # Remove non-digit chars except dot and comma
    text = re.sub(r'[^\d.,]', '', text)

    if not text:
        return None

    # Chinese price format: 1,234.56 — comma is thousand sep, dot is decimal
    # Try to detect: if there's a dot followed by 1-2 digits at the end, it's a decimal
    has_decimal = bool(re.search(r'\.\d{1,2}$', text))

    if has_decimal:
        # Has decimal: remove commas (thousand separators), keep dot as decimal
        text = text.replace(',', '')
    else:
        # No decimal found — might be a VND-style format or integer price.
        # Remove both commas and dots (treat all as thousand separators).
        text = text.replace(',', '').replace('.', '')

    try:
        price = float(text)
    except (ValueError, TypeError):
        return None

    if MIN_VALID_PRICE <= price <= MAX_VALID_PRICE:
        return price
    return None


def _extract_price_from_text(text) -> float | None:
    """Try to extract a valid price from arbitrary text."""
    return _parse_price(text)


def _title_of(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    return title_tag.get_text().strip() if title_tag else ""


# ── Strategy 1: Official site APIs ──────────────────────────
# Chinese e-commerce sites heavily use anti-scraping and JS rendering,
# so official APIs are not publicly available. Strategy 1 is skipped.
# The scraper falls through to JSON-LD, meta tags, and embedded JSON.


_SITE_API_ADAPTERS = {}


def _extract_price_site_api(url: str) -> dict | None:
    for domain, adapter in _SITE_API_ADAPTERS.items():
        if domain in url:
            result = adapter(url)
            if result:
                return result
    return None


# ── Strategy 2: JSON-LD ─────────────────────────────────────
def _extract_price_jsonld(soup: BeautifulSoup) -> dict | None:
    """Extract price from JSON-LD structured data (most reliable in-page)."""
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") == "Product":
                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    raw_price = offers.get("price") or offers.get("lowPrice")
                    name = item.get("name", "")
                    if raw_price is not None:
                        price = _parse_price(raw_price)
                        if price:
                            return {"name": name, "price": price}
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            continue
    return None


# ── Strategy 3: Meta tags ───────────────────────────────────
def _extract_price_meta(soup: BeautifulSoup) -> dict | None:
    """Extract price from Open Graph / meta tags."""
    meta_props = ["product:price:amount", "og:price:amount"]
    for prop in meta_props:
        tag = soup.find("meta", {"property": prop})
        if tag and tag.get("content"):
            price = _parse_price(tag["content"])
            if price:
                og_title = soup.find("meta", {"property": "og:title"})
                name = og_title["content"] if og_title and og_title.get("content") else ""
                return {"name": name, "price": price}
    return None


# ── Strategy 4: Embedded JSON in <script> (JS-render sites) ─
def _walk_json_for_price(obj) -> float | None:
    """
    Recursively walk a decoded JSON structure looking for a price-bearing key.

    Tries preferred keys first across the whole tree, returning the first valid
    VND value found. This rescues sites that ship their state as JSON and render
    the price client-side (Shopee/Lazada/Tiki/etc.).
    """
    # Breadth-first collection of all dict nodes.
    nodes = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            nodes.append(cur)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)

    for key in _PRICE_JSON_KEYS:
        for node in nodes:
            if key in node:
                price = _parse_price(node[key])
                if price:
                    return price
    return None


def _extract_price_embedded_json(soup: BeautifulSoup) -> dict | None:
    """Scan <script> blocks for embedded JSON state and mine a price from it."""
    name = _title_of(soup)
    for script in soup.find_all("script"):
        raw = script.string
        if not raw or ("price" not in raw.lower()):
            continue

        # Whole-script JSON (e.g. <script type="application/json">…</script>).
        candidates = []
        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            candidates.append(stripped)

        # Inline assignments like `window.__DATA__ = {…};`.
        m = re.search(r"=\s*(\{.*\})\s*;?\s*$", stripped, re.DOTALL)
        if m:
            candidates.append(m.group(1))

        for cand in candidates:
            try:
                data = json.loads(cand)
            except (json.JSONDecodeError, ValueError):
                continue
            price = _walk_json_for_price(data)
            if price:
                return {"name": name, "price": price}
    return None


# ── Strategy 5: Site-specific selectors ─────────────────────
def _extract_price_site_specific(soup: BeautifulSoup, url: str) -> dict | None:
    """Extract price using selectors tuned for known Vietnamese e-commerce sites."""
    for domain, selectors in SITE_SELECTORS.items():
        if domain not in url:
            continue
        for selector in selectors:
            for el in soup.select(selector):
                price = _parse_price(el.get_text())
                if price:
                    return {"name": _title_of(soup), "price": price}
    return None


# ── Strategy 6: Generic selectors ───────────────────────────
def _extract_price_selectors(soup: BeautifulSoup) -> dict | None:
    """Extract price using common generic CSS selectors."""
    price_selectors = [
        "[itemprop='price']",
        "[class*='price'] [class*='current']",
        "[class*='product-price']",
        "[class*='price-current']",
        "[class*='sale-price']",
        "[class*='final-price']",
        ".price",
        "#price",
    ]
    for selector in price_selectors:
        for el in soup.select(selector):
            price = _parse_price(el.get("content", "")) or _parse_price(el.get_text())
            if price:
                return {"name": _title_of(soup), "price": price}
    return None


def _fetch(url: str):
    """GET a URL with a small retry/backoff. Returns Response or raises."""
    import time
    last_exc = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            # Only retry on transient errors (timeout / 429 / 5xx).
            transient = isinstance(e, requests.Timeout) or status in (429, 500, 502, 503, 504)
            if attempt < MAX_RETRIES and transient:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_exc


def scrape_price(url: str) -> str:
    """
    从 URL 提取产品价格。

    Args:
        url: 需要获取价格的产品页面 URL

    Returns:
        包含产品价格信息的 JSON 字符串
    """
    if not url or not re.match(r"^https?://", url.strip(), re.IGNORECASE):
        return json.dumps({
            "success": False,
            "url": url,
            "message": "URL 无效。URL 必须以 http:// 或 https:// 开头。"
        }, ensure_ascii=False)

    url = url.strip()

    # Strategy 1: official site API (works even for JS-render pages).
    try:
        api_result = _extract_price_site_api(url)
        if api_result:
            return json.dumps({
                "success": True,
                "url": url,
                "product_name": api_result["name"],
                "price": api_result["price"],
                "currency": "CNY",
                "method": "site_api",
            }, ensure_ascii=False)
    except Exception:
        traceback.print_exc()

    try:
        resp = _fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # For known stores we trust structured data + site-tuned selectors only.
        # The generic selector scans the whole page and frequently grabs an
        # accessory price or a "giảm 3 triệu" promo number, returning a wrong
        # (too-low) price — worse than returning nothing. So we only fall back
        # to generic selectors on UNKNOWN sites.
        is_known_site = any(domain in url for domain in SITE_SELECTORS)

        strategies = [
            ("jsonld", lambda: _extract_price_jsonld(soup)),
            ("meta", lambda: _extract_price_meta(soup)),
            ("embedded_json", lambda: _extract_price_embedded_json(soup)),
            ("site_css", lambda: _extract_price_site_specific(soup, url)),
        ]
        if not is_known_site:
            strategies.append(("generic_css", lambda: _extract_price_selectors(soup)))
        for method, fn in strategies:
            result = fn()
            if result:
                return json.dumps({
                    "success": True,
                    "url": url,
                    "product_name": result["name"],
                    "price": result["price"],
                    "currency": "CNY",
                    "method": method,
                }, ensure_ascii=False)

        title = _title_of(soup) or "Unknown"
        return json.dumps({
            "success": False,
            "url": url,
            "message": f"无法从此页面提取价格（页面可能使用 JavaScript 显示价格）。页面: {title}",
        }, ensure_ascii=False)

    except requests.Timeout:
        return json.dumps({
            "success": False,
            "url": url,
            "message": f"访问 URL 超时 (timeout {REQUEST_TIMEOUT}s)."
        }, ensure_ascii=False)
    except requests.RequestException as e:
        return json.dumps({
            "success": False,
            "url": url,
            "message": f"无法访问 URL: {str(e)}"
        }, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "url": url,
            "message": f"抓取价格时出错: {str(e)}"
        }, ensure_ascii=False)


TOOL_DEFINITION = {
    "name": "scrape_price",
    "description": "从特定 URL 提取产品价格。当需要从特定产品页面获取准确价格时使用。",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "产品页面的完整 URL（例如：'https://item.jd.com/123456.html'）"
            }
        },
        "required": ["url"]
    }
}
