"""用户认证接口。"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import User, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def hash_password(pw: str) -> str:
    """简单密码哈希（个人项目够用）。"""
    return hashlib.sha256(pw.encode()).hexdigest()


@router.post("/register")
def register(body: dict, db: Session = Depends(get_db)):
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    nickname = body.get("nickname", "").strip() or username
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    if len(password) < 4:
        raise HTTPException(400, "密码至少4位")
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(409, "用户名已存在")
    user = User(username=username, password_hash=hash_password(password), nickname=nickname)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "nickname": user.nickname, "token": str(user.id)}


@router.post("/login")
def login(body: dict, db: Session = Depends(get_db)):
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or user.password_hash != hash_password(password):
        raise HTTPException(401, "用户名或密码错误")
    return {"id": user.id, "username": user.username, "nickname": user.nickname, "token": str(user.id)}
