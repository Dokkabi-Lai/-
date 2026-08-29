"""认证依赖：必须登录。"""
from __future__ import annotations

import datetime as dt

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Group, GroupMember, User, get_db
from ..services.group_service import (
    active_membership,
    ensure_user_personal_group,
    first_membership,
    is_platform_admin,
)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + dt.timedelta(days=settings.app.jwt_expire_days),
    }
    return jwt.encode(payload, settings.app.jwt_secret, algorithm="HS256")


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization:
        raise HTTPException(401, "请先登录")
    token = (
        authorization.replace("Bearer ", "").strip()
        if authorization.startswith("Bearer")
        else authorization.strip()
    )
    try:
        settings = get_settings()
        payload = jwt.decode(token, settings.app.jwt_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "登录已失效，请重新登录")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "用户不存在，请重新登录")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_platform_admin(user):
        raise HTTPException(403, "仅管理员可执行此操作")
    return user


def get_current_group(
    x_group_id: int | None = Header(None, alias="X-Group-Id"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Group:
    if x_group_id:
        membership = active_membership(db, user.id, x_group_id)
        if not membership and not is_platform_admin(user):
            raise HTTPException(403, "你不在这个群组中")
        group = db.get(Group, x_group_id)
        if not group:
            raise HTTPException(404, "群组不存在")
        return group

    group_id = user.active_group_id
    membership = active_membership(db, user.id, group_id) if group_id else None
    if not membership:
        membership = first_membership(db, user.id)
    if not membership:
        group = ensure_user_personal_group(db, user)
        db.commit()
        return group
    group = db.get(Group, membership.group_id)
    if not group:
        raise HTTPException(404, "群组不存在")
    return group


def require_group_owner(
    group: Group = Depends(get_current_group),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Group:
    member = active_membership(db, user.id, group.id)
    if not is_platform_admin(user) and (not member or member.role != "owner"):
        raise HTTPException(403, "仅群主可执行此操作")
    return group
