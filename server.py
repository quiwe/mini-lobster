import re
import json
import asyncio
import threading
import anthropic
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import API_KEY, ANTHROPIC_BASE_URL, MODEL, AVAILABLE_MODELS
from tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS
from skills_manager import load_all_skills, install_skill, list_skills
from scheduler import (
    add_reminder,
    list_reminders,
    remove_reminder,
    start_conversation_summary,
    set_summary_callback,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

BASE_DIR = Path(__file__).parent
client = anthropic.Anthropic(api_key=API_KEY, base_url=ANTHROPIC_BASE_URL)

# ============================================================
# 全局状态
# ============================================================
_current_model = MODEL
_current_model_lock = threading.Lock()

# 每个会话的历史
_sessions: dict[str, list[dict]] = {}
_sessions_lock = threading.Lock()

# 每个会话的 stop 标志
_stop_flags: dict[str, bool] = {}
_stop_lock = threading.Lock()


def get_session(session_id: str) -> list[dict]:
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = []
        return _sessions[session_id]


def clear_session(session_id: str):
    with _sessions_lock:
        _sessions[session_id] = []
    with _stop_lock:
        _stop_flags[session_id] = False


def set_stop(session_id: str):
    with _stop_lock:
        _stop_flags[session_id] = True


def is_stopped(session_id: str) -> bool:
    with _stop_lock:
        return _stop_flags.get(session_id, False)


def reset_stop(session_id: str):
    with _stop_lock:
        _stop_flags[session_id] = False


def get_current_model() -> str:
    with _current_model_lock:
        return _current_model


# ============================================================
# 工具执行
# ============================================================
def handle_tool(tool_name: str, tool_input: dict) -> str:
    fn = TOOL_FUNCTIONS.get(tool_name)
    if not fn:
        return f"未知工具: {tool_name}"
    try:
        return fn(**tool_input)
    except TypeError as e:
        return f"工具参数错误: {e}"
    except Exception as e:
        return f"错误: {e}"


# ============================================================
# 系统提示
# ============================================================
def load_system_prompt() -> str:
    skills_section = load_all_skills()
    skills_block = f"\n\n## 已安装 Skills\n{skills_section}" if skills_section else ""
    return (
        Path(BASE_DIR / "agent.md").read_text(encoding="utf-8")
        + "\n\n"
        + Path(BASE_DIR / "user.md").read_text(encoding="utf-8")
        + skills_block
    )


def apply_model_writes(reply: str) -> str:
    agent_match = re.search(r"\[WRITE_AGENT\]\n(.*?)\n\[/WRITE_AGENT\]", reply, re.DOTALL)
    if agent_match:
        Path(BASE_DIR / "agent.md").write_text(agent_match.group(1).strip(), encoding="utf-8")

    user_match = re.search(r"\[WRITE_USER\]\n(.*?)\n\[/WRITE_USER\]", reply, re.DOTALL)
    if user_match:
        Path(BASE_DIR / "user.md").write_text(user_match.group(1).strip(), encoding="utf-8")

    skill_match = re.search(r"\[INSTALL_SKILL\]\n(.*?)\n\[/INSTALL_SKILL\]", reply, re.DOTALL)
    if skill_match:
        lines = skill_match.group(1).strip().split("\n", 1)
        if len(lines) == 2:
            install_skill(lines[0].strip(), lines[1].strip())

    reply = re.sub(r"\[WRITE_AGENT\]\n.*?\n\[/WRITE_AGENT\]\n?", "", reply, flags=re.DOTALL)
    reply = re.sub(r"\[WRITE_USER\]\n.*?\n\[/WRITE_USER\]\n?", "", reply, flags=re.DOTALL)
    reply = re.sub(r"\[INSTALL_SKILL\]\n.*?\n\[/INSTALL_SKILL\]\n?", "", reply, flags=re.DOTALL)
    return reply.strip()


# ============================================================
# 对话摘要
# ============================================================
def do_summary(history: list[dict]):
    recent = history[-50:]
    if len(recent) < 4:
        return

    system_prompt = load_system_prompt()
    summary_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "你是一个摘要助手。请总结以下对话，然后判断是否需要在未来某个时间点给用户发一条跟进消息。\n"
                "如果需要，给出：\n"
                "  - 消息内容（一句话，不超过50字）\n"
                "  - 发送时间（格式：YYYY-MM-DD HH:MM）\n"
                "如果不需要，回复「无需跟进」。\n\n"
                "对话：\n"
                + "\n".join(
                    f"[{m.get('role','')}] {str(m.get('content',''))[:200]}"
                    for m in recent
                )
            ),
        },
    ]
    try:
        resp = client.messages.create(model=get_current_model(), max_tokens=300, messages=summary_messages)
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        print(f"\n[📋 摘要] {text.strip()[:200]}")

        if "无需跟进" in text:
            return

        time_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text)
        if time_match:
            run_at = time_match.group(1)
            msg_match = re.search(r"[:：]\s*([^\n]{5,50})", text)
            msg = msg_match.group(1).strip() if msg_match else "来自 mini-lobster 的跟进"
            job_id = f"followup_{int(datetime.now().timestamp())}"
            add_reminder(job_id, msg, "date", run_at=run_at)
            print(f"[🔔 已调度] {run_at}: {msg}")
    except Exception as e:
        print(f"[摘要错误] {e}")


