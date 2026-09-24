"""投递记录接口。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from ..models import Application, ApplicationStage, Group, Job, User, get_db
from ..services.stage_service import (
    DEFAULT_APPLICATION_STAGES,
    LEGACY_DEFAULT_APPLICATION_STAGES,
    is_assessment_stage,
    is_interview_stage,
    stage_statistics_bucket,
)
from .deps import get_current_group, get_current_user

router = APIRouter(prefix="/api/applications", tags=["applications"])

STAGES = DEFAULT_APPLICATION_STAGES


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
        "position": s.position if s.position is not None else 0,
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


def _ordered_stage_rows(stages: list[ApplicationStage] | None) -> list[ApplicationStage]:
    """按每条投递自己的流程顺序返回阶段。

    ``position`` 是新版本的顺序字段。排序 key 里保留默认阶段名作为第二
    级规则，是为了兼容刚升级但尚未完成迁移的旧记录，以及测试/导入数据。
    """
    rows = list(stages or [])
    default_rank = {name: index for index, name in enumerate(STAGES)}
    default_rank.update({
        name: index for index, name in enumerate(LEGACY_DEFAULT_APPLICATION_STAGES)
        if name not in default_rank
    })
    return sorted(
        rows,
        key=lambda row: (
            row.position if row.position is not None else default_rank.get(row.stage, 1000),
            default_rank.get(row.stage, 1000),
            row.created_at or dt.datetime.min,
            row.id or 0,
        ),
    )


def _deadline_capable_stage(stage_name: str) -> bool:
    """测评类阶段支持“固定时间”或“截止时间”两种安排方式。"""
    return is_assessment_stage(stage_name)


def _stage_has_history(stage: ApplicationStage) -> bool:
    """有过状态或时间/备注记录的阶段不能直接删除。"""
    return bool(
        stage.status not in (None, "pending")
        or stage.scheduled_at
        or stage.deadline_at
        or stage.completed_at
        or stage.location
        or stage.form
        or stage.notes
        or stage.feedback
    )


def _effective_current_stage(
    app: Application,
    stages: list[ApplicationStage] | None = None,
) -> str | None:
    """从阶段记录推导真正正在进行的环节。

    ``Application.current_stage`` 是旧版本的缓存字段，历史数据可能没有及时
    更新。阶段记录才是事实来源：优先取 current，其次取最后一个已完成阶段
    后面的第一个未跳过阶段。
    """
    stage_rows = app.stages if stages is None else stages
    ordered_rows = _ordered_stage_rows(stage_rows)
    if app.status == "已完成":
        return ordered_rows[-1].stage if ordered_rows else (app.current_stage or "Offer")
    if app.status == "已淘汰":
        return app.rejected_stage or app.current_stage

    for stage in ordered_rows:
        if stage.status == "current":
            return stage.stage

    last_completed_idx = -1
    for idx, stage in enumerate(ordered_rows):
        if stage.status == "completed":
            last_completed_idx = idx
    for stage in ordered_rows[last_completed_idx + 1:]:
        if stage.status != "skipped":
            return stage.stage
    if app.current_stage in {stage.stage for stage in ordered_rows}:
        return app.current_stage
    if last_completed_idx >= 0:
        return ordered_rows[last_completed_idx].stage
    return ordered_rows[0].stage if ordered_rows else None


def _reached_stage_index(
    app: Application,
    stages: list[ApplicationStage] | None = None,
) -> int:
    """返回投递记录实际到达过的最高阶段索引，用于漏斗统计。"""
    stage_rows = app.stages if stages is None else stages
    ordered_rows = _ordered_stage_rows(stage_rows)
    if app.status == "已完成":
        return len(ordered_rows) - 1 if ordered_rows else -1
    reached = [
        idx for idx, stage in enumerate(ordered_rows)
        if stage.status in ("completed", "current")
    ]
    if app.status == "已淘汰":
        rejected_idx = next(
            (idx for idx, stage in enumerate(ordered_rows) if stage.stage == app.rejected_stage),
            None,
        )
        if rejected_idx is not None:
            reached.append(rejected_idx)
    if reached:
        return max(reached)
    return next(
        (idx for idx, stage in enumerate(ordered_rows) if stage.stage == app.current_stage),
        -1,
    )


def _serialize_app(
    a: Application,
    stages: list[ApplicationStage] | None = None,
    job_url: str | None = None,
) -> dict:
    stage_rows = a.stages if stages is None else stages
    ordered_stages = [_serialize_stage(stage) for stage in _ordered_stage_rows(stage_rows)]
    if job_url is None:
        # 列表和单条查询会预加载 job；不要因为历史数据没有岗位关联而额外
        # 触发一次隐式查询。
        job = a.__dict__.get("job")
        job_url = job.url if job else None
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
        "current_stage": _effective_current_stage(a, stage_rows),
        "job_url": job_url,
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
    job = None
    if job_id:
        job = db.query(Job).filter(Job.id == job_id, Job.group_id == group.id).first()
        if not job:
            raise HTTPException(404, "当前群组中没有这个岗位")
    else:
        # 从「新增投递」手动录入时也尝试按当前岗位库的公司和岗位精确匹配，
        # 这样不经过岗位卡片创建的记录同样能带出真实投递链接。
        job = db.query(Job).filter(
            Job.group_id == group.id,
            Job.company == company,
            Job.title == title,
            Job.url.isnot(None),
            Job.url != "",
        ).order_by(
            desc(Job.is_active),
            desc(Job.updated_at),
            desc(Job.id),
        ).first()
        if job:
            job_id = job.id

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

    # 创建默认流程阶段。把阶段对象保留在内存中，提交后直接序列化，
    # 避免远程 PostgreSQL 再执行 refresh + lazy-load 的往返查询。
    stages = []
    for i, stage_name in enumerate(STAGES):
        stage = ApplicationStage(
            application_id=app.id,
            stage=stage_name,
            position=i,
            status="completed" if i == 0 else "pending",
            schedule_type="exact",
            completed_at=dt.datetime.now() if i == 0 else None,
        )
        stages.append(stage)
    db.add_all(stages)

    db.commit()
    return _serialize_app(app, stages, job.url if job else None)


# GET /api/applications - 获取所有投递记录
@router.get("")
def list_applications(status: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有投递记录，每条记录带上所有阶段信息。"""
    q = db.query(Application).options(
        selectinload(Application.stages),
        selectinload(Application.job),
    ).filter(
        Application.user_id == user.id
    )
    if status:
        q = q.filter(Application.status == status)
    rows = q.order_by(
        desc(Application.applied_at).nullslast(),
        desc(Application.updated_at),
        desc(Application.id),
    ).all()
    return [_serialize_app(a) for a in rows]


