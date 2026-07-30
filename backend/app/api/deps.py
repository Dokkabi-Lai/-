"""认证依赖：从请求头提取当前用户。"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..models import User, get_db


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    """从 Authorization 头提取用户。头格式: 'Bearer <user_id>'"""
    if not authorization:
        raise HTTPException(401, "未登录")
    token = (
        authorization.replace("Bearer ", "").strip()
        if authorization.startswith("Bearer")
        else authorization.strip()
    )
    try:
        user_id = int(token)
    except (ValueError, TypeError):
        raise HTTPException(401, "无效的token")
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    return user
