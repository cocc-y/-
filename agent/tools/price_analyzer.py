"""
Tool: Price Analyzer — 分析产品价格趋势。
"""
import json
import re
import traceback
import unicodedata

from database.models import Product, PriceHistory
from agent.context import get_current_user_id


def _normalize(text: str) -> str:
    """Lowercase, strip Vietnamese accents, collapse whitespace for matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "d")
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _match_score(query: str, candidate: str) -> float:
    """
    Score how well `candidate` matches `query` (0..1).

    Combines exact/substring bonus with token (word) overlap, so e.g.
    "iPhone 16 Pro" ranks above "iPhone 16" when the query mentions "Pro".
    """
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0

    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if not q_tokens or not c_tokens:
        return 0.0

    overlap = q_tokens & c_tokens
    # Jaccard-like overlap weighted toward covering the query's tokens.
    coverage = len(overlap) / len(q_tokens)
    jaccard = len(overlap) / len(q_tokens | c_tokens)
    score = 0.6 * coverage + 0.4 * jaccard

    # Substring bonus — query appears verbatim in candidate (or vice versa).
    if q in c or c in q:
        score = max(score, 0.85)
    return score


def _rank_matches(query: str, products: list) -> list:
    """Return products sorted by descending match score (only score > 0)."""
    scored = [(p, _match_score(query, p.get("name", ""))) for p in products]
    scored = [(p, s) for p, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def analyze_price(product_name: str) -> str:
    """
    分析关注产品的价格趋势。

    Args:
        product_name: 需要分析的产品名称

    Returns:
        包含价格分析的 JSON 字符串
    """
    try:
        user_id = get_current_user_id()
        # Search the user's whole watchlist, then rank by match quality rather
        # than relying on a raw LIKE and taking the first row.
        candidates = Product.get_all(user_id=user_id)
        ranked = _rank_matches(product_name, candidates)

        if not ranked:
            return json.dumps({
                "success": False,
                "message": f"在关注列表中未找到产品 '{product_name}'。"
            }, ensure_ascii=False)

        best, best_score = ranked[0]

        # Ambiguous: several products match almost equally well → ask the user
        # to disambiguate instead of silently guessing.
        close = [p for p, s in ranked if best_score - s <= 0.1]
        if len(close) > 1 and best_score < 1.0:
            return json.dumps({
                "success": False,
                "ambiguous": True,
                "message": (f"找到 {len(close)} 个与 '{product_name}' 匹配的产品。"
                            "您想分析哪个产品？"),
                "matches": [{"id": p["id"], "name": p["name"],
                             "current_price": p.get("current_price")} for p in close],
            }, ensure_ascii=False)

        product = best
        stats = PriceHistory.get_stats(product["id"])
        history = PriceHistory.get_by_product(product["id"])

        # Calculate trend
        trend = "stable"
        change_percent = 0
        if len(history) >= 2:
            first_price = history[0]["price"]
            last_price = history[-1]["price"]
            if first_price > 0:
                change_percent = ((last_price - first_price) / first_price) * 100
                if change_percent > 2:
                    trend = "increasing"
                elif change_percent < -2:
                    trend = "decreasing"

        # Build analysis
        analysis = {
            "success": True,
            "product": {
                "id": product["id"],
                "name": product["name"],
                "current_price": product["current_price"],
                "target_price": product["target_price"],
            },
            "stats": {
                "min_price": stats["min_price"] if stats else None,
                "max_price": stats["max_price"] if stats else None,
                "avg_price": round(stats["avg_price"], 0) if stats and stats["avg_price"] else None,
                "total_records": stats["total_records"] if stats else 0,
            },
            "trend": trend,
            "change_percent": round(change_percent, 2),
            "recommendation": _get_recommendation(trend, change_percent, product),
            "history_count": len(history),
        }

        return json.dumps(analysis, ensure_ascii=False)

    except Exception as e:
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "message": f"分析错误: {str(e)}"
        }, ensure_ascii=False)


def _get_recommendation(trend: str, change_pct: float, product: dict) -> str:
    """Generate a buying recommendation."""
    if trend == "decreasing" and change_pct < -5:
        return "🟢 价格大幅下降。这可能是购买的好时机！"
    elif trend == "decreasing":
        return "🟡 价格呈小幅下降趋势。可以再等等。"
    elif trend == "increasing" and change_pct > 5:
        return "🔴 价格大幅上涨。如果需要，应尽早购买。"
    elif trend == "increasing":
        return "🟠 价格小幅上涨。建议尽早购买。"
    else:
        return "⚪ 价格稳定。没有大幅波动。"


TOOL_DEFINITION = {
    "name": "analyze_price",
    "description": "分析关注产品的价格趋势。包括最低/最高/平均价格、上涨/下跌趋势和购买建议。",
    "parameters": {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "需要分析的产品名称（必须是正在关注的产品）"
            }
        },
        "required": ["product_name"]
    }
}
