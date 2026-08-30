"""个人待办接口。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc
from sqlalchemy.orm import Session

from ..models import Todo, User, get_db
from .deps import get_current_user


router = APIRouter(prefix="/api/todos", tags=["todos"])

TODO_CATEGORIES = ("评测", "面试准备", "面试", "投递", "材料", "其他")


def _parse_datetime(value, label: str = "截止时间") -> dt.datetime | None:
    if value in (None, ""):
        return None
    try:
        return dt.datetime.fromisoformat(str(value).strip().replace("Z", ""))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label}格式不正确")


def _category(value) -> str:
    category = str(value or "其他").strip()
    if category not in TODO_CATEGORIES:
        raise HTTPException(400, "待办分类不正确")
    return category


def query_todos(
    db: Session,
    user_id: int,
    limit: int = 100,
    include_done: bool = True,
) -> list[Todo]:
    """按待处理优先、截止时间优先返回个人待办。"""
    query = db.query(Todo).filter(Todo.user_id == user_id)
    if not include_done:
        query = query.filter(Todo.is_done.is_(False))
    return query.order_by(
        Todo.is_done.asc(),
        case((Todo.due_at.is_(None), 1), else_=0),
        Todo.due_at.asc(),
        desc(Todo.created_at),
        desc(Todo.id),
    ).limit(max(1, min(limit, 200))).all()


def serialize_todo(todo: Todo) -> dict:
    return {
        "id": todo.id,
        "title": todo.title,
        "category": todo.category or "其他",
        "due_at": todo.due_at.isoformat() if todo.due_at else None,
        "notes": todo.notes,
        "is_done": bool(todo.is_done),
        "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
        "created_at": todo.created_at.isoformat() if todo.created_at else None,
        "updated_at": todo.updated_at.isoformat() if todo.updated_at else None,
    }


@router.get("")
def list_todos(
    include_done: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return [
        serialize_todo(todo)
        for todo in query_todos(db, user.id, include_done=include_done)
    ]


@router.post("")
def create_todo(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "待办标题不能为空")
    if len(title) > 200:
        raise HTTPException(400, "待办标题不能超过 200 个字符")

    notes = body.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise HTTPException(400, "备注格式不正确")

    todo = Todo(
        user_id=user.id,
        title=title,
        category=_category(body.get("category")),
        due_at=_parse_datetime(body.get("due_at")),
        notes=notes.strip() if notes else None,
        is_done=False,
    )
    db.add(todo)
    db.commit()
    return serialize_todo(todo)


@router.patch("/{todo_id}")
def update_todo(
    todo_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(
        Todo.id == todo_id,
        Todo.user_id == user.id,
    ).first()
    if not todo:
        raise HTTPException(404, "待办不存在")

    if "title" in body:
        title = str(body.get("title") or "").strip()
        if not title:
            raise HTTPException(400, "待办标题不能为空")
        if len(title) > 200:
            raise HTTPException(400, "待办标题不能超过 200 个字符")
        todo.title = title
    if "category" in body and body.get("category") is not None:
        todo.category = _category(body.get("category"))
    if "due_at" in body:
        todo.due_at = _parse_datetime(body.get("due_at"))
    if "notes" in body:
        notes = body.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise HTTPException(400, "备注格式不正确")
        todo.notes = notes.strip() if notes else None
    if "is_done" in body:
        if not isinstance(body["is_done"], bool):
            raise HTTPException(400, "完成状态格式不正确")
        todo.is_done = body["is_done"]
        todo.completed_at = dt.datetime.now() if todo.is_done else None

    db.commit()
    return serialize_todo(todo)


@router.delete("/{todo_id}")
def delete_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(
        Todo.id == todo_id,
        Todo.user_id == user.id,
    ).first()
    if not todo:
        raise HTTPException(404, "待办不存在")
    db.delete(todo)
    db.commit()
    return {"ok": True}
