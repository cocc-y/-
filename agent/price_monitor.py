"""
Price Monitor — 自动更新关注产品价格的后台服务。

在守护线程中运行，定期重新爬取有 URL 的产品价格，
写入价格历史，并在价格下降或达到目标时创建通知。
"""
import json
import threading
import time
import traceback

import config
from database.models import Product, Notification, User
from agent.tools.price_scraper import scrape_price
from agent import notify_channels


_monitor_thread = None
_stop_event = threading.Event()


def _format_price(value) -> str:
    try:
        return f"¥{float(value):,.2f}"
    except (TypeError, ValueError):
        return "未知"


def check_product(product: dict) -> dict | None:
    """
    重新爬取产品价格并在价格变化时更新。

    Returns:
        如果有更新则返回描述变化的 dict，否则返回 None。
    """
    url = product.get("url")
    if not url:
        return None

    raw = scrape_price(url)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not data.get("success") or data.get("price") is None:
        return None

    new_price = float(data["price"])
    old_price = product.get("current_price")

    # 没有变化 -> 跳过（仍视为扫描成功）。
    if old_price is not None and float(old_price) == new_price:
        return {"product_id": product["id"], "changed": False, "price": new_price}

    Product.update_price(product["id"], new_price, source=product.get("source"))

    change = {
        "product_id": product["id"],
        "name": product["name"],
        "changed": True,
        "old_price": old_price,
        "new_price": new_price,
    }

    # 创建适当的通知（保存到数据库 + 推送到真实渠道）。
    user_id = product.get("user_id")
    target = product.get("target_price")
    notif_title = notif_message = notif_type = None

    if target is not None and new_price <= float(target):
        notif_title = "🎯 价格已达到目标！"
        notif_message = (f"'{product['name']}' 现为 {_format_price(new_price)} "
                         f"(目标价 {_format_price(target)})。购买好时机！")
        notif_type = "deal"
    elif old_price is not None and new_price < float(old_price):
        notif_title = "📉 价格下降"
        notif_message = (f"'{product['name']}' 从 {_format_price(old_price)} "
                         f"降至 {_format_price(new_price)}。")
        notif_type = "alert"

    if notif_title:
        Notification.create(
            title=notif_title,
            message=notif_message,
            product_id=product["id"],
            ntype=notif_type,
            user_id=user_id,
        )
        # 推送真实通知（Telegram/邮箱），如果用户已配置。
        try:
            user = User.get_by_id(user_id) if user_id else None
            if user:
                full_msg = notif_message
                if product.get("url"):
                    full_msg = f"{notif_message}\n{product['url']}"
                notify_channels.deliver_to_user(user, notif_title, full_msg)
        except Exception:
            traceback.print_exc()

    return change


def run_once(user_id=None) -> int:
    """扫描一次关注的产品。返回更新的产品数量。

    如果传入了 ``user_id``，则只扫描该用户的产品（用于
    手动"刷新价格"按钮）。如果为 None，则扫描全部（用于后台任务）。
    """
    updated = 0
    try:
        products = Product.get_all(user_id=user_id)
    except Exception:
        traceback.print_exc()
        return 0

    for product in products:
        if _stop_event.is_set():
            break
        if not product.get("url"):
            continue
        try:
            result = check_product(product)
            if result and result.get("changed"):
                updated += 1
                print(f"  [PRICE] Updated '{product['name']}': "
                      f"{result.get('old_price')} -> {result.get('new_price')}")
        except Exception:
            traceback.print_exc()
        # 产品之间暂停以避免被限速。
        _stop_event.wait(config.PRICE_MONITOR_PER_ITEM_DELAY)

    return updated


def _monitor_loop():
    print(f"[OK] Price monitor started (interval={config.PRICE_MONITOR_INTERVAL}s).")
    # 启动后稍等片刻。
    if _stop_event.wait(config.PRICE_MONITOR_INITIAL_DELAY):
        return
    while not _stop_event.is_set():
        try:
            count = run_once()
            if count:
                print(f"[PRICE] Monitor cycle complete: {count} product(s) updated.")
        except Exception:
            traceback.print_exc()
        # 等待下一个周期（可被 stop() 中断）。
        if _stop_event.wait(config.PRICE_MONITOR_INTERVAL):
            break


def start_monitor():
    """启动后台监控（幂等）。"""
    global _monitor_thread
    if not config.PRICE_MONITOR_ENABLED:
        print("[INFO] Price monitor disabled (PRICE_MONITOR_ENABLED=false).")
        return
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _stop_event.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop, name="price-monitor", daemon=True
    )
    _monitor_thread.start()


def stop_monitor():
    """停止后台监控。"""
    _stop_event.set()
