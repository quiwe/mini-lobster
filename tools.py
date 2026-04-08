import json
import subprocess
import urllib.request
from pathlib import Path
from PIL import Image
from skills_manager import (
    install_skill,
    uninstall_skill,
    list_skills,
    load_all_skills,
    SKILLS_DIR,
)
from scheduler import (
    add_reminder,
    list_reminders,
    remove_reminder,
    pause_reminder,
    resume_reminder,
)

BASE_DIR = Path(__file__).parent

_PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


def _fetch(url: str) -> str:
    proxy_handler = urllib.request.ProxyHandler(_PROXIES)
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with opener.open(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[网络错误] {e}"


def tool_ls(path: str) -> str:
    """列出目录文件"""
    target = Path(path) if path else BASE_DIR
    if not target.exists():
        return f"路径不存在: {path}"
    if target.is_file():
        return f"{target.name} (文件)"
    items = []
    for p in sorted(target.iterdir()):
        items.append(f"{'📁' if p.is_dir() else '📄'} {p.name}")
    return "\n".join(items) if items else "目录为空"


def tool_read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """读取文件内容"""
    target = Path(path)
    if not target.exists():
        return f"文件不存在: {path}"
    if target.is_dir():
        return f"这是目录，不是文件: {path}"
    text = target.read_text(encoding="utf-8")
    lines = text.split("\n")
    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]
    return "\n".join(lines)


def tool_create_file(path: str, content: str) -> str:
    """创建新文件"""
    target = Path(path)
    if target.exists():
        return f"文件已存在: {path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已创建: {path}"


def tool_update_file(path: str, content: str) -> str:
    """更新/覆盖文件内容"""
    target = Path(path)
    if not target.exists():
        return f"文件不存在，先用 create_file 创建: {path}"
    target.write_text(content, encoding="utf-8")
    return f"已更新: {path}"


def tool_delete_file(path: str) -> str:
    """删除文件"""
    target = Path(path)
    if not target.exists():
        return f"文件不存在: {path}"
    target.unlink()
    return f"已删除: {path}"


def tool_read_image(path: str) -> str:
    """读取图片并返回描述"""
    target = Path(path)
    if not target.exists():
        return f"图片不存在: {path}"
    try:
        img = Image.open(target)
        info = f"图片: {target.name}\n格式: {img.format}\n尺寸: {img.width}x{img.height}"
        return info
    except Exception as e:
        return f"无法读取图片: {e}"


def tool_list_skills() -> str:
    """列出所有已安装的 skill"""
    skills = list_skills()
    if not skills:
        return "暂无已安装的 skill"
    lines = [f"- {s['name']}" for s in skills]
    return f"已安装 {len(skills)} 个 skill：\n" + "\n".join(lines)


def tool_install_skill(name: str, content: str) -> str:
    """安装一个新 skill（覆盖同名 skill）"""
    return install_skill(name, content)


def tool_uninstall_skill(name: str) -> str:
    """卸载一个 skill"""
    return uninstall_skill(name)


def tool_fetch_skill(url: str) -> str:
    """
    从 GitHub 或 ClawHub 网址抓取 skill 并自动安装。
    支持:
    - GitHub raw URL: https://raw.githubusercontent.com/...
    - GitHub blob URL: https://github.com/.../blob/...
    - ClawHub skill 页面: https://clawhub.ai/<owner>/<slug>
    - ClawHub API: https://clawhub.ai/api/v1/skills/<slug>
    """
    url = url.strip()
    if "clawhub.ai" in url or "clawhub.com" in url:
        return _fetch_clawhub(url)
    elif "github.com" in url or "raw.githubusercontent.com" in url:
        return _fetch_github(url)
    else:
        return f"[错误] 不支持的网址: {url}"


def _fetch_github(url: str) -> str:
    """从 GitHub 抓取 SKILL.md"""
    # raw.githubusercontent.com -> 直接用
    if "raw.githubusercontent.com" in url:
        raw_url = url
    # github.com/blob/ -> 转为 raw URL
    elif "/blob/" in url:
        raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    else:
        return "[错误] GitHub 网址格式不对，应包含 /blob/ 或 raw.githubusercontent.com"

    content = _fetch(raw_url)
    if content.startswith("[网络错误]"):
        return content

    # 从 URL 提取 skill 名称
    # 格式: .../<author>/<skill-name>/SKILL.md
    # 取路径倒数第二个目录名（即 skill 目录名）
    parts = [p for p in raw_url.split("/") if p]
    if len(parts) >= 2:
        # 最后一段是 SKILL.md，倒数第二段是 skill 目录名
        skill_name = parts[-2]
    else:
        skill_name = Path(parts[-1]).stem if parts else "github-skill"

    result = install_skill(skill_name, content)
    return f"[GitHub] {result}\n\n内容预览：\n{content[:300]}..."