set_summary_callback(do_summary)


# ============================================================
# SSE 流式对话
# ============================================================
@app.get("/chat/{session_id}")
async def chat_stream(session_id: str, message: str):
    message = message.strip()

    # ---- 指令处理 ----
    if message.startswith("/new"):
        clear_session(session_id)
        reset_stop(session_id)
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": "✅ 已开启新会话，对话历史已清除。"})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    if message.startswith("/stop"):
        set_stop(session_id)
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": "⏹ 已终止当前会话。"})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    if message.startswith("/model"):
        parts = message.split(None, 1)
        if len(parts) < 2:
            current = get_current_model()
            names = [m["name"] for m in AVAILABLE_MODELS]
            async def ev_gen():
                yield {"event": "text", "data": json.dumps({"type": "final", "content": f"当前模型：{current}\n可用模型：{' / '.join(names)}"})}
                yield {"event": "done", "data": "{}"}
            return EventSourceResponse(ev_gen())
        target = parts[1].strip()
        # 模糊匹配
        matched = [m for m in AVAILABLE_MODELS if target.lower() in m["id"].lower() or target.lower() in m["name"].lower()]
        if not matched:
            async def ev_gen():
                yield {"event": "text", "data": json.dumps({"type": "final", "content": f"未找到匹配的模型：「{target}」\n可用：{' / '.join(m['id'] for m in AVAILABLE_MODELS)}"})}
                yield {"event": "done", "data": "{}"}
            return EventSourceResponse(ev_gen())
        with _current_model_lock:
            global _current_model
            _current_model = matched[0]["id"]
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": f"✅ 已切换模型：{matched[0]['name']}"})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    if message.startswith("/skills"):
        skills = list_skills()
        if not skills:
            text = "暂无已安装的 skill"
        else:
            text = "已安装 " + str(len(skills)) + " 个 skill：\n" + "\n".join(f"- {s['name']}" for s in skills)
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": text})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    if message.startswith("/schedules"):
        reminders = list_reminders()
        if not reminders:
            text = "暂无定时提醒"
        else:
            text = "定时提醒列表：\n" + "\n".join(
                f"- [{r['id']}] {r['message']} | {r['trigger']} | 下次: {r.get('next_run', 'N/A')}"
                for r in reminders
            )
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": text})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    if message.startswith("/help"):
        help_text = (
            "🦞 Mini-Lobster 指令列表：\n\n"
            "/new        - 开启新会话（清除历史）\n"
            "/stop       - 终止当前生成\n"
            "/model      - 显示当前模型\n"
            "/model <名> - 切换模型\n"
            "/skills     - 列出已安装的 skill\n"
            "/schedules  - 列出定时提醒\n"
            "/help       - 显示本帮助"
        )
        async def ev_gen():
            yield {"event": "text", "data": json.dumps({"type": "final", "content": help_text})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(ev_gen())

    # ---- 正常对话 ----
    reset_stop(session_id)
    model = get_current_model()
    history = get_session(session_id)
    system_prompt = load_system_prompt()

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    async def event_generator():
        nonlocal messages
        try:
            # Use streaming for first call — yields text incrementally
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            ) as stream:
                text_buffer = ""
                for event in stream:
                    if is_stopped(session_id):
                        break

                    # Text delta
                    if hasattr(event, "text"):
                        text_buffer += event.text
                        yield {"event": "text", "data": json.dumps({"type": "text", "content": event.text})}

                    # Tool call request
                    elif hasattr(event, "type") and event.type == "tool_use":
                        tool_name = event.name
                        tool_input = dict(event.input)
                        yield {"event": "tool_start", "data": json.dumps({"name": tool_name, "input": tool_input})}

                        if is_stopped(session_id):
                            break

                        result = handle_tool(tool_name, tool_input)
                        yield {"event": "tool_end", "data": json.dumps({"name": tool_name, "result": result[:500]})}

                        messages.append({"role": "assistant", "content": [{"type": "tool_use", "name": tool_name, "input": tool_input}]})
                        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": event.id, "content": result}]})

                        # Tool result → non-streaming call (recursive, use fresh stream)
                        if not is_stopped(session_id):
                            tool_resp = client.messages.create(
                                model=model, max_tokens=4096,
                                messages=messages, tools=TOOL_DEFINITIONS,
                            )
                            tool_text = "".join(b.text for b in tool_resp.content if hasattr(b, "text"))
                            tool_blocks = [b for b in tool_resp.content
                                          if hasattr(b, "type") and b.type == "tool_use"]

                            if tool_text:
                                text_buffer += tool_text
                                yield {"event": "text", "data": json.dumps({"type": "text", "content": tool_text})}

                            for tblock in tool_blocks:
                                tn = tblock.name
                                ti = dict(tblock.input)
                                yield {"event": "tool_start", "data": json.dumps({"name": tn, "input": ti})}
                                if is_stopped(session_id):
                                    break
                                res = handle_tool(tn, ti)
                                yield {"event": "tool_end", "data": json.dumps({"name": tn, "result": res[:500]})}
                                messages.append({"role": "assistant", "content": [{"type": "tool_use", "name": tn, "input": ti}]})
                                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tblock.id, "content": res}]})

                                if not is_stopped(session_id):
                                    next_resp = client.messages.create(
                                        model=model, max_tokens=4096,
                                        messages=messages, tools=TOOL_DEFINITIONS,
                                    )
                                    nt = "".join(b.text for b in next_resp.content if hasattr(b, "text"))
                                    if nt:
                                        text_buffer += nt
                                        yield {"event": "text", "data": json.dumps({"type": "text", "content": nt})}

                    # End of stream
                    elif hasattr(event, "type") and event.type == "message_stop":
                        final = apply_model_writes(text_buffer)
                        history.append({"role": "user", "content": message})
                        history.append({"role": "assistant", "content": final})
                        yield {"event": "text", "data": json.dumps({"type": "final", "content": final})}

        except asyncio.CancelledError:
            print(f"[SSE] Session {session_id} cancelled")
        finally:
            yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


