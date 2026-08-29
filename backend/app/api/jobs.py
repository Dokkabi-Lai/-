"""秋招岗位相关接口。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..models import Application, Group, Job, JobMark, User, get_db
from ..services.group_service import is_platform_admin
from .deps import get_current_group, get_current_user, require_group_owner

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: int
    source: str
    company: str
    title: str
    location: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    url: Optional[str] = None
    referrer_code: Optional[str] = None
    favorited: bool = False

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    company: str
    title: str
    company_type: Optional[str] = None
    batch: Optional[str] = None
    location: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    close_date_text: Optional[str] = None
    apply_rule: Optional[str] = None
    url: Optional[str] = None
    referrer_code: Optional[str] = None


def _marks_map(db: Session, user_id: int, job_ids: list[int] | None = None) -> dict[int, JobMark]:
    query = db.query(JobMark).filter(JobMark.user_id == user_id)
    if job_ids:
        query = query.filter(JobMark.job_id.in_(job_ids))
    rows = query.all()
    return {m.job_id: m for m in rows}


def _get_mark(db: Session, user_id: int, job_id: int) -> JobMark:
    mark = db.query(JobMark).filter_by(user_id=user_id, job_id=job_id).first()
    if not mark:
        mark = JobMark(user_id=user_id, job_id=job_id, passed=False, favorited=False)
        db.add(mark)
        db.flush()
    return mark


def _serialize(
    job: Job,
    applied: bool = False,
    mark: JobMark | None = None,
    include_details: bool = True,
) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "company": job.company,
        "title": job.title,
        "company_type": job.company_type,
        "location": job.location,
        "salary": job.salary,
        # 岗位列表只需要摘要；详情在点击岗位时按需加载，避免把整张 JD
        # 随 500 条岗位一起传到手机端。
        "description": job.description if include_details else None,
        "requirements": job.requirements if include_details else None,
        "batch": job.batch,
        "open_date": job.open_date.isoformat() if job.open_date else None,
        "close_date": job.close_date.isoformat() if job.close_date else None,
        "close_date_text": job.close_date_text,
        "apply_rule": job.apply_rule,
        "url": job.url,
        "referrer_code": job.referrer_code,
        "favorited": bool(mark.favorited) if mark else False,
        "passed": bool(mark.passed) if mark else False,
        "applied": applied,
        "is_active": job.is_active is not False,
        "created_by_id": job.created_by_id,
        "group_id": job.group_id,
    }


@router.get("")
def list_jobs(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    batch: Optional[str] = None,
    company_type: Optional[str] = None,
    favorited: Optional[bool] = None,
    only_open: bool = False,
    source: Optional[str] = None,
    hide_passed: bool = True,
    applied: Optional[str] = None,
    summary: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    q = db.query(Job).filter(Job.group_id == group.id, Job.is_active.is_not(False))
    applied_ids_query = select(Application.job_id).where(
        Application.user_id == user.id,
        Application.job_id.isnot(None),
    )
    if hide_passed:
        q = q.filter(~Job.id.in_(select(JobMark.job_id).where(
            JobMark.user_id == user.id,
            JobMark.passed.is_(True),
        )))
    if keyword:
        q = q.filter(or_(
            Job.company.contains(keyword),
            Job.title.contains(keyword),
            Job.description.contains(keyword),
        ))
    if location:
        q = q.filter(Job.location.contains(location))
    if batch:
        q = q.filter(Job.batch == batch)
    if company_type:
        q = q.filter(Job.company_type == company_type)
    if source:
        q = q.filter(Job.source == source)
    if favorited is not None:
        if favorited:
            q = q.filter(Job.id.in_(select(JobMark.job_id).where(
                JobMark.user_id == user.id,
                JobMark.favorited.is_(True),
            )))
        else:
            q = q.filter(~Job.id.in_(select(JobMark.job_id).where(
                JobMark.user_id == user.id,
                JobMark.favorited.is_(True),
            )))
    if only_open:
        today = dt.date.today()
        q = q.filter(or_(Job.close_date == None, Job.close_date >= today))
    if applied == "applied":
        q = q.filter(Job.id.in_(applied_ids_query))
    elif applied == "unapplied":
        q = q.filter(~Job.id.in_(applied_ids_query))
    total = q.count()
    rows = q.order_by(desc(Job.created_at)).offset(offset).limit(limit).all()
    row_ids = [job.id for job in rows]
    applied_ids = set()
    marks = {}
    if row_ids:
        applied_ids = {
            row[0]
            for row in db.query(Application.job_id).filter(
                Application.user_id == user.id,
                Application.job_id.in_(row_ids),
            ).all()
            if row[0]
        }
        marks = _marks_map(db, user.id, row_ids)
    return {
        "total": total,
        "items": [
            _serialize(j, j.id in applied_ids, marks.get(j.id), include_details=not summary)
            for j in rows
        ],
    }


@router.get("/batches/list")
def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """获取所有可用批次列表"""
    from sqlalchemy import func
    rows = db.query(Job.batch, func.count(Job.id)).filter(
        Job.group_id == group.id, Job.batch.isnot(None), Job.is_active.is_not(False)
    ).group_by(Job.batch).all()
    return [{"batch": b, "count": c} for b, c in rows]


@router.get("/company-types/list")
def list_company_types(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    from sqlalchemy import func
    rows = db.query(Job.company_type, func.count(Job.id)).filter(
        Job.group_id == group.id, Job.company_type.isnot(None), Job.is_active.is_not(False)
    ).group_by(Job.company_type).all()
    return [{"company_type": t, "count": c} for t, c in rows]


@router.get("/import/status")
def import_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    from ..services.excel_import_service import import_status as _status

    result = _status(db, group_id=group.id)
    result["can_manage"] = True
    result["can_sync"] = bool(is_platform_admin(user) or group.owner_id == user.id)
    return result


@router.post("/import/reload")
def reload_from_excel(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(require_group_owner),
):
    """从最近一次上传或配置的 Excel 重新导入岗位。"""
    from ..services.excel_import_service import import_jobs_from_excel

    try:
        result = import_jobs_from_excel(db=db, group_id=group.id, created_by_id=user.id)
        return {"message": "导入完成", **result}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导入失败: {e}")


@router.post("/import/upload")
async def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(require_group_owner),
):
    """上传 Excel / CSV 覆盖岗位库（推荐每天更新用这个）。"""
    from ..services.excel_import_service import import_jobs_from_bytes

    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "请上传 .xlsx 表格")
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件是空的")
    try:
        result = import_jobs_from_bytes(
            content, save_as_latest=True, db=db, group_id=group.id, created_by_id=user.id
        )
        return {"message": "上传并导入完成", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"导入失败: {e}")


@router.post("/import/rows")
def import_rows(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """接收类 Excel 网格提交的固定字段岗位。"""
    from ..services.excel_import_service import import_job_items, parse_value_rows

    rows = body.get("rows") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "请至少填写一行岗位")
    if len(rows) > 300:
        raise HTTPException(400, "单次最多导入 300 行")
    keys = [
        "company", "company_type", "batch", "location", "title", "description",
        "url", "open_date", "close_date", "apply_rule", "referrer_code", "recorded_at",
    ]
    headers = [
        "公司", "公司类型", "批次", "BASE", "岗位", "岗位JD",
        "投递链接", "开始日期", "截止日期", "投递机制", "内推码", "记录时间",
    ]
    values = []
    errors = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append({"row": index, "message": "行格式不正确"})
            continue
        company = str(row.get("company") or "").strip()
        title = str(row.get("title") or "").strip()
        if not company or not title:
            errors.append({"row": index, "message": "公司和岗位为必填项"})
            continue
        values.append([row.get(key) for key in keys])
    items = parse_value_rows(headers, values)
    if not items:
        raise HTTPException(400, {"message": "没有可导入的岗位", "errors": errors})
    result = import_job_items(
        items,
        db=db,
        source_label="manual",
        group_id=group.id,
        created_by_id=user.id,
    )
    return {"message": "岗位已加入群组", **result, "errors": errors}


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    applied = db.query(Application).filter(
        Application.user_id == user.id, Application.job_id == job_id
    ).first() is not None
    return _serialize(job, applied, _marks_map(db, user.id, [job.id]).get(job.id))


@router.post("")
def add_job(
    data: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = Job(
        source="manual",
        source_id=f"g{group.id}-manual-{dt.datetime.now().timestamp()}-{user.id}",
        group_id=group.id,
        created_by_id=user.id,
        company=data.company,
        title=data.title,
        company_type=data.company_type,
        batch=data.batch,
        location=data.location,
        salary=data.salary,
        description=data.description,
        requirements=data.requirements,
        open_date=dt.date.fromisoformat(data.open_date) if data.open_date else None,
        close_date=dt.date.fromisoformat(data.close_date) if data.close_date else None,
        close_date_text=data.close_date_text,
        apply_rule=data.apply_rule,
        url=data.url,
        referrer_code=data.referrer_code,
    )
    db.add(job)
    db.commit()
    return _serialize(job)


@router.post("/{job_id}/favorite")
def toggle_favorite(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    mark = _get_mark(db, user.id, job_id)
    mark.favorited = not mark.favorited
    db.commit()
    return {"favorited": mark.favorited}


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    if not is_platform_admin(user) and group.owner_id != user.id and job.created_by_id != user.id:
        raise HTTPException(403, "只能下架自己添加的岗位")
    job.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/pass-company")
def pass_company(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    company = body.get("company", "").strip()
    if not company:
        raise HTTPException(400, "company 不能为空")
    jobs = db.query(Job).filter(Job.group_id == group.id, Job.company == company).all()
    if not jobs:
        raise HTTPException(404, "没有找到该公司岗位")
    marks = _marks_map(db, user.id, [job.id for job in jobs])
    all_passed = bool(jobs) and all(marks.get(j.id) and marks[j.id].passed for j in jobs)
    new_val = not all_passed
    for j in jobs:
        mark = _get_mark(db, user.id, j.id)
        mark.passed = new_val
    db.commit()
    return {"company": company, "passed": new_val, "count": len(jobs)}


@router.post("/{job_id}/pass")
def toggle_pass(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
    if not job:
        raise HTTPException(404, "岗位不存在")
    mark = _get_mark(db, user.id, job_id)
    mark.passed = not mark.passed
    db.commit()
    return {"passed": mark.passed}