def _fetch_clawhub(url: str) -> str:
    """从 ClawHub 抓取 skill"""
    # 从 API 获取 skill 元数据
    if "/api/v1/skills/" in url:
        slug = url.split("/api/v1/skills/")[-1].split("?")[0].split("/")[0]
    elif "/cdn/skills" in url:
        slug = url.split("/")[-2]
    else:
        # 从页面 URL 提取 slug: https://clawhub.ai/<owner>/<slug>
        # 或 https://clawhub.ai/<slug> (无 owner)
        segments = url.rstrip("/").split("/")
        slug = segments[-1]
        if slug in ("", "skills", "cdn"):
            slug = segments[-2]

    # 获取 skill 元数据（含 owner）
    meta_url = f"https://clawhub.ai/api/v1/skills/{slug}"
    meta_raw = _fetch(meta_url)
    if meta_raw.startswith("[网络错误]"):
        return meta_raw

    try:
        meta = json.loads(meta_raw)
    except Exception:
        return f"[错误] 无法解析 ClawHub 返回: {meta_raw[:200]}"

    skill_info = meta.get("skill", {})
    owner = (meta.get("owner", {}) or {}).get("handle", "unknown")
    display_name = skill_info.get("displayName", slug)

    # 获取完整 skill 内容（从 HTML 页面）
    page_url = f"https://clawhub.ai/{owner}/{slug}"
    page_html = _fetch(page_url)
    if page_html.startswith("[网络错误]"):
        return page_html

    # 从 HTML 中提取 readme（嵌入在 initialData JSON 中）
    readme = _extract_readme_from_html(page_html)
    if not readme:
        return f"[错误] 无法从页面提取 skill 内容: {page_url}"

    # 同时提取 allowed-tools 和 description 头部
    frontmatter = ""
    desc = skill_info.get("summary", "")
    if desc:
        frontmatter += f"description: {desc}\n"

    # 尝试从 readme 中提取 frontmatter
    if readme.startswith("---"):
        parts = readme.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1] + "\n"
            readme = parts[2].strip()

    content = f"---\nname: {display_name}\n/frontmatter\n\n{readme}".replace("/frontmatter", frontmatter)

    result = install_skill(slug, content)
    return f"[ClawHub] {result} (by @{owner})\n\n描述: {desc}\n\n内容预览：\n{readme[:300]}..."


def _extract_readme_from_html(html: str) -> str:
    """从 ClawHub HTML 页面中提取 readme 内容"""
    import re

    # ClawHub 使用 readme:"..." 格式（无引号前缀，但内容经过 JSON 转义）
    match = re.search(r'readme:"((?:[^"\\]|\\.)*)"', html)
    if match:
        raw = match.group(1)
        raw = raw.encode().decode("unicode_escape", errors="replace")
        return raw.strip()

    return ""


def tool_learn_skill(path: str, name: str | None = None) -> str:
    """从本地 .md 文件学习并安装为 skill"""
    target = Path(path)
    if not target.exists():
        return f"文件不存在: {path}"
    if target.suffix.lower() not in (".md", ".markdown"):
        return f"只支持 .md / .markdown 文件: {path}"

    content = target.read_text(encoding="utf-8")
    if not content.strip():
        return f"文件内容为空: {path}"

    # 没有提供 name 则用文件名（去掉后缀）
    if not name:
        name = target.stem

    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return "Skill 名称无效，只允许字母、数字、-、_"

    result = install_skill(safe_name, content)
    return f"{result}\n\n内容预览：\n{content[:300]}..."


def _reminder_callback(reminder_id: str, message: str):
    """定时提醒触发时的回调，打印到终端"""
    print(f"\n[🔔 定时提醒 {reminder_id}] {message}\n")


