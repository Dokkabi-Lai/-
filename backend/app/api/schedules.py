"""日程接口：从投递阶段中获取有安排时间的日程。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models import Application, ApplicationStage, get_db

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("")
def list_schedules(upcoming: bool = True, limit: int = 100, db: Session = Depends(get_db)):
    """从投递阶段中获取有安排时间的日程。"""
    query = db.query(ApplicationStage).join(Application).filter(
        ApplicationStage.scheduled_at.isnot(None)
    )
    if upcoming:
        query = query.filter(ApplicationStage.scheduled_at >= dt.datetime.now())
    items = query.order_by(ApplicationStage.scheduled_at).limit(limit).all()
    result = []
    for s in items:
        app = s.application
        result.append({
            "id": s.id,
            "application_id": s.application_id,
            "company": app.company if app else "",
            "title": app.title if app else "",
            "stage": s.stage,
            "status": s.status,
            "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "location": s.location,
            "form": s.form,
            "notes": s.notes,
            "feedback": s.feedback,
        })
    return result
