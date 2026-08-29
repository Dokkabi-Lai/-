"""群组协作、邀请链接和成员管理。"""
from __future__ import annotations

import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Group, GroupInvite, GroupMember, User, get_db
from ..services.group_service import active_membership, group_payload, is_platform_admin
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["groups"])


def _group_for_member(db: Session, group_id: int, user: User) -> tuple[Group, GroupMember]:
    group = db.get(Group, group_id)
    member = active_membership(db, user.id, group_id)
    if not group or not member:
        raise HTTPException(404, "群组不存在或你已不在群组中")
    return group, member


def _require_owner(db: Session, group_id: int, user: User) -> tuple[Group, GroupMember]:
    group, member = _group_for_member(db, group_id, user)
    if member.role != "owner" and not is_platform_admin(user):
        raise HTTPException(403, "仅群主可执行此操作")
    return group, member


@router.get("/groups")
def list_groups(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(GroupMember, Group).join(Group, Group.id == GroupMember.group_id).filter(
        GroupMember.user_id == user.id,
        GroupMember.status == "active",
    ).order_by(Group.is_system.desc(), GroupMember.joined_at).all()
    group_ids = [group.id for _, group in rows]
    counts = {}
    if group_ids:
        counts = dict(
            db.query(GroupMember.group_id, func.count(GroupMember.id))
            .filter(GroupMember.group_id.in_(group_ids), GroupMember.status == "active")
            .group_by(GroupMember.group_id)
            .all()
        )
    return {
        "active_group_id": user.active_group_id,
        "items": [
            group_payload(db, group, user, member=member, member_count=counts.get(group.id, 0))
            for member, group in rows
        ],
    }


@router.post("/groups")
def create_group(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "请输入群组名称")
    group = Group(
        name=name[:100],
        description=str(body.get("description") or "").strip()[:500] or None,
        owner_id=user.id,
        is_system=False,
    )
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id, role="owner", status="active"))
    user.active_group_id = group.id
    db.commit()
    db.refresh(group)
    return group_payload(db, group, user)


@router.patch("/groups/{group_id}")
def update_group(
    group_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group, _ = _require_owner(db, group_id, user)
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "群组名称不能为空")
        group.name = name[:100]
    if "description" in body:
        group.description = str(body.get("description") or "").strip()[:500] or None
    db.commit()
    db.refresh(group)
    return group_payload(db, group, user)


@router.post("/groups/{group_id}/activate")
def activate_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group, _ = _group_for_member(db, group_id, user)
    user.active_group_id = group.id
    db.commit()
    return group_payload(db, group, user)


