"""投递记录接口。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, contains_eager, selectinload

from ..models import Application, ApplicationStage, Group, Job, User, get_db
from .deps import get_current_group, get_current_user

router = APIRouter(prefix="/api/applications", tags=["applications"])

STAGES = ["投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"]


def _parse_datetime(value, label: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", ""))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label}格式不正确")


def _serialize_stage(s: ApplicationStage) -> dict:
    return {
        "id": s.id,
        "stage": s.stage,
        "status": s.status,
        "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
        "schedule_type": s.schedule_type or "exact",
        "deadline_at": s.deadline_at.isoformat() if s.deadline_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "location": s.location,
        "form": s.form,
        "notes": s.notes,
        "feedback": s.feedback,
    }


def _serialize_app(a: Application) -> dict:
    # 按 STAGES 顺序排列阶段
    stage_map = {s.stage: s for s in (a.stages or [])}
    ordered_stages = [_serialize_stage(stage_map[name]) for name in STAGES if name in stage_map]
    # 追加不在 STAGES 列表中的阶段（容错）
    known = set(STAGES)
    for s in (a.stages or []):
        if s.stage not in known:
            ordered_stages.append(_serialize_stage(s))
    return {
        "id": a.id,
        "user_id": a.user_id,
        "job_id": a.job_id,
        "company": a.company,
        "title": a.title,
        "channel": a.channel,
        "resume_id": a.resume_id,
        "status": a.status,
        "rejected_stage": a.rejected_stage,
        "current_stage": a.current_stage,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "notes": a.notes,
        "stages": ordered_stages,
    }


# POST /api/applications - 创建投递记录
@router.post("")
def create_application(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    group: Group = Depends(get_current_group),
):
    """创建投递记录，自动生成所有 7 个阶段。"""
    company = body.get("company", "").strip()
    title = body.get("title", "").strip()
    if not company or not title:
        raise HTTPException(400, "company 和 title 不能为空")
    job_id = body.get("job_id")
    if job_id and not db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first():
        raise HTTPException(404, "当前群组中没有这个岗位")

    notes = body.get("notes")
    applied_at = None
    if body.get("applied_at"):
        try:
            applied_at = dt.datetime.fromisoformat(str(body["applied_at"]).replace("Z", ""))
        except ValueError:
            raise HTTPException(400, "投递时间格式不正确")

    app = Application(
        user_id=user.id,
        job_id=job_id,
        company=company,
        title=title,
        channel=body.get("channel"),
        notes=notes,
        status="已投递",
        current_stage="投递",
        applied_at=applied_at or dt.datetime.now(),
    )
    db.add(app)
    db.flush()  # 获取 app.id

    # 创建 7 个阶段记录
    for i, stage_name in enumerate(STAGES):
        stage = ApplicationStage(
            application_id=app.id,
            stage=stage_name,
            status="completed" if i == 0 else "pending",
            completed_at=dt.datetime.now() if i == 0 else None,
        )
        db.add(stage)

    db.commit()
    db.refresh(app)
    return _serialize_app(app)


# GET /api/applications - 获取所有投递记录
@router.get("")
def list_applications(status: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有投递记录，每条记录带上所有阶段信息。"""
    q = db.query(Application).options(selectinload(Application.stages)).filter(
        Application.user_id == user.id
    )
    if status:
        q = q.filter(Application.status == status)
    rows = q.order_by(desc(Application.updated_at)).all()
    return [_serialize_app(a) for a in rows]


# GET /api/applications/offers/list - 获取所有已拿到 Offer 的投递记录
@router.get("/offers/list")
def list_offers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有已拿到 Offer 的投递记录"""
    apps = db.query(Application).options(selectinload(Application.stages)).filter(
        Application.status == "已完成", Application.user_id == user.id
    ).order_by(desc(Application.updated_at)).all()
    return [_serialize_app(a) for a in apps]


# GET /api/applications/reviews/all - 获取所有复盘反馈
@router.get("/reviews/all")
def list_all_reviews(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有有复盘反馈的阶段，按公司分组"""
    stages = db.query(ApplicationStage).join(Application).options(
        contains_eager(ApplicationStage.application)
    ).filter(
        Application.user_id == user.id,
        ApplicationStage.feedback.isnot(None),
        ApplicationStage.feedback != "",
    ).order_by(desc(Application.updated_at)).all()

    result = {}
    for s in stages:
        app = s.application
        key = app.company
        if key not in result:
            result[key] = {"company": app.company, "items": []}
        result[key]["items"].append({
            "id": s.id,
            "application_id": s.application_id,
            "company": app.company,
            "title": app.title,
            "stage": s.stage,
            "feedback": s.feedback,
            "notes": s.notes,
            "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "form": s.form,
            "location": s.location,
        })
    return list(result.values())


