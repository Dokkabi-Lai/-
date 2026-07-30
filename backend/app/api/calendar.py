"""日历与每日推荐接口。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, Job, User, get_db
from .deps import get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/today")
def today(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """今日待办：即将截止岗位、今日日程。"""
    today_date = dt.date.today()
    soon = today_date + dt.timedelta(days=3)

    # 即将截止的秋招岗位（3天内）
    closing_jobs = db.query(Job).filter(
        and_(Job.close_date != None, Job.close_date >= today_date, Job.close_date <= soon)
    ).order_by(Job.close_date).limit(20).all()

    # 今日日程：从 application_stages 获取今天有安排的
    day_start = dt.datetime.combine(today_date, dt.time.min)
    day_end = dt.datetime.combine(today_date, dt.time.max)
    today_stages = db.query(ApplicationStage).join(Application).filter(
        Application.user_id == user.id,
        and_(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= day_start,
            ApplicationStage.scheduled_at <= day_end,
        )
    ).order_by(ApplicationStage.scheduled_at).all()

    return {
        "date": today_date.isoformat(),
        "closing_jobs": [
            {"id": j.id, "company": j.company, "title": j.title,
             "close_date": j.close_date.isoformat() if j.close_date else None}
            for j in closing_jobs
        ],
        "schedules": [
            {
                "id": s.id,
                "application_id": s.application_id,
                "company": s.application.company if s.application else "",
                "title": s.application.title if s.application else "",
                "stage": s.stage,
                "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                "location": s.location,
                "form": s.form,
            }
            for s in today_stages
        ],
    }


@router.get("/month")
def month_view(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """某月的日历事件。"""
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1)
    else:
        end = dt.date(year, month + 1, 1)

    events = []

    def _to_date(v):
        """将 datetime/date/str 统一转为 date"""
        if v is None:
            return None
        if isinstance(v, dt.datetime):
            return v.date()
        if isinstance(v, dt.date):
            return v
        if isinstance(v, str):
            return dt.date.fromisoformat(v[:10])
        return None

    # 1. job_deadline: 秋招岗位截止日期（全局共享）
    for j in db.query(Job).filter(Job.close_date != None).all():
        close = _to_date(j.close_date)
        if close and start <= close < end:
            events.append({
                "date": close.isoformat(), "type": "job_deadline",
                "title": f"{j.company} - {j.title} 截止", "id": j.id,
            })

    # 2. application_stage: 投递阶段有安排时间的（按用户过滤）
    stage_start = dt.datetime.combine(start, dt.time.min)
    stage_end = dt.datetime.combine(end, dt.time.min)
    for s in db.query(ApplicationStage).join(Application).filter(
        Application.user_id == user.id,
        and_(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= stage_start,
            ApplicationStage.scheduled_at < stage_end,
        )
    ):
        app = s.application
        company = app.company if app else ""
        events.append({
            "date": s.scheduled_at.date().isoformat(), "type": "application_stage",
            "title": f"{company} - {s.stage}", "id": s.id,
            "application_id": s.application_id,
            "time": s.scheduled_at.strftime("%H:%M") if s.scheduled_at else None,
            "location": s.location,
            "form": s.form,
            "url": s.notes if s.notes and s.notes.startswith("http") else None,
        })

    # 3. todo_deadline: 待投递岗位截止日期（按用户过滤）
    for a in db.query(Application).filter(Application.current_stage == "投递", Application.user_id == user.id):
        if a.job_id:
            job = db.query(Job).get(a.job_id)
            if job and job.close_date:
                close = _to_date(job.close_date)
                if close and start <= close < end:
                    events.append({
                        "date": close.isoformat(), "type": "todo_deadline",
                        "title": f"待投递: {job.company} - {job.title}", "id": job.id,
                    })

    # 4. todo_deadline: 收藏的岗位截止日期事件（全局共享）
    favorited_jobs = db.query(Job).filter(
        Job.favorited == True,
        Job.close_date.isnot(None),
        Job.close_date >= start,
        Job.close_date < end,
    ).all()
    for job in favorited_jobs:
        close = _to_date(job.close_date)
        if close:
            events.append({
                "date": close.isoformat(),
                "type": "todo_deadline",
                "title": f"待投递: {job.company} - {job.title}",
                "url": job.url,
            })

    return {"year": year, "month": month, "events": events}


@router.get("/month/stats")
def month_stats(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """本月统计概览"""
    start = dt.datetime(year, month, 1)
    if month == 12:
        end = dt.datetime(year + 1, 1, 1)
    else:
        end = dt.datetime(year, month + 1, 1)
    now = dt.datetime.now()

    # 本月所有有时间安排的阶段（按用户过滤）
    all_stages = db.query(ApplicationStage).join(Application).filter(
        Application.user_id == user.id,
        ApplicationStage.scheduled_at.isnot(None),
        ApplicationStage.scheduled_at >= start,
        ApplicationStage.scheduled_at < end,
    ).all()

    total = len(all_stages)
    completed = len([s for s in all_stages if s.status == "completed"])
    upcoming = len([s for s in all_stages if s.scheduled_at and s.scheduled_at > now and s.status != "completed"])

    # 按类型统计
    by_stage = {}
    for s in all_stages:
        by_stage[s.stage] = by_stage.get(s.stage, 0) + 1

    return {
        "total": total,
        "completed": completed,
        "upcoming": upcoming,
        "by_stage": by_stage,
    }
