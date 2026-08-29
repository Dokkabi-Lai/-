"""群组上下文和成员权限的共享逻辑。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Group, GroupMember, User


def ensure_user_default_group(db: Session, user: User) -> Group:
    """保留旧版本调用的共享默认群组助手。

    新注册用户不再调用这个函数，避免所有人自动进入同一个岗位库；老数据和
    外部兼容调用仍然可以显式使用它。
    """
    group = db.query(Group).filter(Group.is_system.is_(True)).order_by(Group.id).first()
    if not group:
        group = Group(
            name="默认岗位群",
            description="大家共同维护的岗位库",
            owner_id=user.id,
            is_system=True,
        )
        db.add(group)
        db.flush()
    if not group.owner_id:
        group.owner_id = user.id
    member = db.query(GroupMember).filter_by(group_id=group.id, user_id=user.id).first()
    if not member:
        member = GroupMember(
            group_id=group.id,
            user_id=user.id,
            role="owner" if group.owner_id == user.id else "member",
            status="active",
        )
        db.add(member)
    elif member.status != "active":
        member.status = "active"
    if not user.active_group_id:
        user.active_group_id = group.id
    db.flush()
    return group


def ensure_user_personal_group(db: Session, user: User) -> Group:
    """为没有岗位空间的用户创建一个只属于自己的岗位库。

    函数是幂等的：已有任意有效群组成员关系的用户不会被重新分配；这能保护
    旧用户当前的群组和成员信息，也让邀请加入群组的流程优先于个人库兜底。
    """
    membership = first_membership(db, user.id)
    if membership:
        group = db.get(Group, membership.group_id)
        if group:
            if not user.active_group_id:
                user.active_group_id = group.id
            db.flush()
            return group

    group = db.query(Group).filter(
        Group.owner_id == user.id,
        Group.is_system.is_(False),
        Group.name == "我的岗位库",
    ).order_by(Group.id).first()
    if not group:
        group = Group(
            name="我的岗位库",
            description="只有你自己可以访问的岗位库",
            owner_id=user.id,
            is_system=False,
        )
        db.add(group)
        db.flush()

    member = db.query(GroupMember).filter_by(group_id=group.id, user_id=user.id).first()
    if not member:
        db.add(GroupMember(
            group_id=group.id,
            user_id=user.id,
            role="owner",
            status="active",
        ))
    else:
        member.role = "owner"
        member.status = "active"
    user.active_group_id = group.id
    db.flush()
    return group


def active_membership(db: Session, user_id: int, group_id: int) -> GroupMember | None:
    return db.query(GroupMember).filter(
        GroupMember.user_id == user_id,
        GroupMember.group_id == group_id,
        GroupMember.status == "active",
    ).first()


def first_membership(db: Session, user_id: int) -> GroupMember | None:
    return db.query(GroupMember).filter(
        GroupMember.user_id == user_id,
        GroupMember.status == "active",
    ).order_by(GroupMember.joined_at, GroupMember.id).first()


def is_platform_admin(user: User) -> bool:
    return bool(user.is_admin or (user.email or "").lower() in set(get_settings().app.admin_emails))


def group_payload(db: Session, group: Group, user: User) -> dict:
    member = active_membership(db, user.id, group.id)
    count = db.query(GroupMember).filter(
        GroupMember.group_id == group.id,
        GroupMember.status == "active",
    ).count()
    platform_admin = is_platform_admin(user)
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "role": member.role if member else None,
        "member_count": count,
        "is_system": group.is_system,
        "is_owner": bool(platform_admin or (member and member.role == "owner")),
    }
