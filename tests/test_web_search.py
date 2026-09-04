"""
Tests for web_search — URL filtering, domain whitelist and SERP parsing.

All tests are offline: parsers run against sample HTML snippets, never the
network.
"""
from agent.tools import web_search as ws


# ── product-URL heuristic ─────────────────────────────────────

def test_rejects_blog_and_news_urls():
    assert ws._is_product_url("https://www.jd.com/bbs/help-123.html") is False
    assert ws._is_product_url("https://www.suning.com/news/abc") is False
    assert ws._is_product_url("https://www.smzdm.com/activity/huodong-1") is False
    assert ws._is_product_url("https://www.tmall.com/promotion/123") is False


def test_accepts_product_urls():
    assert ws._is_product_url("https://item.jd.com/100012043978.html") is True
    assert ws._is_product_url("https://detail.tmall.com/item.htm?id=123") is True
    assert ws._is_product_url("https://www.smzdm.com/p/1234567/") is True
    assert ws._is_product_url("https://www.vip.com/detail-12345.html") is True


def test_rejects_empty_and_bare_domain():
    assert ws._is_product_url("") is False
    assert ws._is_product_url("https://www.apple.com/iphone/") is False


# ── domestic domain hard filter ───────────────────────────────

def test_cn_ecommerce_domain_filter_accepts_domestic():
    assert ws._is_cn_ecommerce_url("https://item.jd.com/100012043978.html") is True
    assert ws._is_cn_ecommerce_url("https://detail.tmall.com/item.htm?id=123") is True
    assert ws._is_cn_ecommerce_url("https://www.smzdm.com/p/1234567/") is True
    assert ws._is_cn_ecommerce_url("https://mobile.pinduoduo.com/goods.html?goods_id=1") is True
    assert ws._is_cn_ecommerce_url("https://www.vip.com/detail-123.html") is True


def test_cn_ecommerce_domain_filter_rejects_foreign_and_lookalikes():
    assert ws._is_cn_ecommerce_url("") is False
    assert ws._is_cn_ecommerce_url("https://en.wikipedia.org/wiki/IPhone") is False
    assert ws._is_cn_ecommerce_url("https://www.amazon.com/dp/B0XXXX") is False
    assert ws._is_cn_ecommerce_url("https://www.notjd.com/item/1") is False
    assert ws._is_cn_ecommerce_url("https://jd.com.cn/item/1") is False
    assert ws._is_cn_ecommerce_url("https://detail.tmall.hk/hk/item.htm?id=1") is False


# ── URL fixing ─────────────────────────────────────────────────

def test_abs_url():
    assert ws._abs_url("//product.suning.com/1.html") == "https://product.suning.com/1.html"
    assert ws._abs_url("https://item.jd.com/1.html") == "https://item.jd.com/1.html"


# ── SERP parsers (offline, sample HTML) ───────────────────────

def test_parse_suning_html():
    html = (
        '<div id="product-list"><ul class="general">'
        '<li class="item-wrap"><div class="product-box">'
        '<a title="宣传语" href="//product.suning.com/0000000000/12451095561.html">'
        '<img alt="img"></a>'
        '<div class="title-selling-point">'
        '<a href="//product.suning.com/0000000000/12451095561.html">'
        "途沁快充数据线适用iPhone16</a></div>"
        "</div></li>"
        "</ul></div>"
    )
    items = ws._parse_suning_html(html)
    assert items == [
        ("途沁快充数据线适用iPhone16", "https://product.suning.com/0000000000/12451095561.html", "")
    ]


def test_parse_suning_html_bad_markup():
    assert ws._parse_suning_html("") == []
    assert ws._parse_suning_html("<html><body>no results</body></html>") == []


def test_parse_dangdang_html():
    html = (
        '<ul class="bigimg">'
        '<li>'
        '<a title="iPhone 16 手机壳 正品" href="//product.dangdang.com/12368946109.html">'
        '<img src="x.jpg"></a>'
        '<span class="search_now_price">¥214.17</span>'
        "</li>"
        "</ul>"
    )
    items = ws._parse_dangdang_html(html)
    assert items[0][0] == "iPhone 16 手机壳 正品"
    assert items[0][1] == "https://product.dangdang.com/12368946109.html"
    assert items[0][2] == "价格: ¥214.17"


def test_identify_source():
    assert ws._identify_source("https://item.jd.com/1.html") == "京东"
    assert ws._identify_source("https://product.suning.com/1.html") == "苏宁易购"
    assert ws._identify_source("https://www.apple.com.cn/iphone/") == "Web"