@router.get("/dashboard")
def application_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """投递仪表盘：漏斗与阶段分布。"""
    apps = db.query(Application).filter(Application.user_id == user.id).all()
    by_stage = {s: 0 for s in STAGES}
    by_status = {"进行中": 0, "已淘汰": 0, "已完成": 0}
    for a in apps:
        if a.status == "已淘汰":
            by_status["已淘汰"] += 1
        elif a.status == "已完成":
            by_status["已完成"] += 1
        else:
            by_status["进行中"] += 1
        if a.current_stage in by_stage:
            by_stage[a.current_stage] += 1

    def _reached(stage: str) -> int:
        idx = STAGES.index(stage)
        n = 0
        for a in apps:
            cur = STAGES.index(a.current_stage) if a.current_stage in STAGES else 0
            if a.status == "已完成":
                n += 1
            elif cur >= idx:
                n += 1
        return n

    return {
        "total": len(apps),
        "by_status": by_status,
        "by_stage": by_stage,
        "funnel": {
            "投递": _reached("投递"),
            "简历筛选": _reached("简历筛选"),
            "笔试": _reached("笔试"),
            "面试": _reached("一面"),
            "Offer": by_status["已完成"],
        },
        "reject_by_stage": _reject_by_stage(apps),
        "weekly": _weekly_counts(apps),
    }


def _reject_by_stage(apps: list[Application]) -> dict:
    out: dict[str, int] = {}
    for a in apps:
        if a.status != "已淘汰":
            continue
        key = a.rejected_stage or "未知"
        out[key] = out.get(key, 0) + 1
    return out


def _weekly_counts(apps: list[Application]) -> list[dict]:
    today = dt.date.today()
    start_monday = today - dt.timedelta(days=today.weekday())
    weeks = []
    for i in range(7, -1, -1):
        week_start = start_monday - dt.timedelta(days=i * 7)
        week_end = week_start + dt.timedelta(days=7)
        count = 0
        for a in apps:
            if not a.applied_at:
                continue
            d = a.applied_at.date()
            if week_start <= d < week_end:
                count += 1
        label = f"{week_start.month}/{week_start.day}"
        weeks.append({"week": week_start.isoformat(), "label": label, "count": count})
    return weeks


