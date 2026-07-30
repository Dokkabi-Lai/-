"""推送服务：macOS 本地通知 + 系统日历集成。

1. macOS 本地通知：用 osascript 调用系统通知中心
2. 系统日历集成：用 AppleScript 创建日历事件
3. 每日定时推送：每天早上 8:00 推送今日待办
"""
from __future__ import annotations

import datetime as dt
import subprocess
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, Job, get_sessionmaker


def send_macos_notification(title: str, message: str, subtitle: str = "") -> bool:
    """发送 macOS 本地通知。返回是否成功。"""
    # 转义双引号
    title = title.replace('"', '\\"')
    message = message.replace('"', '\\"')
    subtitle = subtitle.replace('"', '\\"')

    script = f'''
    display notification "{message}" with title "{title}" subtitle "{subtitle}" sound name "Glass"
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def add_to_calendar(
    title: str,
    start_dt: dt.datetime,
    end_dt: Optional[dt.datetime] = None,
    location: str = "",
    notes: str = "",
    calendar_name: str = "求职助手",
) -> bool:
    """添加事件到 macOS 系统日历。

    会自动创建名为"求职助手"的日历（如果不存在）。
    需要"自动化"权限（首次运行会弹窗请求）。
    """
    if end_dt is None:
        end_dt = start_dt + dt.timedelta(hours=1)

    # 格式化时间为 AppleScript 需要的格式: "2026年7月30日 14:00:00"
    def fmt(d: dt.datetime) -> str:
        return d.strftime("%Y年%m月%d日 %H:%M:%S")

    title = title.replace('"', '\\"')
    location = location.replace('"', '\\"')
    notes = notes.replace('"', '\\"')

    script = f'''
    tell application "Calendar"
        -- 查找或创建"求职助手"日历
        set calName to "{calendar_name}"
        set targetCal to missing value
        repeat with c in calendars
            if name of c is calName then
                set targetCal to c
                exit repeat
            end if
        end repeat
        if targetCal is missing value then
            -- 创建新日历（在本地账户）
            set targetCal to make new calendar at end of calendars with properties {{name:calName}}
        end if

        -- 创建事件
        make new event at end of events of targetCal with properties {{
            summary:"{title}",
            start date:date "{fmt(start_dt)}",
            end date:date "{fmt(end_dt)}",
            location:"{location}",
            description:"{notes}"
        }}
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_today_summary(db: Session) -> dict:
    """获取今日待办摘要。"""
    today = dt.date.today()
    soon = today + dt.timedelta(days=3)
    day_start = dt.datetime.combine(today, dt.time.min)
    day_end = dt.datetime.combine(today, dt.time.max)

    # 即将截止的岗位
    closing_jobs = db.query(Job).filter(
        Job.close_date != None,
        Job.close_date >= today,
        Job.close_date <= soon,
    ).order_by(Job.close_date).limit(10).all()

    # 今日日程：从 application_stages 获取今天有安排的
    today_stages = db.query(ApplicationStage).join(Application).filter(
        ApplicationStage.scheduled_at.isnot(None),
        ApplicationStage.scheduled_at >= day_start,
        ApplicationStage.scheduled_at <= day_end + dt.timedelta(days=1),
    ).order_by(ApplicationStage.scheduled_at).all()

    return {
        "closing_jobs": closing_jobs,
        "schedules": today_stages,
    }


def push_daily_notification() -> bool:
    """每日推送：发送今日待办通知。"""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        summary = get_today_summary(db)
        job_count = len(summary["closing_jobs"])
        sch_count = len(summary["schedules"])

        if job_count == 0 and sch_count == 0:
            send_macos_notification(
                "求职助手",
                "今天没有紧急待办，可以去浏览新岗位或准备面试",
            )
            return True

        # 分多条通知
        if sch_count > 0:
            msg = f"今天有 {sch_count} 项日程"
            first = summary["schedules"][0]
            app = first.application
            stage_desc = f"{app.company} - {first.stage}" if app else first.stage
            send_macos_notification(
                "今日日程提醒", msg,
                f"最近: {stage_desc} {first.scheduled_at.strftime('%H:%M') if first.scheduled_at else ''}"
            )

        if job_count > 0:
            msg = f"{job_count} 个岗位即将截止"
            send_macos_notification("秋招截止提醒", msg, "请尽快投递")

        return True
    finally:
        db.close()


def sync_schedules_to_calendar() -> dict:
    """把所有未来日程同步到 macOS 系统日历。返回同步结果。"""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        now = dt.datetime.now()
        stages = db.query(ApplicationStage).join(Application).filter(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= now,
        ).all()
        success = 0
        failed = 0
        for s in stages:
            app = s.application
            title = f"[{s.stage}] {app.company} - {app.title}" if app else f"[{s.stage}]"
            ok = add_to_calendar(
                title=title,
                start_dt=s.scheduled_at,
                end_dt=s.scheduled_at + dt.timedelta(hours=1),
                location=s.location or "",
                notes=s.notes or "",
            )
            if ok:
                success += 1
            else:
                failed += 1
        return {"total": len(stages), "success": success, "failed": failed}
    finally:
        db.close()


def sync_deadlines_to_calendar() -> dict:
    """把即将截止的岗位 DDL 同步到系统日历。"""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        today = dt.date.today()
        success = 0
        failed = 0

        # 秋招岗位截止
        jobs = db.query(Job).filter(
            Job.close_date != None, Job.close_date >= today,
        ).all()
        for j in jobs:
            close_dt = dt.datetime.combine(j.close_date, dt.time(18, 0))
            ok = add_to_calendar(
                title=f"截止: {j.company} - {j.title}",
                start_dt=close_dt,
                end_dt=close_dt + dt.timedelta(hours=1),
                notes=f"投递链接: {j.url or '无'}",
            )
            success += 1 if ok else 0
            failed += 0 if ok else 1

        return {"total": len(jobs), "success": success, "failed": failed}
    finally:
        db.close()
