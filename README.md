# Mini 龙虾 🦞

基于 MiniMax API 的 AI 助手，支持网页 UI、对话管理、技能扩展和定时任务。

## 功能特性

- **对话管理** — 多会话支持、上下文记忆、历史记录
- **技能系统** — 可扩展的技能插件（Code Review、Python Expert、Self-Improving 等）
- **定时任务** — 支持定时提醒和对话摘要
- **网页 UI** — 实时流式输出，美观的对话界面
- **工具调用** — 支持 Python 代码执行、文件操作等

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/mini-lobster.git
cd mini-lobster
```

### 2. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

如果项目根目录没有 `requirements.txt`，安装核心依赖：

```bash
pip install fastapi uvicorn sse-starlette anthropic
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的密钥：

```bash
MINILOBSTER_API_KEY=sk-cp-xxxxxxxxxxxxxxxxxxxx
```

获取 API Key：https://www.minimaxi.com/

### 4. 启动服务

```bash
./venv/bin/python server.py
```

服务启动后访问：**http://localhost:8765**

## 目录结构

```
mini-lobster/
├── server.py          # FastAPI 服务端
├── client.py          # 客户端（CLI 模式）
├── tools.py           # 工具函数定义
├── scheduler.py       # 定时任务
├── skills_manager.py  # 技能管理器
├── config.py          # 配置文件
├── skills/            # 技能目录
│   ├── registry.json  # 技能注册表
│   ├── code-review.md
│   ├── python-expert.md
│   └── self-improving-agent.md
├── static/            # 前端静态文件
├── templates/         # HTML 模板
├── agent.md           # Agent 角色定义
└── user.md            # 用户配置
```

## 技能系统

技能定义在 `skills/` 目录，通过 `skills/registry.json` 注册。

### 内置技能

| 技能 | 说明 |
|------|------|
| `code-review` | 代码审查 |
| `python-expert` | Python 专家 |
| `self-improving-agent` | 自我改进（记录错误和学习） |
| `openclaw-version-monitor` | OpenClaw 版本监控 |

### 安装新技能

1. 将技能文件放入 `skills/` 目录
2. 在 `skills/registry.json` 中注册
3. 重启服务

## 配置说明

### config.py

```python
import os

# MiniMax API Key（必填）
API_KEY = os.environ.get("MINILOBSTER_API_KEY", "")

# API 地址（默认使用 MiniMax 国内代理）
ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"

# 默认模型
MODEL = "claude-sonnet-4-6"

# 可用模型列表
AVAILABLE_MODELS = [
    {"id": "MiniMax-2.7-Flash", "name": "MiniMax-2.7-Flash"},
]
```

### 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `MINILOBSTER_API_KEY` | MiniMax API Key | 是 |

## API 接口

服务启动后提供以下接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 网页 UI |
| `/chat/{session_id}` | GET | 对话（SSE 流式） |
| `/api/history/{session_id}` | GET | 获取历史记录 |
| `/api/clear/{session_id}` | POST | 清空会话 |
| `/api/model` | POST | 切换模型 |
| `/api/skills` | GET | 获取技能列表 |
| `/api/schedules` | GET | 获取定时任务 |

### 对话参数

```
GET /chat/{session_id}?message=你好
```

返回 SSE 流式数据，格式：

```
event: text
data: {"type": "text", "content": "你好！"}

event: text
data: {"type": "final", "content": "你好，我是 Mini 龙虾！"}
```

## 开发

### 添加新工具

在 `tools.py` 中定义工具，参考现有工具格式：

```python
TOOL_DEFINITIONS = [...]
TOOL_FUNCTIONS = {...}
```

### 添加新技能

1. 在 `skills/` 创建 `YOUR_SKILL.md`
2. 在 `skills/registry.json` 中注册
3. 在 `skills_manager.py` 中加载

## License

MIT