# GET /api/applications/{id} - 获取单条投递详情
@router.get("/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取单条投递详情，包含所有阶段。"""
    app = db.query(Application).options(selectinload(Application.stages)).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    return _serialize_app(app)


# PATCH /api/applications/{id} - 更新投递记录基本信息
@router.patch("/{app_id}")
def update_application(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新投递记录基本信息。"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    for field in ("company", "title", "channel", "notes", "applied_at"):
        if field not in body:
            continue
        val = body[field]
        if field == "applied_at":
            if not val:
                continue
            try:
                app.applied_at = dt.datetime.fromisoformat(str(val).replace("Z", ""))
            except ValueError:
                raise HTTPException(400, "投递时间格式不正确")
        elif val is not None:
            setattr(app, field, val)
    db.commit()
    db.refresh(app)
    return _serialize_app(app)


# DELETE /api/applications/{id} - 删除投递记录（级联删除阶段）
@router.delete("/{app_id}")
def delete_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """删除投递记录（级联删除阶段）。"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    db.delete(app)
    db.commit()
    return {"ok": True}


# PATCH /api/applications/{id}/stage/{stage_name} - 更新某个阶段
@router.patch("/{app_id}/stage/{stage_name}")
def update_stage(app_id: int, stage_name: str, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新某个阶段的信息。"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    stage = db.query(ApplicationStage).filter(
        ApplicationStage.application_id == app_id,
        ApplicationStage.stage == stage_name,
    ).first()
    if not stage:
        raise HTTPException(404, f"阶段 '{stage_name}' 不存在")

    for field in ("location", "form", "notes", "feedback"):
        if field in body and body[field] is not None:
            setattr(stage, field, body[field])

    if "scheduled_at" in body:
        stage.scheduled_at = _parse_datetime(body["scheduled_at"], "固定时间")

    if "deadline_at" in body:
        stage.deadline_at = _parse_datetime(body["deadline_at"], "截止时间")

    if "schedule_type" in body:
        schedule_type = body.get("schedule_type") or "exact"
        if schedule_type not in ("exact", "deadline"):
            raise HTTPException(400, "笔试时间类型不正确")
        stage.schedule_type = schedule_type
    elif stage_name == "笔试" and body.get("deadline_at"):
        # 兼容只提交截止时间的旧客户端。
        stage.schedule_type = "deadline"

    if stage_name != "笔试":
        stage.schedule_type = "exact"
        stage.deadline_at = None
    elif stage.schedule_type == "deadline":
        stage.scheduled_at = None
    else:
        stage.deadline_at = None

    if "completed_at" in body:
        stage.completed_at = dt.datetime.fromisoformat(body["completed_at"]) if body["completed_at"] else None

    if "status" in body:
        stage.status = body["status"]
        # 当 status 改为 completed 时自动设 completed_at
        if body["status"] == "completed" and not stage.completed_at:
            stage.completed_at = dt.datetime.now()
        # 更新 Application 的 current_stage 为最新的 completed 阶段
        _sync_current_stage(app, db)

    db.commit()
    db.refresh(app)
    return _serialize_app(app)


# POST /api/applications/{id}/advance - 推进到下一阶段
@router.post("/{app_id}/advance")
def advance_stage(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """推进到下一阶段：将当前阶段标记为 completed，下一个阶段设为 current。"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    stage_map = {s.stage: s for s in (app.stages or [])}

    # 找到当前阶段在 STAGES 中的索引
    current_idx = None
    for i, name in enumerate(STAGES):
        if name == app.current_stage:
            current_idx = i
            break

    if current_idx is None:
        raise HTTPException(400, f"当前阶段 '{app.current_stage}' 无法识别")

    if current_idx >= len(STAGES) - 1:
        # 已经在最后一个阶段（Offer），标记为已完成
        current_stage = stage_map.get(STAGES[current_idx])
        if current_stage:
            current_stage.status = "completed"
            if not current_stage.completed_at:
                current_stage.completed_at = dt.datetime.now()
        app.status = "已完成"
        app.current_stage = "Offer"
        db.commit()
        db.refresh(app)
        return _serialize_app(app)

    # 将当前阶段标记为 completed
    current_stage = stage_map.get(STAGES[current_idx])
    if current_stage:
        current_stage.status = "completed"
        if not current_stage.completed_at:
            current_stage.completed_at = dt.datetime.now()

    next_name = STAGES[current_idx + 1]
    next_stage = stage_map.get(next_name)
    if next_stage:
        next_stage.status = "current"

    app.current_stage = next_name
    db.commit()
    db.refresh(app)
    return _serialize_app(app)


def _sync_current_stage(app: Application, db: Session):
    """根据阶段完成情况，更新 Application.current_stage。"""
    stage_map = {s.stage: s for s in (app.stages or [])}
    last_completed = None
    for name in STAGES:
        s = stage_map.get(name)
        if s and s.status == "completed":
            last_completed = name
    if last_completed:
        idx = STAGES.index(last_completed)
        if idx < len(STAGES) - 1:
            app.current_stage = STAGES[idx + 1]
        else:
            app.current_stage = last_completed
    else:
        # 没有任何 completed 阶段，回到第一个
        app.current_stage = STAGES[0]


# POST /api/applications/{id}/rollback - 回退到指定阶段
@router.post("/{app_id}/rollback")
def rollback_stage(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """回退到指定阶段：将该阶段及后续阶段全部重置为 pending。"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    target_stage = body.get("stage")
    if not target_stage or target_stage not in STAGES:
        raise HTTPException(400, "无效的阶段名")

    target_idx = STAGES.index(target_stage)
    stage_map = {s.stage: s for s in (app.stages or [])}

    # 将目标阶段及之后的阶段全部重置为 pending
    for i in range(target_idx, len(STAGES)):
        s = stage_map.get(STAGES[i])
        if s:
            s.status = "pending"
            s.completed_at = None

    # 将目标阶段之前最后一个标记为 completed（如果有的话）
    if target_idx > 0:
        prev = stage_map.get(STAGES[target_idx - 1])
        if prev and prev.status != "completed":
            prev.status = "completed"
            if not prev.completed_at:
                prev.completed_at = dt.datetime.now()

    # 更新 current_stage
    app.current_stage = target_stage
    # 如果之前是淘汰状态，恢复
    if app.status == "已淘汰":
        app.status = "进行中"
        app.rejected_stage = None

    db.commit()
    db.refresh(app)
    return _serialize_app(app)


@router.post("/{app_id}/reject")
def reject_application(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """标记投递为已淘汰"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    app.status = "已淘汰"
    app.rejected_stage = body.get("stage", app.current_stage)
    # 将被淘汰的阶段标记为 skipped
    stage = db.query(ApplicationStage).filter(
        ApplicationStage.application_id == app_id,
        ApplicationStage.stage == app.rejected_stage,
    ).first()
    if stage:
        stage.status = "skipped"
    db.commit()
    db.refresh(app)
    return _serialize_app(app)


@router.post("/{app_id}/restore")
def restore_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """恢复已淘汰的投递"""
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    old_stage = app.rejected_stage
    app.status = "进行中"
    app.rejected_stage = None
    if old_stage:
        stage = db.query(ApplicationStage).filter(
            ApplicationStage.application_id == app_id,
            ApplicationStage.stage == old_stage,
        ).first()
        if stage:
            stage.status = "pending"
    db.commit()
    db.refresh(app)
    return _serialize_app(app)
