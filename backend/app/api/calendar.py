"""日历与每日推荐接口。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, Group, Job, User, get_db
from .deps import get_current_group, get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


def _stage_kind(stage: str) -> str:
    if stage == "笔试":
        return "exam"
    if stage in ("一面", "二面", "HR面"):
        return "interview"
    return "other"


@router.get("/today")
def today(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """今日待办：即将截止岗位、今日日程。"""
    today_date = dt.date.today()
    soon = today_date + dt.timedelta(days=3)

    # 即将截止的秋招岗位（3天内）
    closing_jobs = db.query(Job).filter(
        and_(
            Job.is_active.is_not(False),
            Job.group_id == group.id,
            Job.close_date != None,
            Job.close_date >= today_date,
            Job.close_date <= soon,
        )
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
    """某月的日历事件：仅笔试 / 面试 / 其他流程安排。"""
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1)
    else:
        end = dt.date(year, month + 1, 1)

    events = []
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
            "date": s.scheduled_at.date().isoformat(),
            "type": _stage_kind(s.stage),
            "stage": s.stage,
            "title": f"{company} - {s.stage}",
            "id": s.id,
            "application_id": s.application_id,
            "time": s.scheduled_at.strftime("%H:%M") if s.scheduled_at else None,
            "location": s.location,
            "form": s.form,
            "url": s.notes if s.notes and s.notes.startswith("http") else None,
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