def tool_schedule_reminder(
    job_id: str,
    message: str,
    trigger: str,
    run_at: str | None = None,
    seconds: int | None = None,
    minutes: int | None = None,
    hours: int | None = None,
    days: int | None = None,
    cron_second: str | None = None,
    cron_minute: str | None = None,
    cron_hour: str | None = None,
    cron_day: str | None = None,
    cron_month: str | None = None,
    cron_day_of_week: str | None = None,
) -> str:
    """
    添加定时提醒，支持一次性、间隔重复、Cron 三种触发方式。

    示例 - 一次性提醒（明天 9:00）：
      trigger="date", run_at="2026-04-09 09:00:00"

    示例 - 每 30 分钟重复：
      trigger="interval", minutes=30

    示例 - 每天 9:00 执行：
      trigger="cron", cron_hour="9", cron_minute="0"

    示例 - 每周一早上 8:00：
      trigger="cron", cron_hour="8", cron_minute="0", cron_day_of_week="mon"

    示例 - 工作日每天 18:00：
      trigger="cron", cron_hour="18", cron_minute="0", cron_day_of_week="mon-fri"
    """
    if trigger not in ("date", "interval", "cron"):
        return f"[错误] trigger 必须是 date / interval / cron，当前: {trigger}"

    params = {}
    if trigger == "date":
        if not run_at:
            return "[错误] date 触发需要 run_at 参数（格式：YYYY-MM-DD HH:MM:SS）"
        params["run_at"] = run_at
    elif trigger == "interval":
        if not any([seconds, minutes, hours, days]):
            return "[错误] interval 触发需要至少一个时间参数"
        params = {k: v for k, v in {
            "seconds": seconds, "minutes": minutes, "hours": hours, "days": days
        }.items() if v is not None}
    elif trigger == "cron":
        params = {k: v for k, v in {
            "second": cron_second, "minute": cron_minute, "hour": cron_hour,
            "day": cron_day, "month": cron_month, "day_of_week": cron_day_of_week,
        }.items() if v is not None}

    # 注册回调
    from scheduler import add_callback
    add_callback(_reminder_callback)

    task = add_reminder(job_id, message, trigger, **params)
    next_run = task.get("next_run", "（仅执行一次）")
    return (
        f"✅ 定时提醒已添加！\n"
        f"  任务 ID: {job_id}\n"
        f"  消息: {message}\n"
        f"  触发方式: {trigger}\n"
        f"  下次执行: {next_run}"
    )


def tool_list_schedules() -> str:
    """列出所有定时提醒"""
    reminders = list_reminders()
    if not reminders:
        return "暂无定时提醒"
    lines = []
    for r in reminders:
        lines.append(
            f"- [{r['id']}] {r['message']} | {r['trigger']} | "
            f"下次: {r.get('next_run', 'N/A') or 'N/A'}"
        )
    return "📋 定时提醒列表：\n" + "\n".join(lines)


def tool_remove_schedule(job_id: str) -> str:
    """删除指定定时提醒"""
    return remove_reminder(job_id)


def tool_pause_schedule(job_id: str) -> str:
    """暂停指定定时提醒"""
    return pause_reminder(job_id)


def tool_resume_schedule(job_id: str) -> str:
    """恢复已暂停的定时提醒"""
    return resume_reminder(job_id)


def tool_start_summary(interval_minutes: int = 30) -> str:
    """启动定期对话摘要任务。每隔指定分钟数触发一次，mini-lobster 会自动总结对话并判断是否需要定时发消息给用户。"""
    from scheduler import start_conversation_summary
    return start_conversation_summary(interval_minutes)


def tool_run_python(code: str) -> str:
    """执行 Python 代码，返回 stdout+stderr"""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = result.stdout.strip() if result.stdout else ""
        err = result.stderr.strip() if result.stderr else ""
        if err and not out:
            return f"[错误]\n{err}"
        if err and out:
            return f"[输出]\n{out}\n[错误]\n{err}"
        return out if out else "[执行完成，无输出]"
    except subprocess.TimeoutExpired:
        return "[错误] 代码执行超时（30秒）"
    except Exception as e:
        return f"[错误] {e}"


