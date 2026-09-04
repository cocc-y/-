# 🛒 ShopSmart AI Agent

> AI 智能购物助手:帮你找好价、全网比价、跨平台跟踪商品价格。

[English](README.md) | **简体中文**

![ShopSmart AI](https://img.shields.io/badge/AI-Shopping%20Agent-6C63FF?style=for-the-badge&logo=robot&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-4285F4?style=for-the-badge&logo=google&logoColor=white)

[![CI](https://github.com/tridpt/ShopSmart/actions/workflows/ci.yml/badge.svg)](https://github.com/tridpt/ShopSmart/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 功能特性

- **多用户账户** — 注册/登录使用 JWT 认证;每个用户的关注商品、聊天记录和通知互相隔离
- **AI 聊天界面** — 用自然语言搜索商品、对比价格
- **网页搜索工具** — 只在国内电商平台搜索商品和优惠(苏宁易购、当当站内搜索,支持多页),结果经过域名白名单硬过滤,不含外网链接
- **价格抓取** — 自动从商品页面提取价格(站点专属选择器 + 合理的价格区间校验)
- **价格跟踪** — 关注商品并持续监控价格变化
- **自动价格监控** — 后台任务定时重新抓取已关注商品的价格并记录历史
- **价格分析** — AI 驱动的趋势分析和购买建议
- **真实推送通知** — 降价或达到目标价时,站内提醒 + 可选的 Telegram / 邮件推送

## 技术栈

| 组件 | 技术 |
|------|------|
| AI 大脑 | 兼容 OpenAI 的大模型 API(默认 Google Gemini 2.5 Flash,`google-genai` SDK;支持通过 `LLM_BASE_URL` 接入 DeepSeek 等) |
| 后端 | Python + Flask |
| 认证 | JWT (PyJWT) + bcrypt |
| 数据库 | SQLite |
| 前端 | HTML + CSS + JavaScript |
| 图表 | Chart.js |
| 搜索 | 苏宁 / 当当站内搜索(只搜国内电商平台) |
| 推送渠道 | Telegram Bot API、SMTP 邮件 |
| 测试 | pytest |

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/YOUR_USERNAME/ShopSmart.git
cd ShopSmart

# 仅运行时依赖
pip install -r requirements.txt

# 或:开发 + 运行测试
pip install -r requirements-dev.txt
```

提示:建议使用虚拟环境(`python -m venv .venv`),让 ShopSmart 的固定版本依赖与其他项目隔离。

### 2. 设置 API Key

从 [Google AI Studio](https://aistudio.google.com/apikey) 免费获取 Gemini API Key;

也可以使用 DeepSeek 等 OpenAI 兼容 API(在 `.env` 中配置 `LLM_API_KEY`、`LLM_MODEL_ID`、`LLM_BASE_URL`)。

```bash
# Windows PowerShell
$env:GEMINI_API_KEY='your_api_key_here'

# Windows CMD
set GEMINI_API_KEY=your_api_key_here

# Linux/Mac
export GEMINI_API_KEY='your_api_key_here'
```

### 3. 运行

```bash
python app.py
```

浏览器打开 **http://127.0.0.1:5000**,注册账号即可开始使用。

`app.py` 是**开发**服务器(Werkzeug)。生产环境请参考[部署](#部署)。

## 配置

把 `.env.example` 复制为 `.env` 并填写所需项。只有 `LLM_API_KEY`(或 `GEMINI_API_KEY`)是必需的。

| 变量 | 用途 |
|------|------|
| `LLM_API_KEY` / `GEMINI_API_KEY` | 大模型 API Key(AI 聊天必需) |
| `LLM_MODEL_ID` | 模型 ID(默认 `gemini-2.5-flash`;DeepSeek 可设为 `deepseek-chat`) |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址(如 `https://api.deepseek.com/v1`) |
| `JWT_SECRET` | 签名认证令牌的密钥。**生产环境必须设置。** 开发环境会自动生成本地密钥。 |
| `FLASK_DEBUG` | `true` 开启调试模式(默认关闭) |
| `PRICE_MONITOR_ENABLED` | `false` 关闭后台价格监控 |
| `PRICE_MONITOR_INTERVAL` | 扫描周期(秒,默认 6 小时) |
| `PRICE_MONITOR_IN_PROCESS` | `false` 时 Web 进程不启动监控(多 worker 部署时配合独立的 `monitor.py` 使用) |
| `TELEGRAM_BOT_TOKEN` | 启用 Telegram 降价提醒 |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | 启用邮件降价提醒 |
| `SERVE_THREADS` | Waitress worker 线程数(默认 8) |
| `CORS_ORIGINS` | 允许调用 API 的来源列表(逗号分隔)。空 = 仅同源(默认)。仅当前端部署在独立域名时设置。 |
| `RATE_LIMIT_ENABLED` | `false` 关闭接口限流(默认开启) |
| `RATE_LIMIT_AUTH` / `RATE_LIMIT_CHAT` / `RATE_LIMIT_SEARCH` / `RATE_LIMIT_REFRESH` | 各端点组每 60 秒每客户端的最大请求数 |
| `SEARCH_TIMEOUT` | 单次搜索请求超时(秒,默认 `8`) |
| `SEARCH_PER_SOURCE_MAX` | 每个平台进入最终结果的最大数量(默认 `6`,保证多平台多样) |
| `SEARCH_MAX_RAW_PER_SOURCE` | 每个搜索源最多解析的原始结果数(默认 `12`) |
| `SEARCH_PAGES_PER_SOURCE` | 每个搜索源抓取的搜索页数(默认 `2`,翻页增加结果量) |

## 部署

`app.py` 是 Flask 开发服务器——不要在生产环境直接使用,请用真正的 WSGI 服务器。

### 单进程(waitress,跨平台,含 Windows)

```bash
python serve.py
# 或:  waitress-serve --host=0.0.0.0 --port=5000 wsgi:app
```

后台价格监控随进程启动——单进程场景没有问题。

### 多 worker(如 Linux 上的 gunicorn)

运行 N 个 worker 会启动 N 个监控线程,导致每个商品被重复抓取 N 次。为避免这种情况,请关闭进程内监控,单独运行一个监控进程:

```bash
# .env: PRICE_MONITOR_IN_PROCESS=false
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app   # Web worker
python monitor.py                        # 单独的监控进程
```

生产环境务必把 `JWT_SECRET` 设为固定值,保证重启后令牌仍然有效。

## 测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试运行在隔离的临时 SQLite 数据库上——不会触碰 `shopsmart.db`。

## 架构

```
ShopSmart/
├── app.py                  # Flask 服务器与 API 端点
├── config.py               # 配置
├── requirements.txt        # Python 依赖
├── agent/
│   ├── core.py             # AI Agent(ReAct 循环)
│   ├── prompts.py          # 系统提示词
│   └── tools/
│       ├── web_search.py   # 国内电商商品搜索(苏宁/当当站内 + 必应补充)
│       ├── price_scraper.py# 从 URL 提取价格
│       ├── price_tracker.py# 数据库价格跟踪
│       ├── price_analyzer.py# 价格趋势分析
│       └── notifier.py     # 通知系统
├── database/
│   ├── db.py               # SQLite 连接与建表
│   └── models.py           # 数据模型 (CRUD)
└── frontend/
    ├── index.html           # 单页应用
    ├── css/                 # 暗色主题 UI 样式
    └── js/                  # 聊天、看板、通知
```

## Agent 工具

| 工具 | 说明 |
|------|------|
| `search_product` | 只在国内电商平台搜索商品 |
| `scrape_price` | 从商品 URL 提取价格 |
| `track_price` | 把商品加入价格关注列表 |
| `analyze_price` | 分析价格趋势与购买建议 |
| `get_tracked_products` | 查看所有已关注商品 |
| `send_notification` | 创建降价提醒 |

## 许可证

MIT License
