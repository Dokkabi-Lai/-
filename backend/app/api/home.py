"""首页聚合接口：投递跟踪仪表盘。"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, Group, Job, User, get_db
from .applications import build_dashboard
from .deps import get_current_group, get_current_user

router = APIRouter(prefix="/api/home", tags=["home"])


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
    today_stages = db.query(ApplicationStage).join(Application).filter(
        Application.user_id == user.id,
        and_(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= day_start,
            ApplicationStage.scheduled_at <= day_end + dt.timedelta(days=1),
        ),
    ).order_by(ApplicationStage.scheduled_at).all()

    job_day_start = (
        dt.datetime.combine(today, dt.time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
        .astimezone(dt.timezone.utc)
        .replace(tzinfo=None)
    )
    new_today_count = db.query(Job).filter(
        Job.group_id == group.id,
        Job.is_active.is_not(False),
        Job.created_at >= job_day_start,
    ).count()
    contributor_rows = db.query(User, func.count(Job.id)).join(
        Job, Job.created_by_id == User.id
    ).filter(
        Job.group_id == group.id,
        Job.is_active.is_not(False),
        Job.created_at >= job_day_start,
    ).group_by(User.id).order_by(func.count(Job.id).desc()).all()

    apps = db.query(Application).filter(Application.user_id == user.id).order_by(
        desc(Application.updated_at)
    ).all()
    in_progress_apps = [a for a in apps if a.status not in ("已淘汰", "已完成")][:12]
    rejected_apps = [a for a in apps if a.status == "已淘汰"][:12]
    dashboard = build_dashboard(apps)
    by_status = dashboard["by_status"]

    total_jobs = db.query(Job).filter(
        Job.group_id == group.id, Job.is_active.is_not(False)
    ).count()

    return {
        "stats": {
            "total_jobs": total_jobs,
            "total_apps": dashboard["total"],
            "schedule_count": len(today_stages),
            "offer_count": by_status["已完成"],
            "rejected_count": by_status["已淘汰"],
            "in_progress_count": by_status["进行中"],
            "new_today_count": new_today_count,
        },
        "dashboard": dashboard,
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
                "location": s.location,
                "form": s.form,
            }
            for s in today_stages
        ],
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