def tool_run_javascript(code: str) -> str:
    """执行 JavaScript 代码"""
    try:
        result = subprocess.run(
            ["node", "-e", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = result.stdout.strip() if result.stdout else ""
        err = result.stderr.strip() if result.stderr else ""
        if err and not out:
            return f"[错误]\n{err}"
        if err and out:
            return f"[输出]\n{out}\n[错误]\n{err}"
        return out if out else "[执行完成，无输出]"
    except FileNotFoundError:
        return "[错误] node 未安装"
    except subprocess.TimeoutExpired:
        return "[错误] 代码执行超时（30秒）"
    except Exception as e:
        return f"[错误] {e}"


TOOL_FUNCTIONS = {
    "ls": tool_ls,
    "read_file": tool_read_file,
    "create_file": tool_create_file,
    "update_file": tool_update_file,
    "delete_file": tool_delete_file,
    "read_image": tool_read_image,
    "list_skills": tool_list_skills,
    "install_skill": tool_install_skill,
    "uninstall_skill": tool_uninstall_skill,
    "fetch_skill": tool_fetch_skill,
    "learn_skill": tool_learn_skill,
    "schedule_reminder": tool_schedule_reminder,
    "list_schedules": tool_list_schedules,
    "remove_schedule": tool_remove_schedule,
    "pause_schedule": tool_pause_schedule,
    "resume_schedule": tool_resume_schedule,
    "start_summary": tool_start_summary,
    "run_python": tool_run_python,
    "run_javascript": tool_run_javascript,
}

TOOL_DEFINITIONS = [
    {
        "name": "ls",
        "description": "列出指定目录下的文件和子目录。不传参数时默认列出项目根目录。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "目录路径，默认项目根目录"}},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "读取文件内容。适合读取代码、文本、配置等文件。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "offset": {"type": "integer", "description": "跳过的行数，默认0"},
                "limit": {"type": "integer", "description": "最多读取行数，默认0表示不限制"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_file",
        "description": "创建新文件。如果文件已存在会报错。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "update_file",
        "description": "更新/覆盖文件内容。文件不存在时先报错。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "新的文件内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": "删除文件。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "文件路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_image",
        "description": "读取图片文件，返回图片基本信息。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "图片路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_skills",
        "description": "列出所有已安装的 skill。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "install_skill",
        "description": "安装一个新 skill（同名 skill 会被覆盖）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill 名称（字母/数字/-/_）"},
                "content": {"type": "string", "description": "Skill 的完整指令内容"},
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "uninstall_skill",
        "description": "卸载一个已安装的 skill。",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill 名称"}},
            "required": ["name"],
        },
    },
    {
        "name": "fetch_skill",
        "description": "从 GitHub 或 ClawHub 网址抓取 skill 并自动安装。传入 skill 页面的完整 URL。",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Skill 网址（GitHub raw/blob URL 或 ClawHub skill 页面 URL）"}},
            "required": ["url"],
        },
    },
    {
        "name": "learn_skill",
        "description": "从本地 .md 文件学习并安装为 skill。可指定名称，不指定则用文件名。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "本地 .md 文件路径"},
                "name": {"type": "string", "description": "Skill 名称（可选，不填则用文件名）"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_python",
        "description": "执行 Python 代码，返回执行结果。",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python 代码"}},
            "required": ["code"],
        },
    },
    {
        "name": "run_javascript",
        "description": "执行 JavaScript 代码，返回执行结果。",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "JavaScript 代码"}},
            "required": ["code"],
        },
    },
    {
        "name": "schedule_reminder",
        "description": "添加定时提醒，支持一次性（date）、间隔重复（interval）、Cron 三种触发方式。",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "任务唯一 ID"},
                "message": {"type": "string", "description": "提醒消息内容"},
                "trigger": {"type": "string", "description": "触发类型：date / interval / cron"},
                "run_at": {"type": "string", "description": "date 触发时的时间（YYYY-MM-DD HH:MM:SS）"},
                "seconds": {"type": "integer", "description": "interval：间隔秒数"},
                "minutes": {"type": "integer", "description": "interval：间隔分钟数"},
                "hours": {"type": "integer", "description": "interval：间隔小时数"},
                "days": {"type": "integer", "description": "interval：间隔天数"},
                "cron_second": {"type": "string", "description": "cron：秒（可选，0-59）"},
                "cron_minute": {"type": "string", "description": "cron：分钟（可选，0-59 或 0,30）"},
                "cron_hour": {"type": "string", "description": "cron：小时（可选，0-23）"},
                "cron_day": {"type": "string", "description": "cron：日期（可选，1-31）"},
                "cron_month": {"type": "string", "description": "cron：月份（可选，1-12）"},
                "cron_day_of_week": {"type": "string", "description": "cron：星期（可选，mon-fri 或 0-6）"},
            },
            "required": ["job_id", "message", "trigger"],
        },
    },
    {
        "name": "list_schedules",
        "description": "列出所有已设置的定时提醒。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remove_schedule",
        "description": "删除指定 ID 的定时提醒。",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string", "description": "任务 ID"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "pause_schedule",
        "description": "暂停指定 ID 的定时提醒（可恢复）。",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string", "description": "任务 ID"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "resume_schedule",
        "description": "恢复已暂停的定时提醒。",
        "input_schema": {
            "type": "object",
            "properties": {"job_id": {"type": "string", "description": "任务 ID"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "start_summary",
        "description": "启动定期对话摘要。每隔指定分钟自动总结对话，判断是否需要定时推送消息给用户。",
        "input_schema": {
            "type": "object",
            "properties": {
                "interval_minutes": {"type": "integer", "description": "摘要间隔分钟数，默认 30"},
            },
            "required": [],
        },
    },
]
