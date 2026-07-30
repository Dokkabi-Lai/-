"""爬虫管理接口：手动触发、查看日志。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..models import SpiderLog, get_db
from ..spiders.scheduler import run_all_spiders, run_spider

router = APIRouter(prefix="/api/spider", tags=["spider"])


@router.post("/run")
def run_all():
    results = run_all_spiders()
    return [
        {"source": r.source, "status": r.status, "count": r.count, "message": r.message}
        for r in results
    ]


@router.post("/run/{source}")
def run_one(source: str):
    r = run_spider(source)
    return {"source": r.source, "status": r.status, "count": r.count, "message": r.message}


@router.get("/logs")
def logs(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(SpiderLog).order_by(desc(SpiderLog.ran_at)).limit(limit).all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "status": r.status,
            "count": r.count,
            "message": r.message,
            "ran_at": r.ran_at.isoformat() if r.ran_at else None,
        }
        for r in rows
    ]
