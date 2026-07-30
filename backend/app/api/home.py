"""首页聚合接口：分类推送。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, Job, Preference, Resume, User, get_db
from ..services.match_service import _rule_match_job
from .deps import get_current_user

router = APIRouter(prefix="/api/home", tags=["home"])


@router.get("")
def home_feed(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """首页聚合数据：新开岗位、匹配推荐、即将截止、今日待办。"""
    today = dt.date.today()
    week_ago = today - dt.timedelta(days=7)
    soon = today + dt.timedelta(days=7)

    # 1. 新开岗位（最近7天内开放的）
    new_jobs = db.query(Job).filter(
        Job.open_date != None,
        Job.open_date >= week_ago,
        or_(Job.close_date == None, Job.close_date >= today),
    ).order_by(desc(Job.open_date)).limit(12).all()

    # 2. 匹配推荐（基于偏好+简历+AI推荐职位的规则匹配，取分数最高的）
    pref = db.query(Preference).filter(Preference.user_id == user.id).first()
    resume = db.query(Resume).filter_by(is_default=True, user_id=user.id).first() or db.query(Resume).filter(Resume.user_id == user.id).first()
    resume_text = (resume.raw_text or "") if resume else ""
    rec_positions = (resume.structured or {}).get("recommended_positions") if resume else None
    all_open = db.query(Job).filter(
        or_(Job.close_date == None, Job.close_date >= today),
    ).order_by(desc(Job.created_at)).limit(300).all()
    matched = []
    if pref or rec_positions:
        for job in all_open:
            result = _rule_match_job(job, resume_text, pref, recommended_positions=rec_positions)
            if result["score"] >= 55:
                matched.append((job, result))
        matched.sort(key=lambda x: x[1]["score"], reverse=True)
        matched = matched[:12]
    else:
        # 没设偏好就取最新的
        matched = [(j, {"score": 50, "summary": "未设置偏好，按时间推荐"}) for j in all_open[:12]]

    # 3. 即将截止（7天内截止）
    closing_jobs = db.query(Job).filter(
        Job.close_date != None,
        Job.close_date >= today,
        Job.close_date <= soon,
    ).order_by(Job.close_date).limit(12).all()

    # 4. 今日待办：从 application_stages 获取今天有安排的
    now = dt.datetime.now()
    day_start = dt.datetime.combine(today, dt.time.min)
    day_end = dt.datetime.combine(today, dt.time.max)
    today_stages = db.query(ApplicationStage).join(Application).filter(
        Application.user_id == user.id,
        and_(
            ApplicationStage.scheduled_at.isnot(None),
            ApplicationStage.scheduled_at >= day_start,
            ApplicationStage.scheduled_at <= day_end + dt.timedelta(days=1),
        )
    ).order_by(ApplicationStage.scheduled_at).all()

    # 5. 统计
    total_jobs = db.query(Job).count()
    total_apps = db.query(Application).filter(Application.user_id == user.id).count()
    offer_count = db.query(Application).filter(
        Application.status == "已完成", Application.user_id == user.id
    ).count()

    rejected_count = db.query(Application).filter(Application.status == "已淘汰", Application.user_id == user.id).count()
    in_progress_count = db.query(Application).filter(Application.status != "已淘汰", Application.status != "已完成", Application.user_id == user.id).count()

    return {
        "stats": {
            "total_jobs": total_jobs,
            "total_apps": total_apps,
            "closing_count": len(closing_jobs),
            "schedule_count": len(today_stages),
            "offer_count": offer_count,
            "rejected_count": rejected_count,
            "in_progress_count": in_progress_count,
        },
        "new_jobs": [_job_summary(j) for j in new_jobs],
        "matched": [
            {**_job_summary(job), "match_score": result["score"], "match_summary": result.get("summary", "")}
            for job, result in matched
        ],
        "closing_jobs": [_job_summary(j) for j in closing_jobs],
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
        "location": j.location,
        "salary": j.salary,
        "open_date": j.open_date.isoformat() if j.open_date else None,
        "close_date": j.close_date.isoformat() if j.close_date else None,
        "url": j.url,
        "favorited": j.favorited,
    }
