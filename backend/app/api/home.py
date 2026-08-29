"""首页聚合接口：投递跟踪仪表盘。"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, desc, func
from sqlalchemy.orm import Session, contains_eager

from ..models import Application, ApplicationStage, Group, Job, User, get_db
from .deps import get_current_group, get_current_user

router = APIRouter(prefix="/api/home", tags=["home"])


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    return value


def _deadline_tone(days_left: int) -> str:
    if days_left <= 1:
        return "critical"
    if days_left <= 3:
        return "warning"
    if days_left <= 7:
        return "soon"
    return "normal"


def _deadline_label(days_left: int) -> str:
    if days_left <= 0:
        return "今天截止"
    if days_left == 1:
        return "明天截止"
    return f"{days_left}天后截止"


def _deadline_notifications(db: Session, user: User, group: Group, today: dt.date) -> list[dict]:
    """聚合首页提醒：岗位申请截止 + 笔试截止，按紧急程度排序。"""
    items = []
    window_end = today + dt.timedelta(days=14)

    closing_jobs = db.query(Job).filter(
        Job.group_id == group.id,
        Job.is_active.is_not(False),
        Job.close_date.isnot(None),
        Job.close_date >= today,
        Job.close_date <= window_end,
    ).order_by(Job.close_date).limit(30).all()
    for job in closing_jobs:
        target = _as_date(job.close_date)
        days_left = (target - today).days
        items.append({
            "id": f"job-{job.id}",
            "kind": "job_deadline",
            "tone": _deadline_tone(days_left),
            "priority": 0 if days_left <= 1 else 1 if days_left <= 3 else 2 if days_left <= 7 else 3,
            "days_left": days_left,
            "label": _deadline_label(days_left),
            "target_date": target.isoformat(),
            "company": job.company,
            "title": job.title,
            "meta": "岗位申请截止",
            "action": "jobs",
            "job_id": job.id,
        })

    deadline_start = dt.datetime.combine(today, dt.time.min)
    deadline_end = dt.datetime.combine(window_end + dt.timedelta(days=1), dt.time.min)
    exam_deadlines = db.query(ApplicationStage, Application).join(
        Application, Application.id == ApplicationStage.application_id
    ).filter(
        Application.user_id == user.id,
        ApplicationStage.stage == "笔试",
        ApplicationStage.schedule_type == "deadline",
        ApplicationStage.deadline_at.isnot(None),
        ApplicationStage.status.notin_(["completed", "skipped"]),
        ApplicationStage.deadline_at >= deadline_start,
        ApplicationStage.deadline_at < deadline_end,
    ).order_by(ApplicationStage.deadline_at).limit(30).all()
    for stage, app in exam_deadlines:
        target = _as_date(stage.deadline_at)
        days_left = (target - today).days
        items.append({
            "id": f"exam-{stage.id}",
            "kind": "exam_deadline",
            "tone": _deadline_tone(days_left),
            "priority": 0 if days_left <= 1 else 1 if days_left <= 3 else 2 if days_left <= 7 else 3,
            "days_left": days_left,
            "label": _deadline_label(days_left),
            "target_date": target.isoformat(),
            "company": app.company,
            "title": app.title,
            "meta": "笔试截止",
            "action": "track",
            "application_id": app.id,
        })

    items.sort(key=lambda item: (item["priority"], item["target_date"], item["title"]))
    return items[:10]


@router.get("")
def home_feed(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """首页：投递进度、今日日程、岗位动态。"""
    now_local = dt.datetime.now(ZoneInfo("Asia/Shanghai"))
    today = now_local.date()

    day_start = dt.datetime.combine(today, dt.time.min)
    day_end = dt.datetime.combine(today, dt.time.max)
    today_stages = db.query(ApplicationStage).join(Application).options(
        contains_eager(ApplicationStage.application)
    ).filter(
        Application.user_id == user.id,
        and_(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= day_start,
            ApplicationStage.scheduled_at <= day_end,
        ),
    ).order_by(ApplicationStage.scheduled_at).all()

    job_day_start = (
        dt.datetime.combine(today, dt.time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
        .astimezone(dt.timezone.utc)
        .replace(tzinfo=None)
    )
    job_counts = db.query(
        func.count(Job.id),
        func.sum(case((Job.created_at >= job_day_start, 1), else_=0)),
    ).filter(
        Job.group_id == group.id,
        Job.is_active.is_not(False),
    ).one()
    total_jobs = int(job_counts[0] or 0)
    new_today_count = int(job_counts[1] or 0)
    contributor_rows = db.query(User, func.count(Job.id)).join(
        Job, Job.created_by_id == User.id
    ).filter(
        Job.group_id == group.id,
        Job.is_active.is_not(False),
        Job.created_at >= job_day_start,
    ).group_by(User.id).order_by(func.count(Job.id).desc()).all()

    # 投递记录一次取出后在内存中分组，避免首页为同一用户重复发起 5 次统计查询。
    user_apps = db.query(Application).filter(
        Application.user_id == user.id,
    ).order_by(
        desc(Application.applied_at).nullslast(),
        desc(Application.updated_at),
        desc(Application.id),
    ).all()
    in_progress_apps = [
        a for a in user_apps if a.status not in ("已淘汰", "已完成")
    ][:12]
    rejected_apps = [a for a in user_apps if a.status == "已淘汰"][:12]
    total_apps = len(user_apps)
    offer_count = sum(1 for a in user_apps if a.status == "已完成")
    rejected_count = sum(1 for a in user_apps if a.status == "已淘汰")
    in_progress_count = sum(
        1 for a in user_apps if a.status not in ("已淘汰", "已完成")
    )
    notifications = _deadline_notifications(db, user, group, today)

    return {
        "stats": {
            "total_jobs": total_jobs,
            "total_apps": total_apps,
            "schedule_count": len(today_stages),
            "offer_count": offer_count,
            "rejected_count": rejected_count,
            "in_progress_count": in_progress_count,
            "new_today_count": new_today_count,
            "urgent_count": sum(1 for item in notifications if item["tone"] == "critical"),
            "deadline_count": len(notifications),
        },
        "group": {"id": group.id, "name": group.name},
        "job_activity_today": {
            "total": new_today_count,
            "contributors": [{
                "user_id": contributor.id,
                "nickname": contributor.nickname or contributor.email,
                "avatar_type": contributor.avatar_type,
                "avatar_url": contributor.avatar_url,
                "avatar_emoji": contributor.avatar_emoji,
                "count": count,
            } for contributor, count in contributor_rows],
        },
        "in_progress_apps": [_app_summary(a) for a in in_progress_apps],
        "rejected_apps": [_app_summary(a) for a in rejected_apps],
        "today_schedules": [
            {
                "id": s.id,
                "application_id": s.application_id,
                "company": s.application.company if s.application else "",
                "title": s.application.title if s.application else "",
                "stage": s.stage,
                "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                "schedule_type": s.schedule_type or "exact",
                "location": s.location,
                "form": s.form,
            }
            for s in today_stages
        ],
        "notifications": notifications,
    }


def _job_summary(j: Job) -> dict:
    return {
        "id": j.id,
        "company": j.company,
        "title": j.title,
        "company_type": j.company_type,
        "location": j.location,
        "batch": j.batch,
        "open_date": j.open_date.isoformat() if j.open_date else None,
        "close_date": j.close_date.isoformat() if j.close_date else None,
        "close_date_text": j.close_date_text,
        "url": j.url,
        "referrer_code": j.referrer_code,
        "apply_rule": j.apply_rule,
        "favorited": j.favorited,
    }


def _app_summary(a: Application) -> dict:
    return {
        "id": a.id,
        "company": a.company,
        "title": a.title,
        "status": a.status,
        "current_stage": a.current_stage,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
