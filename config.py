import os
from pathlib import Path

# ── Load .env file ──────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ── LLM API (支持 Gemini 或 OpenAI 兼容 API，如 DeepSeek) ──
# 优先使用 LLM_API_KEY；向后兼容 GEMINI_API_KEY
def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v

LLM_API_KEY = _strip_quotes(os.environ.get("LLM_API_KEY", "") or os.environ.get("GEMINI_API_KEY", ""))
LLM_MODEL_ID = _strip_quotes(os.environ.get("LLM_MODEL_ID", "gemini-2.5-flash"))
LLM_BASE_URL = _strip_quotes(os.environ.get("LLM_BASE_URL", ""))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))

# ── Database ────────────────────────────────────────────────
DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "database", "shopsmart.db"
)

# ── Flask ───────────────────────────────────────────────────
def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
# Debug defaults to OFF for safety; enable explicitly via FLASK_DEBUG=true.
FLASK_DEBUG = _env_bool("FLASK_DEBUG", False)

# ── Auth / JWT ──────────────────────────────────────────────
def _load_or_create_jwt_secret() -> str:
    """JWT secret from env, or a persisted local one (gitignored) for dev."""
    secret = os.environ.get("JWT_SECRET", "").strip()
    if secret:
        return secret
    secret_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".jwt_secret")
    try:
        if os.path.isfile(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                existing = f.read().strip()
                if existing:
                    return existing
        import secrets as _secrets
        generated = _secrets.token_hex(32)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(generated)
        print("[WARNING] JWT_SECRET not set — generated a local one in .jwt_secret. "
              "Set JWT_SECRET env var for production!")
        return generated
    except Exception:
        import secrets as _secrets
        return _secrets.token_hex(32)


JWT_SECRET = _load_or_create_jwt_secret()
JWT_EXPIRY_SECONDS = int(os.environ.get("JWT_EXPIRY_SECONDS", str(7 * 24 * 3600)))
# bcrypt work factor; tests can lower via BCRYPT_ROUNDS=4 for speed.
try:
    BCRYPT_ROUNDS = max(4, min(int(os.environ.get("BCRYPT_ROUNDS", "12")), 15))
except ValueError:
    BCRYPT_ROUNDS = 12

# ── Notification Channels (real push) ───────────────────────
# Telegram bot — set both to enable price-drop alerts via Telegram.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

# SMTP email — set all to enable email alerts.
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER

# ── Rate limiting ───────────────────────────────────────────
# 保护高消耗端点（认证暴力破解、Gemini 费用、爬取）。
# 进程内令牌桶；运行多个 worker 时应使用共享存储。
RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", True)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


# (limit, per_seconds) 每个端点组的限制。
RATE_LIMIT_AUTH = (_env_int("RATE_LIMIT_AUTH", 10), 60.0)          # login/register
RATE_LIMIT_CHAT = (_env_int("RATE_LIMIT_CHAT", 20), 60.0)          # Gemini chat
RATE_LIMIT_SEARCH = (_env_int("RATE_LIMIT_SEARCH", 30), 60.0)      # search/scrape/compare
RATE_LIMIT_REFRESH = (_env_int("RATE_LIMIT_REFRESH", 6), 60.0)     # 手动刷新价格

# ── Agent session cache ─────────────────────────────────────
# Per-user chat agents are kept in memory. Bound the cache so idle/abandoned
# sessions are evicted instead of growing without limit.
AGENT_CACHE_MAX = _env_int("AGENT_CACHE_MAX", 200)
AGENT_CACHE_TTL = _env_int("AGENT_CACHE_TTL", 2 * 60 * 60)  # 2h

# ── CORS ────────────────────────────────────────────────────
# 允许调用 API 的 origin 列表，用逗号分隔。
# 前端由 Flask 同源服务，默认不开启 CORS。
# 仅当前端部署在不同域名时才设置。
# 例如: CORS_ORIGINS=https://shopsmart.example.com,https://www.shopsmart.example.com
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
]

# ── Agent ───────────────────────────────────────────────────
MAX_AGENT_ITERATIONS = 10

# ── Price Monitor (background auto-update) ──────────────────
# 启用/禁用自动更新关注产品的价格。
PRICE_MONITOR_ENABLED = _env_bool("PRICE_MONITOR_ENABLED", True)
# 扫描间隔时间（秒）。默认 6 小时。
PRICE_MONITOR_INTERVAL = int(os.environ.get("PRICE_MONITOR_INTERVAL", str(6 * 60 * 60)))
# 启动后等待多久才开始首次扫描（秒）。
PRICE_MONITOR_INITIAL_DELAY = int(os.environ.get("PRICE_MONITOR_INITIAL_DELAY", "60"))
# 每个产品爬取之间的间隔（秒），避免被屏蔽。
PRICE_MONITOR_PER_ITEM_DELAY = float(os.environ.get("PRICE_MONITOR_PER_ITEM_DELAY", "3"))
# 是否在 Web 进程中立即启动监控。
# 当运行多个 worker（gunicorn -w N）时，请设为 false 以避免每个 worker 生成一个
# 监控线程并重复扫描；应改为通过 `python monitor.py` 单独运行监控。
# 默认为 true，适用于开发环境/单进程（waitress 单进程仍然安全）。
PRICE_MONITOR_IN_PROCESS = _env_bool("PRICE_MONITOR_IN_PROCESS", True)
