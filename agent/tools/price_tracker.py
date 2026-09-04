"""
Tool: Price Tracker — 在数据库中关注产品价格。
"""
import json
import traceback
from database.models import Product, Notification
from agent.context import get_current_user_id


def track_price(product_name: str, url: str = None,
                current_price: float = None, target_price: float = None,
                source: str = None) -> str:
    """
    将产品添加到价格关注列表。

    Args:
        product_name: 产品名称
        url: 产品 URL（可选）
        current_price: 当前价格（可选）
        target_price: 目标价格，用于接收降价通知（可选）
        source: 来源（shopee, tiki, lazada...）（可选）

    Returns:
        确认已添加关注的 JSON 字符串
    """
    try:
        user_id = get_current_user_id()
        product_id = Product.create(
            name=product_name,
            url=url,
            source=source,
            current_price=current_price,
            target_price=target_price,
            user_id=user_id,
        )

        # Create notification
        price_str = f"{current_price:,.0f}₫" if current_price else "未知"
        Notification.create(
            title="📌 新产品已关注",
            message=f"已将 '{product_name}' 添加到关注列表。当前价格: {price_str}",
            product_id=product_id,
            ntype="tracking",
            user_id=user_id,
        )

        return json.dumps({
            "success": True,
            "product_id": product_id,
            "message": f"已将 '{product_name}' 添加到价格关注列表。",
            "product": {
                "id": product_id,
                "name": product_name,
                "url": url,
                "current_price": current_price,
                "target_price": target_price,
                "source": source
            }
        }, ensure_ascii=False)

    except Exception as e:
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "message": f"添加产品时出错: {str(e)}"
        }, ensure_ascii=False)


def get_tracked_products() -> str:
    """
    获取所有正在关注的产品列表。

    Returns:
        包含产品列表的 JSON 字符串
    """
    try:
        products = Product.get_all(user_id=get_current_user_id())
        return json.dumps({
            "success": True,
            "total": len(products),
            "products": products
        }, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "message": f"错误: {str(e)}"
        }, ensure_ascii=False)


TOOL_DEFINITIONS = [
    {
        "name": "track_price",
        "description": "将产品添加到价格关注列表。当用户想要关注产品价格以在降价时接收通知时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "需要关注的产品名称"
                },
                "url": {
                    "type": "string",
                    "description": "产品页面 URL（如果有）"
                },
                "current_price": {
                    "type": "number",
                    "description": "产品的当前价格 (VND)"
                },
                "target_price": {
                    "type": "number",
                    "description": "目标价格，降价到此价格时接收通知 (VND)"
                },
                "source": {
                    "type": "string",
                    "description": "销售来源（例如：'shopee', 'tiki', 'lazada', 'cellphones'）"
                }
            },
            "required": ["product_name"]
        }
    },
    {
        "name": "get_tracked_products",
        "description": "获取所有正在关注价格的产品列表。当用户想要查看已添加关注的产品时使用。",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]