@router.get("/groups/{group_id}/members")
def list_members(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _group_for_member(db, group_id, user)
    rows = db.query(GroupMember, User).join(User, User.id == GroupMember.user_id).filter(
        GroupMember.group_id == group_id,
        GroupMember.status == "active",
    ).order_by(GroupMember.role.desc(), GroupMember.joined_at).all()
    return [{
        "user_id": member_user.id,
        "nickname": member_user.nickname,
        "email": member_user.email,
        "avatar_type": member_user.avatar_type,
        "avatar_url": member_user.avatar_url,
        "avatar_emoji": member_user.avatar_emoji,
        "role": member.role,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
    } for member, member_user in rows]


@router.delete("/groups/{group_id}/members/{member_user_id}")
def remove_member(
    group_id: int,
    member_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group, _ = _require_owner(db, group_id, user)
    if member_user_id == group.owner_id:
        raise HTTPException(400, "不能移除群主")
    membership = active_membership(db, member_user_id, group_id)
    if not membership:
        raise HTTPException(404, "成员不存在")
    membership.status = "removed"
    member_user = db.get(User, member_user_id)
    if member_user and member_user.active_group_id == group_id:
        fallback = db.query(GroupMember).filter(
            GroupMember.user_id == member_user_id,
            GroupMember.status == "active",
            GroupMember.group_id != group_id,
        ).first()
        member_user.active_group_id = fallback.group_id if fallback else None
    db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """群主删除群组：解散成员、下架岗位，不可删除系统默认群。"""
    from ..models import Job

    group, _ = _require_owner(db, group_id, user)
    if group.is_system:
        raise HTTPException(400, "系统默认群不能删除")

    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    member_user_ids = [m.user_id for m in members]
    for member in members:
        member.status = "left"
    for invite in db.query(GroupInvite).filter(
        GroupInvite.group_id == group_id,
        GroupInvite.revoked_at.is_(None),
    ).all():
        invite.revoked_at = dt.datetime.now()
    for job in db.query(Job).filter(Job.group_id == group_id, Job.is_active.is_(True)).all():
        job.is_active = False

    affected_users = db.query(User).filter(
        User.id.in_(member_user_ids),
        User.active_group_id == group_id,
    ).all()
    for member_user in affected_users:
        fallback = db.query(GroupMember).filter(
            GroupMember.user_id == member_user.id,
            GroupMember.status == "active",
            GroupMember.group_id != group_id,
        ).first()
        member_user.active_group_id = fallback.group_id if fallback else None

    group.name = f"{group.name}（已删除）"
    db.commit()
    return {"ok": True}


@router.post("/groups/{group_id}/leave")
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    group, member = _group_for_member(db, group_id, user)
    if member.role == "owner":
        raise HTTPException(400, "群主需要先转让群组，不能直接退出")
    member.status = "left"
    if user.active_group_id == group.id:
        fallback = db.query(GroupMember).filter(
            GroupMember.user_id == user.id,
            GroupMember.status == "active",
            GroupMember.group_id != group.id,
        ).first()
        user.active_group_id = fallback.group_id if fallback else None
    db.commit()
    return {"ok": True}


@router.post("/groups/{group_id}/invites")
def create_invite(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, group_id, user)
    invite = GroupInvite(
        group_id=group_id,
        token=secrets.token_urlsafe(32),
        created_by_id=user.id,
        expires_at=dt.datetime.now() + dt.timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    base = str(request.base_url).rstrip("/")
    return {
        "id": invite.id,
        "token": invite.token,
        "url": f"{base}/?invite={invite.token}",
        "expires_at": invite.expires_at.isoformat(),
    }


@router.delete("/groups/{group_id}/invites/{invite_id}")
def revoke_invite(
    group_id: int,
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_owner(db, group_id, user)
    invite = db.query(GroupInvite).filter_by(id=invite_id, group_id=group_id).first()
    if not invite:
        raise HTTPException(404, "邀请不存在")
    invite.revoked_at = dt.datetime.now()
    db.commit()
    return {"ok": True}


@router.get("/invites/{token}")
def preview_invite(token: str, db: Session = Depends(get_db)):
    invite = db.query(GroupInvite).filter(GroupInvite.token == token).first()
    if not invite or invite.revoked_at or invite.expires_at < dt.datetime.now():
        raise HTTPException(404, "邀请链接无效或已过期")
    group = db.get(Group, invite.group_id)
    inviter = db.get(User, invite.created_by_id)
    count = db.query(GroupMember).filter_by(group_id=invite.group_id, status="active").count()
    return {
        "group_id": group.id,
        "group_name": group.name,
        "description": group.description,
        "member_count": count,
        "inviter": inviter.nickname or inviter.email,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/invites/{token}/accept")
def accept_invite(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invite = db.query(GroupInvite).filter(GroupInvite.token == token).first()
    if not invite or invite.revoked_at or invite.expires_at < dt.datetime.now():
        raise HTTPException(404, "邀请链接无效或已过期")
    membership = db.query(GroupMember).filter_by(group_id=invite.group_id, user_id=user.id).first()
    if membership:
        membership.status = "active"
        membership.role = membership.role or "member"
    else:
        db.add(GroupMember(group_id=invite.group_id, user_id=user.id, role="member", status="active"))
    invite.use_count += 1
    user.active_group_id = invite.group_id
    db.commit()
    group = db.get(Group, invite.group_id)
    return group_payload(db, group, user)

