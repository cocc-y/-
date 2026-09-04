"""Tool: Notifier — 发送通知给用户。"""
import json
import traceback
from database.models import Notification


def send_notification(title: str, message: str, ntype: str = "info") -> str:
    """
    创建用户通知。

    Args:
        title: 通知标题
        message: 通知内容
        ntype: 通知类型 (info, deal, alert, tracking)

    Returns:
        确认信息的 JSON 字符串
    """
    try:
        nid = Notification.create(title=title, message=message, ntype=ntype)
        return json.dumps({
            "success": True,
            "notification_id": nid,
            "message": "通知发送成功。"
        }, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "message": f"发送通知失败: {str(e)}"
        }, ensure_ascii=False)


TOOL_DEFINITION = {
    "name": "send_notification",
    "description": "发送通知给用户。用于通知好 deal、价格下降或重要更新。",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "通知标题"
            },
            "message": {
                "type": "string",
                "description": "通知的详细内容"
            },
            "ntype": {
                "type": "string",
                "description": "通知类型: 'info', 'deal', 'alert', 'tracking'",
                "enum": ["info", "deal", "alert", "tracking"]
            }
        },
        "required": ["title", "message"]
    }
}