# ============================================================
# REST API
# ============================================================
@app.get("/api/history/{session_id}")
def get_history(session_id: str):
    with _sessions_lock:
        return JSONResponse({"history": _sessions.get(session_id, [])})


@app.post("/api/clear/{session_id}")
def api_clear(session_id: str):
    clear_session(session_id)
    return {"ok": True}


@app.api_route("/api/models", methods=["GET", "POST"])
def api_models():
    return JSONResponse({
        "current": get_current_model(),
        "available": AVAILABLE_MODELS,
    })


@app.post("/api/model")
def api_set_model(data: dict):
    model_id = data.get("model_id")
    matched = [m for m in AVAILABLE_MODELS if m["id"] == model_id]
    if not matched:
        return JSONResponse({"ok": False, "error": "未知的模型"}, status_code=400)
    with _current_model_lock:
        global _current_model
        _current_model = model_id
    return {"ok": True, "current": model_id}


@app.api_route("/api/skills", methods=["GET", "POST"])
def api_skills():
    return JSONResponse({"skills": list_skills()})


@app.api_route("/api/schedules", methods=["GET", "POST"])
def api_schedules():
    return JSONResponse({"schedules": list_reminders()})


@app.post("/api/schedules")
def api_add_schedule(data: dict):
    job_id = data.get("job_id", f"manual_{int(datetime.now().timestamp())}")
    message = data.get("message", "")
    trigger = data.get("trigger", "date")
    run_at = data.get("run_at")
    minutes = data.get("minutes")
    hours = data.get("hours")
    days = data.get("days")
    kwargs = {}
    if run_at:
        kwargs["run_at"] = run_at
    if minutes:
        kwargs["minutes"] = minutes
    if hours:
        kwargs["hours"] = hours
    if days:
        kwargs["days"] = days
    task = add_reminder(job_id, message, trigger, **kwargs)
    return JSONResponse({"ok": True, "task": task})


@app.delete("/api/schedules/{job_id}")
def api_delete_schedule(job_id: str):
    try:
        remove_reminder(job_id)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.post("/api/summary/start")
def api_start_summary(interval_minutes: int = 30):
    result = start_conversation_summary(interval_minutes)
    return {"ok": True, "message": result}


@app.get("/ping")
def ping():
    return {"ok": True, "ip": "local"}


@app.get("/")
async def index():
    html = Path(BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


@app.get("/test")
async def test_page():
    html = Path(BASE_DIR / "test.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


if __name__ == "__main__":
    print("Mini-Lobster Web 上线: http://localhost:8765")
    uvicorn.run("server:app", host="0.0.0.0", port=8765, reload=False)
