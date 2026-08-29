"""用户认证、个人资料与头像。"""
from __future__ import annotations

import hashlib
import re

import bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, get_db
from ..services.avatar_service import save_avatar
from ..services.group_service import ensure_user_personal_group
from .deps import create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

_SALT = "pt-autumn-2026"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_EMOJIS = {"🌱", "🎯", "🚀", "🍊", "🦊", "🐳", "🌻", "🪐", "🧭", "💡", "📚", "☕", "🚗", "🌧️"}


def _legacy_hash(pw: str) -> str:
    return hashlib.sha256((_SALT + pw).encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """返回 (是否匹配, 是否为需要升级的旧哈希)。"""
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode(), stored.encode()), False
        except ValueError:
            return False, False
    return stored == _legacy_hash(password), True


def _is_admin(user: User) -> bool:
    return bool(user.is_admin or (user.email or "").lower() in set(get_settings().app.admin_emails))


def _user_payload(user: User, include_token: bool = False) -> dict:
    payload = {
        "id": user.id,
        "username": user.username,
        "email": user.email or user.username,
        "nickname": user.nickname,
        "avatar_type": user.avatar_type or "emoji",
        "avatar_url": user.avatar_url,
        "avatar_emoji": user.avatar_emoji or "🌱",
        "bio": user.bio,
        "school": user.school,
        "major": user.major,
        "graduation_year": user.graduation_year,
        "target_roles": user.target_roles or [],
        "target_cities": user.target_cities or [],
        "is_admin": _is_admin(user),
        "active_group_id": user.active_group_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    if include_token:
        payload["token"] = create_access_token(user.id)
    return payload


def _unique_username(db: Session, email: str) -> str:
    base = (email.split("@")[0][:40] or "user")
    username = base
    i = 1
    while db.query(User).filter(User.username == username).first():
        suffix = str(i)
        username = f"{base[:50 - len(suffix)]}{suffix}"
        i += 1
    return username


@router.post("/register")
def register(body: dict, db: Session = Depends(get_db)):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    nickname = (body.get("nickname") or "").strip()
    avatar_emoji = (body.get("avatar_emoji") or "🌱").strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "请输入正确的邮箱")
    if len(password) < 8:
        raise HTTPException(400, "密码至少 8 位")
    if len(password.encode()) > 72:
        raise HTTPException(400, "密码不能超过 72 个字节")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "该邮箱已注册，请直接登录")
    user = User(
        username=_unique_username(db, email),
        email=email,
        password_hash=hash_password(password),
        nickname=nickname or email.split("@")[0],
        avatar_type="emoji",
        avatar_emoji=avatar_emoji if avatar_emoji in ALLOWED_EMOJIS else "🌱",
        is_admin=email in set(get_settings().app.admin_emails),
    )
    db.add(user)
    db.flush()
    ensure_user_personal_group(db, user)
    db.commit()
    db.refresh(user)
    return _user_payload(user, include_token=True)


@router.post("/login")
def login(body: dict, db: Session = Depends(get_db)):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        raise HTTPException(400, "请输入邮箱和密码")
    user = db.query(User).filter(User.email == email).first()
    valid, legacy = (
        verify_password(password, user.password_hash)
        if user and user.password_hash and len(password.encode()) <= 72
        else (False, False)
    )
    if not valid:
        raise HTTPException(401, "邮箱或密码错误")
    if legacy:
        user.password_hash = hash_password(password)
        db.commit()
    return _user_payload(user, include_token=True)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)


@router.patch("/me")
def update_me(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    text_fields = {
        "nickname": 50,
        "bio": 500,
        "school": 120,
        "major": 120,
    }
    for field, limit in text_fields.items():
        if field in body:
            value = str(body.get(field) or "").strip()
            setattr(user, field, value[:limit] or None)
    if "graduation_year" in body:
        raw_year = body.get("graduation_year")
        if raw_year in (None, ""):
            user.graduation_year = None
        else:
            try:
                year = int(raw_year)
            except (TypeError, ValueError):
                raise HTTPException(400, "毕业年份格式不正确")
            if year < 2000 or year > 2100:
                raise HTTPException(400, "毕业年份格式不正确")
            user.graduation_year = year
    for field in ("target_roles", "target_cities"):
        if field in body:
            values = body.get(field) or []
            if not isinstance(values, list):
                raise HTTPException(400, f"{field} 必须是列表")
            setattr(user, field, [str(v).strip()[:50] for v in values if str(v).strip()][:12])
    if "avatar_emoji" in body:
        emoji = str(body.get("avatar_emoji") or "").strip()
        if emoji not in ALLOWED_EMOJIS:
            raise HTTPException(400, "请选择提供的表情头像")
        user.avatar_type = "emoji"
        user.avatar_emoji = emoji
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        url = save_avatar(user.id, await file.read(), file.content_type or "", file.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    user.avatar_type = "upload"
    user.avatar_url = url
    db.commit()
    db.refresh(user)
    return _user_payload(user)