# GET /api/applications/offers/list - 获取所有已拿到 Offer 的投递记录
@router.get("/offers/list")
def list_offers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """获取所有已拿到 Offer 的投递记录"""
    apps = db.query(Application).options(
        selectinload(Application.stages),
        selectinload(Application.job),
    ).filter(
        Application.status == "已完成", Application.user_id == user.id
    ).order_by(
        desc(Application.applied_at).nullslast(),
        desc(Application.updated_at),
        desc(Application.id),
    ).all()
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
    apps = db.query(Application).options(selectinload(Application.stages)).filter(
        Application.user_id == user.id
    ).all()
    by_stage = {s: 0 for s in ("投递", "简历筛选", "测评", "面试", "Offer")}
    by_status = {"进行中": 0, "已淘汰": 0, "已完成": 0}
    for a in apps:
        if a.status == "已淘汰":
            by_status["已淘汰"] += 1
        elif a.status == "已完成":
            by_status["已完成"] += 1
        else:
            by_status["进行中"] += 1
        if a.status not in ("已淘汰", "已完成"):
            current = _effective_current_stage(a, a.stages)
            if current:
                bucket = stage_statistics_bucket(current)
                by_stage.setdefault(bucket, 0)
                by_stage[bucket] += 1

    def _reached_named(matcher) -> int:
        """按每条投递的自定义顺序统计到达过某类阶段的数量。"""
        count = 0
        for a in apps:
            rows = _ordered_stage_rows(a.stages)
            target_idx = next(
                (idx for idx, row in enumerate(rows) if matcher(row.stage)),
                None,
            )
            if target_idx is not None and _reached_stage_index(a, rows) >= target_idx:
                count += 1
        return count

    return {
        "total": len(apps),
        "by_status": by_status,
        "by_stage": by_stage,
        "funnel": {
            "投递": _reached_named(lambda name: name == "投递"),
            "简历筛选": _reached_named(lambda name: name == "简历筛选"),
            "测评": _reached_named(is_assessment_stage),
            "面试": _reached_named(is_interview_stage),
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
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    return _serialize_app(app)


# PATCH /api/applications/{id} - 更新投递记录基本信息
@router.patch("/{app_id}")
def update_application(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新投递记录基本信息。"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
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


# PATCH /api/applications/{id}/workflow - 更新某条投递的流程顺序与阶段
@router.patch("/{app_id}/workflow")
def update_workflow(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """编辑单条投递的流程，保留已经产生的阶段历史。"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    raw_stages = body.get("stages") if isinstance(body, dict) else None
    if not isinstance(raw_stages, list) or not raw_stages:
        raise HTTPException(400, "至少保留一个流程环节")
    if len(raw_stages) > 20:
        raise HTTPException(400, "一条投递最多支持 20 个流程环节")

    existing_by_id = {stage.id: stage for stage in (app.stages or []) if stage.id is not None}
    submitted_ids: set[int] = set()
    seen_names: set[str] = set()
    ordered: list[ApplicationStage] = []

    for position, item in enumerate(raw_stages):
        if not isinstance(item, dict):
            raise HTTPException(400, "流程环节格式不正确")
        name = item.get("stage")
        if not isinstance(name, str):
            raise HTTPException(400, "流程环节名称不能为空")
        name = name.strip()
        if not name or len(name) > 50:
            raise HTTPException(400, "流程环节名称需为 1-50 个字符")
        if name in seen_names:
            raise HTTPException(400, f"流程环节不能重名：{name}")
        seen_names.add(name)

        raw_id = item.get("id")
        if raw_id in (None, ""):
            stage = ApplicationStage(
                application_id=app.id,
                stage=name,
                position=position,
                status="pending",
                schedule_type="exact",
            )
            app.stages.append(stage)
        else:
            try:
                stage_id = int(raw_id)
            except (TypeError, ValueError):
                raise HTTPException(400, "流程环节 id 不正确")
            if stage_id in submitted_ids:
                raise HTTPException(400, "同一个流程环节不能重复提交")
            stage = existing_by_id.get(stage_id)
            if not stage:
                raise HTTPException(400, "流程环节不属于当前投递记录")
            submitted_ids.add(stage_id)
            old_name = stage.stage
            if old_name != name:
                if app.current_stage == old_name:
                    app.current_stage = name
                if app.rejected_stage == old_name:
                    app.rejected_stage = name
                stage.stage = name
            stage.position = position
        ordered.append(stage)

    # 只有尚未开始且没有任何时间/备注的阶段才能删除，避免误删历史。
    for stage in app.stages or []:
        if stage.id in submitted_ids or stage.id is None:
            continue
        if _stage_has_history(stage):
            raise HTTPException(400, f"「{stage.stage}」已有记录，不能删除；可以改为跳过")
        db.delete(stage)

    # 已拿到 Offer 后如果新增了待进行环节，自动重新打开流程。
    if app.status == "已完成" and any(stage.status in ("pending", "current") for stage in ordered):
        app.status = "进行中"
    _sync_current_stage(app, db, ordered)
    db.flush()
    db.commit()
    return _serialize_app(app, ordered)


# PATCH /api/applications/{id}/stage/{stage_name} - 更新某个阶段
@router.patch("/{app_id}/stage/{stage_name}")
def update_stage(app_id: int, stage_name: str, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """更新某个阶段的信息。"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    stage = next((item for item in (app.stages or []) if item.stage == stage_name), None)
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
            raise HTTPException(400, "时间类型不正确")
        stage.schedule_type = schedule_type
    elif _deadline_capable_stage(stage_name) and body.get("deadline_at"):
        # 兼容只提交截止时间的旧客户端。
        stage.schedule_type = "deadline"

    if not _deadline_capable_stage(stage_name):
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
        if stage.status == "current":
            # 一个投递同时只保留一个真实的进行中阶段。
            for other in app.stages or []:
                if other is not stage and other.status == "current":
                    other.status = "pending"
        # 当 status 改为 completed 时自动设 completed_at
        if body["status"] == "completed" and not stage.completed_at:
            stage.completed_at = dt.datetime.now()
        # 更新 Application 的 current_stage 为最新的 completed 阶段
        _sync_current_stage(app, db)

    db.commit()
    return _serialize_app(app)


# POST /api/applications/{id}/advance - 推进到下一阶段
@router.post("/{app_id}/advance")
def advance_stage(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """推进到下一阶段：将当前阶段标记为 completed，下一个阶段设为 current。"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    # 兼容旧数据：如果缓存字段没有跟着阶段记录更新，先以真实阶段状态为准。
    ordered = _ordered_stage_rows(app.stages)
    _sync_current_stage(app, db, ordered)
    current_stage = next((stage for stage in ordered if stage.status == "current"), None)
    if not current_stage:
        current_stage = next((stage for stage in ordered if stage.stage == app.current_stage), None)
    current_idx = ordered.index(current_stage) if current_stage in ordered else None

    if current_idx is None or current_stage is None:
        raise HTTPException(400, f"当前阶段 '{app.current_stage}' 无法识别")

    current_stage.status = "completed"
    if not current_stage.completed_at:
        current_stage.completed_at = dt.datetime.now()

    # 找到当前阶段之后第一个没有被跳过的环节。
    next_stage = next(
        (stage for stage in ordered[current_idx + 1:] if stage.status != "skipped"),
        None,
    )
    if not next_stage:
        # 已经完成自定义流程的最后一个阶段。
        app.status = "已完成"
        app.current_stage = current_stage.stage
        db.commit()
        return _serialize_app(app)

    next_stage.status = "current"
    app.current_stage = next_stage.stage
    db.commit()
    return _serialize_app(app)


def _sync_current_stage(
    app: Application,
    db: Session,
    stages: list[ApplicationStage] | None = None,
):
    """根据实际阶段状态更新 Application.current_stage 缓存。"""
    ordered = _ordered_stage_rows(app.stages if stages is None else stages)
    current_stage = next((stage for stage in ordered if stage.status == "current"), None)
    if current_stage:
        app.current_stage = current_stage.stage
        return
    last_completed_idx = max(
        (idx for idx, stage in enumerate(ordered) if stage.status == "completed"),
        default=-1,
    )
    next_stage = next(
        (stage for stage in ordered[last_completed_idx + 1:] if stage.status != "skipped"),
        None,
    )
    if next_stage:
        app.current_stage = next_stage.stage
    elif last_completed_idx >= 0:
        app.current_stage = ordered[last_completed_idx].stage
    elif ordered:
        app.current_stage = ordered[0].stage


# POST /api/applications/{id}/rollback - 回退到指定阶段
@router.post("/{app_id}/rollback")
def rollback_stage(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """回退到指定阶段：将该阶段及后续阶段全部重置为 pending。"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")

    target_stage = body.get("stage")
    ordered = _ordered_stage_rows(app.stages)
    stage_names = [stage.stage for stage in ordered]
    if not target_stage or target_stage not in stage_names:
        raise HTTPException(400, "无效的阶段名")

    target_idx = stage_names.index(target_stage)

    # 将目标阶段及之后的阶段全部重置为 pending
    for stage in ordered[target_idx:]:
        stage.status = "pending"
        stage.completed_at = None

    # 将目标阶段之前最后一个标记为 completed（如果有的话）
    if target_idx > 0:
        prev = ordered[target_idx - 1]
        if prev and prev.status != "completed":
            prev.status = "completed"
            if not prev.completed_at:
                prev.completed_at = dt.datetime.now()

    # 更新 current_stage
    _sync_current_stage(app, db, ordered)
    # 如果之前是淘汰或已完成状态，回退即视为重新进行。
    if app.status in ("已淘汰", "已完成"):
        app.status = "进行中"
        if app.rejected_stage:
            app.rejected_stage = None

    db.commit()
    return _serialize_app(app)


@router.post("/{app_id}/reject")
def reject_application(app_id: int, body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """标记投递为已淘汰"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    if "stage" not in body:
        _sync_current_stage(app, db)
    else:
        valid_stages = {stage.stage for stage in (app.stages or [])}
        if body.get("stage") not in valid_stages:
            raise HTTPException(400, "无效的阶段名")
    app.status = "已淘汰"
    app.rejected_stage = body.get("stage", app.current_stage)
    # 将被淘汰的阶段标记为 skipped
    stage = next((item for item in (app.stages or []) if item.stage == app.rejected_stage), None)
    if stage:
        stage.status = "skipped"
    db.commit()
    return _serialize_app(app)


@router.post("/{app_id}/restore")
def restore_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """恢复已淘汰的投递"""
    app = db.query(Application).options(
        joinedload(Application.stages),
        joinedload(Application.job),
    ).filter(
        Application.id == app_id, Application.user_id == user.id
    ).first()
    if not app:
        raise HTTPException(404, "投递记录不存在")
    old_stage = app.rejected_stage
    app.status = "进行中"
    app.rejected_stage = None
    if old_stage:
        stage = next((item for item in (app.stages or []) if item.stage == old_stage), None)
        if stage:
            stage.status = "pending"
        _sync_current_stage(app, db)
    db.commit()
    return _serialize_app(app)
