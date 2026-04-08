import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

BASE_DIR = Path(__file__).parent
SCHEDULE_FILE = BASE_DIR / "schedule.json"

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.start()

_reminders: list[dict] = []
_lock = threading.Lock()
_callbacks: list[callable] = []
_summary_callback: callable | None = None


def _load() -> list[dict]:
    if SCHEDULE_FILE.exists():
        try:
            return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save():
    SCHEDULE_FILE.write_text(
        json.dumps(_reminders, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _notify(reminder_id: str, message: str):
    """触发提醒回调"""
    for cb in _callbacks:
        try:
            cb(reminder_id, message)
        except Exception:
            pass


def add_callback(cb: callable):
    """注册普通提醒回调（接收 reminder_id, message）"""
    _callbacks.append(cb)


def set_summary_callback(cb: callable):
    """注册对话摘要回调。触发时会传入当前对话历史，cb 应返回摘要文字或决定是否调度后续消息。"""
    global _summary_callback
    _summary_callback = cb


def trigger_summary():
    """手动触发一次对话摘要（由定时任务调用）"""
    if _summary_callback:
        try:
            _summary_callback()
        except Exception as e:
            print(f"[摘要回调错误] {e}")


def start_conversation_summary(interval_minutes: int = 30):
    """启动定期对话摘要任务，每隔 interval_minutes 分钟触发一次"""
    job_id = "__conversation_summary__"
    with _lock:
        # 移除旧的
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        scheduler.add_job(
            trigger_summary,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=60,
        )
        job = scheduler.get_job(job_id)
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else "未知"
        print(f"[对话摘要] 已启动，每 {interval_minutes} 分钟执行一次，下次: {next_run}")
    return f"对话摘要任务已启动，每 {interval_minutes} 分钟一次"


def add_reminder(
    job_id: str,
    message: str,
    trigger_type: str,
    **trigger_kwargs,
) -> dict:
    """添加定时任务，返回任务信息"""
    global _reminders
    with _lock:
        # 避免重复
        _reminders = [r for r in _reminders if r["id"] != job_id]

        task = {
            "id": job_id,
            "message": message,
            "trigger": trigger_type,
            "params": trigger_kwargs,
            "created_at": datetime.now().isoformat(),
        }

        if trigger_type == "date":
            # 一次性：在指定时间触发
            run_at = datetime.fromisoformat(trigger_kwargs["run_at"])
            scheduler.add_job(
                lambda: _notify(job_id, message),
                trigger=DateTrigger(run_date=run_at),
                id=job_id,
                replace_existing=True,
            )
            task["next_run"] = run_at.isoformat()

        elif trigger_type == "interval":
            # 间隔重复
            interval_seconds = trigger_kwargs.get("seconds")
            interval_minutes = trigger_kwargs.get("minutes")
            interval_hours = trigger_kwargs.get("hours")
            interval_days = trigger_kwargs.get("days")
            interval_kwargs = {
                k: v for k, v in {
                    "seconds": interval_seconds,
                    "minutes": interval_minutes,
                    "hours": interval_hours,
                    "days": interval_days,
                }.items() if v is not None
            }
            scheduler.add_job(
                lambda: _notify(job_id, message),
                trigger=IntervalTrigger(**interval_kwargs),
                id=job_id,
                replace_existing=True,
            )
            job = scheduler.get_job(job_id)
            if job:
                task["next_run"] = job.next_run_time.isoformat() if job.next_run_time else None

        elif trigger_type == "cron":
            # Cron 表达式
            cron_fields = {}
            for field in ("second", "minute", "hour", "day", "month", "day_of_week"):
                val = trigger_kwargs.get(field)
                if val is not None:
                    cron_fields[field] = val
            scheduler.add_job(
                lambda: _notify(job_id, message),
                trigger=CronTrigger(**cron_fields),
                id=job_id,
                replace_existing=True,
            )
            job = scheduler.get_job(job_id)
            if job:
                task["next_run"] = job.next_run_time.isoformat() if job.next_run_time else None

        _reminders.append(task)
        _save()
        return task


def list_reminders() -> list[dict]:
    """列出所有定时任务"""
    with _lock:
        result = []
        for r in _reminders:
            job = scheduler.get_job(r["id"])
            next_run = None
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
            result.append({**r, "next_run": next_run})
        return result


def remove_reminder(job_id: str) -> str:
    """删除定时任务"""
    with _lock:
        scheduler.remove_job(job_id)
        global _reminders
        _reminders = [r for r in _reminders if r["id"] != job_id]
        _save()
        return f"已删除定时任务: {job_id}"


def pause_reminder(job_id: str) -> str:
    """暂停任务"""
    scheduler.pause_job(job_id)
    return f"已暂停: {job_id}"


def resume_reminder(job_id: str) -> str:
    """恢复任务"""
    scheduler.resume_job(job_id)
    return f"已恢复: {job_id}"


# 启动时加载已有任务
_reminders = _load()
for r in _reminders:
    try:
        if r["trigger"] == "date":
            run_at = datetime.fromisoformat(r["params"]["run_at"])
            scheduler.add_job(
                lambda rid=r["id"], msg=r["message"]: _notify(rid, msg),
                trigger=DateTrigger(run_date=run_at),
                id=r["id"],
                replace_existing=True,
            )
        elif r["trigger"] == "interval":
            interval_kwargs = {k: v for k, v in r["params"].items() if v is not None}
            scheduler.add_job(
                lambda rid=r["id"], msg=r["message"]: _notify(rid, msg),
                trigger=IntervalTrigger(**interval_kwargs),
                id=r["id"],
                replace_existing=True,
            )
        elif r["trigger"] == "cron":
            cron_fields = {k: v for k, v in r["params"].items() if v is not None}
            scheduler.add_job(
                lambda rid=r["id"], msg=r["message"]: _notify(rid, msg),
                trigger=CronTrigger(**cron_fields),
                id=r["id"],
                replace_existing=True,
            )
    except Exception as e:
        print(f"[scheduler] 加载任务失败 {r.get('id')}: {e}")
