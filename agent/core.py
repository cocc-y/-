"""
ShopSmart AI Agent Core — ReAct loop with OpenAI-compatible LLM APIs (DeepSeek, Gemini, etc.).
"""
import json
import traceback

from openai import OpenAI

import config
from agent import context
from agent.prompts import SYSTEM_PROMPT
from agent.tools import web_search, price_scraper, price_tracker, price_analyzer, notifier


# ── Tool Registry ──────────────────────────────────────────
TOOL_FUNCTIONS = {
    "search_product": web_search.search_product,
    "scrape_price": price_scraper.scrape_price,
    "track_price": price_tracker.track_price,
    "get_tracked_products": price_tracker.get_tracked_products,
    "analyze_price": price_analyzer.analyze_price,
    "send_notification": notifier.send_notification,
}

# OpenAI-compatible tool definitions (auto-generated from function signatures).
def _build_tool_definitions() -> list:
    """Build OpenAI-compatible tool definitions from registered functions."""
    tools = []
    for name, fn in TOOL_FUNCTIONS.items():
        import inspect
        sig = inspect.signature(fn)
        properties = {}
        required = []
        for p_name, p_param in sig.parameters.items():
            if p_name == "kwargs":
                continue
            param_type = "string"
            if p_param.annotation is not None:
                if p_param.annotation in (int, float):
                    param_type = "number"
                elif p_param.annotation is bool:
                    param_type = "boolean"
            properties[p_name] = {"type": param_type, "description": p_name}
            if p_param.default is inspect.Parameter.empty:
                required.append(p_name)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Tool: {name}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


_TOOL_DEFINITIONS = _build_tool_definitions()


class ShopSmartAgent:
    """AI Shopping Agent powered by LLM with tool-use (OpenAI-compatible API)."""

    def __init__(self):
        if not config.LLM_API_KEY:
            raise ValueError(
                "LLM_API_KEY not configured! "
                "Set LLM_API_KEY (or GEMINI_API_KEY) in .env file."
            )

        client_kwargs = {"api_key": config.LLM_API_KEY}
        if config.LLM_BASE_URL:
            client_kwargs["base_url"] = config.LLM_BASE_URL

        self.client = OpenAI(**client_kwargs)
        self.model = config.LLM_MODEL_ID
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        print(f"[OK] ShopSmart Agent initialized (model={self.model}).")

    def reset_chat(self):
        """Reset the chat session."""
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def process_message(self, user_message: str, user_id=None) -> dict:
        """
        Process a user message through the ReAct loop.

        Args:
            user_message: the user's text.
            user_id: the authenticated user's id, made available to tools
                (e.g. track_price) via agent.context during this call.

        Returns:
            dict with keys: response (str), tool_calls (list), error (str|None)
        """
        tool_calls_log = []
        _ctx_token = context.set_current_user_id(user_id)

        try:
            self._messages.append({"role": "user", "content": user_message})

            # ReAct loop — keep processing until we get a text response.
            iterations = 0
            while iterations < config.MAX_AGENT_ITERATIONS:
                iterations += 1

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self._messages,
                    tools=_TOOL_DEFINITIONS if _TOOL_DEFINITIONS else None,
                )

                choice = response.choices[0]
                msg = choice.message

                if not msg.tool_calls:
                    # Text response — done.
                    final_text = msg.content or ""
                    self._messages.append({"role": "assistant", "content": final_text})
                    return {
                        "response": final_text,
                        "tool_calls": tool_calls_log,
                        "error": None,
                    }

                # Execute tool calls.
                self._messages.append({"role": "assistant", "content": msg.content or ""})
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        fn_args = {}

                    print(f"  [TOOL] {fn_name}({fn_args})")

                    tool_result = self._execute_tool(fn_name, fn_args)

                    tool_calls_log.append({
                        "tool": fn_name,
                        "args": fn_args,
                        "result_preview": tool_result[:200] + "..."
                                          if len(tool_result) > 200 else tool_result,
                    })

                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

            # Max iterations reached — return last assistant content.
            final_text = "抱歉，我无法在有限步骤内完成此请求。请尝试简化您的需求。"
            return {
                "response": final_text,
                "tool_calls": tool_calls_log,
                "error": "max_iterations_reached",
            }

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)

            if "API_KEY" in error_msg.upper() or "authentication" in error_msg.lower():
                return {
                    "response": "API Key 错误！请检查您的 LLM_API_KEY 配置。",
                    "tool_calls": tool_calls_log,
                    "error": error_msg,
                }

            if "quota" in error_msg.lower() or "429" in error_msg or "insufficient_quota" in error_msg:
                return {
                    "response": "API 配额已用完。请稍后重试或检查您的账户余额。",
                    "tool_calls": tool_calls_log,
                    "error": error_msg,
                }

            return {
                "response": f"发生错误: {error_msg}",
                "tool_calls": tool_calls_log,
                "error": error_msg,
            }
        finally:
            context.reset_current_user_id(_ctx_token)

    def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool by name with given arguments."""
        fn = TOOL_FUNCTIONS.get(name)
        if not fn:
            return json.dumps({
                "success": False,
                "message": f"Tool '{name}' does not exist."
            })

        try:
            return fn(**args)
        except TypeError as e:
            return json.dumps({
                "success": False,
                "message": f"Argument error for tool '{name}': {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "success": False,
                "message": f"Error executing tool '{name}': {str(e)}"
            })
