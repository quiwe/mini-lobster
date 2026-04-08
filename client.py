import re
import threading
import anthropic
from config import API_KEY, ANTHROPIC_BASE_URL, MODEL
from pathlib import Path
from tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS
from skills_manager import load_all_skills, install_skill

client = anthropic.Anthropic(
    api_key=API_KEY,
    base_url=ANTHROPIC_BASE_URL,
)

BASE_DIR = Path(__file__).parent

_history_lock = threading.Lock()
_history: list[dict] = []


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


def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    fn = TOOL_FUNCTIONS.get(tool_name)
    if not fn:
        return f"未知工具: {tool_name}"
    try:
        return fn(**tool_input)
    except TypeError as e:
        return f"工具参数错误: {e}"


def _do_summary():
    """摘要回调：每30分钟执行一次，总结对话并判断是否需要定时推送"""
    try:
        # 取最近50条非system消息
        with _history_lock:
            recent = [m for m in _history if m.get("role") not in ("system",)]
        if len(recent) < 4:
            print("[摘要] 对话太少，跳过")
            return

        system_prompt = load_system_prompt()
        summary_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "你是一个摘要助手。请总结以下对话，然后判断：\n"
                    "1. 总结本次对话的核心内容和结论（1-3句）\n"
                    "2. 是否需要在未来某个时间点给用户发一条跟进消息？\n"
                    "   如果需要，给出：\n"
                    "   - 消息内容（一句话）\n"
                    "   - 建议的发送时间（格式：YYYY-MM-DD HH:MM）\n"
                    "   如果不需要，回覆「无需跟进」\n\n"
                    "对话内容：\n"
                    + "\n".join(
                        f"[{m.get('role','')}] {str(m.get('content',''))[:200]}"
                        for m in recent[-50:]
                    )
                ),
            },
        ]

        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=summary_messages,
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        print(f"\n[📋 对话摘要]\n{text.strip()}\n")

        # 判断是否要调度后续消息
        if "无需跟进" in text:
            return

        # 尝试解析时间和消息
        import re as _re
        time_match = _re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", text)
        if time_match:
            run_at = time_match.group(1)
            # 提取消息：取「消息内容：」后的句子
            msg_match = _re.search(r"[:：]\s*([^\n]{5,100})", text)
            msg = msg_match.group(1).strip() if msg_match else "来自 mini-lobster 的跟进消息"
            job_id = f"followup_{int(__import__('time').time())}"
            try:
                from scheduler import add_reminder
                add_reminder(job_id, msg, "date", run_at=run_at)
                print(f"[🔔 已调度跟进消息] {run_at}: {msg}")
            except Exception as e:
                print(f"[调度失败] {e}")

    except Exception as e:
        print(f"[摘要错误] {e}")


def _setup_summary_callback():
    from scheduler import set_summary_callback
    set_summary_callback(_do_summary)
    print("[摘要] 回调已注册")


def chat(message: str) -> str:
    global _history

    system_prompt = load_system_prompt()

    # 构建带 system 的消息列表用于 API
    messages_for_api = [{"role": "system", "content": system_prompt}]
    with _history_lock:
        messages_for_api.extend(_history)
    messages_for_api.append({"role": "user", "content": message})

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=messages_for_api,
        tools=TOOL_DEFINITIONS,
    )

    # 处理 tool use，直到没有 tool_use 块为止
    while True:
        text_parts = []
        tool_parts = []

        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_parts.append(block)

        if not tool_parts:
            break

        # 更新 messages_for_api 中的 tool 结果
        messages_for_api = [{"role": "system", "content": system_prompt}]
        with _history_lock:
            messages_for_api.extend(_history)
        messages_for_api.append({"role": "user", "content": message})
        messages_for_api.append({"role": "assistant", "content": response.content})

        for block in tool_parts:
            result = handle_tool_call(block.name, dict(block.input))
            messages_for_api.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }]
            })

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=messages_for_api,
            tools=TOOL_DEFINITIONS,
        )

    reply = "".join(text_parts)
    reply = apply_model_writes(reply)

    # 追加到历史（不含 system）
    with _history_lock:
        _history.append({"role": "user", "content": message})
        _history.append({"role": "assistant", "content": reply})

    return reply


if __name__ == "__main__":
    _setup_summary_callback()
    print("Mini-Lobster 上线了，输入 exit/quit 退出\n")
    while True:
        user_input = input("you: ")
        if user_input.lower() in ("exit", "quit"):
            break
        resp = chat(user_input)
        print(f"mini-lobster: {resp}\n")
