"""匹配分析与内容生成接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import User, get_db
from ..services.match_service import (
    generate_self_intro,
    match_job,
    optimize_resume,
)
from .deps import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/match/job/{job_id}")
def api_match_job(job_id: int, use_ai: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """匹配分析。use_ai=true 用大模型，默认 false 用规则匹配（免费）。"""
    try:
        return match_job(db, job_id, use_ai=use_ai, user_id=user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/optimize/{job_id}")
def api_optimize(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return optimize_resume(db, job_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/intro/{job_id}")
def api_intro(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return generate_self_intro(db, job_id, user_id=user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
