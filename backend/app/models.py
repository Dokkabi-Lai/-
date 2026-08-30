"""SQLAlchemy 模型定义。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import BASE_DIR, get_settings


class Base(DeclarativeBase):
    pass


# ---------- 用户 ----------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True, index=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    avatar_type: Mapped[str] = mapped_column(String(20), default="emoji")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    avatar_emoji: Mapped[str] = mapped_column(String(32), default="🌱")
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    major: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_roles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    target_cities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active_group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("groups.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # relationships
    resumes: Mapped[list["Resume"]] = relationship("Resume", back_populates="user")
    preferences: Mapped[list["Preference"]] = relationship("Preference", back_populates="user")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user")
    job_marks: Mapped[list["JobMark"]] = relationship("JobMark", back_populates="user")
    todos: Mapped[list["Todo"]] = relationship(
        "Todo", back_populates="user", cascade="all, delete-orphan"
    )


class Todo(Base):
    """用户个人待办；不绑定群组，避免切换岗位库时混淆个人任务。"""
    __tablename__ = "todos"
    __table_args__ = (
        Index("ix_todos_user_done_due", "user_id", "is_done", "due_at"),
        Index("ix_todos_user_source", "user_id", "source_type", "source_id"),
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_todo_user_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="其他", nullable=False)
    due_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="todos")


class Group(Base):
    """多人协作维护的岗位空间；投递记录仍属于个人。"""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    status: Mapped[str] = mapped_column(String(20), default="active")
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


class GroupInvite(Base):
    __tablename__ = "group_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


class JobMark(Base):
    """用户对岗位的个人标记（Pass / 收藏），互不影响。"""
    __tablename__ = "job_marks"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_mark"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    favorited: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="job_marks")


class EmailVerification(Base):
    """邮箱验证码记录。"""
    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


# ---------- 简历与画像 ----------

class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), default="默认简历")  # 版本名
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 解析出的纯文本
    structured: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # AI 解析的结构化数据
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())

    # relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="resumes")


class Preference(Base):
    """求职偏好（每个用户一条记录）。"""
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    desired_locations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["北京","上海"]
    desired_job_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    desired_industries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    min_salary: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # K
    max_company_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="preferences")


# ---------- 岗位 ----------

class Job(Base):
    """秋招岗位（Excel 导入）。"""
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_source"),
        Index("ix_jobs_group_active_close", "group_id", "is_active", "close_date"),
        Index("ix_jobs_group_created", "group_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("groups.id"), nullable=True, index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50))  # excel / manual
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    company_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    salary: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    open_date: Mapped[Optional[dt.date]] = mapped_column(DateTime, nullable=True)
    close_date: Mapped[Optional[dt.date]] = mapped_column(DateTime, nullable=True)
    close_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    apply_rule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    referrer_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 内推码
    favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)  # 标记不感兴趣
    batch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 批次：27届秋招、27届提前批等
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 原始抓取数据
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class SyncState(Base):
    """外部岗位源的最近同步状态。"""
    __tablename__ = "sync_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    deactivated_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


# ---------- 投递记录 ----------

class Application(Base):
    """投递记录。"""
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_user_updated", "user_id", "updated_at"),
        Index("ix_applications_user_applied", "user_id", "applied_at"),
        Index("ix_applications_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)  # nullable 以兼容老数据
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    channel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 投递渠道
    resume_id: Mapped[Optional[int]] = mapped_column(ForeignKey("resumes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="已投递")
    # 已投递/进行中/已淘汰/已完成
    current_stage: Mapped[str] = mapped_column(String(50), default="投递")
    applied_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    rejected_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 被淘汰的环节
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="applications")
    # 只读关联：投递记录保留岗位快照字段，同时可以拿到岗位库里的真实链接。
    job: Mapped[Optional["Job"]] = relationship("Job", foreign_keys=[job_id], viewonly=True)
    stages: Mapped[list["ApplicationStage"]] = relationship(
        "ApplicationStage", backref="application", cascade="all, delete-orphan"
    )


# ---------- 投递流程阶段 ----------

class ApplicationStage(Base):
    """投递流程中的每个阶段。"""
    __tablename__ = "application_stages"
    __table_args__ = (
        Index("ix_application_stages_application", "application_id"),
        Index("ix_application_stages_schedule", "scheduled_at"),
        Index(
            "ix_application_stages_deadline",
            "stage",
            "schedule_type",
            "deadline_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50))  # "投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer", "入职"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending" / "current" / "completed" / "skipped"
    scheduled_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)  # 安排的时间（同步到日历）
    schedule_type: Mapped[str] = mapped_column(String(20), default="exact", nullable=False)  # exact / deadline，主要用于笔试
    deadline_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)  # 截止前完成的时间
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    form: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 现场/线上
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


# ---------- AI 生成内容缓存 ----------

class AICache(Base):
    """缓存 AI 生成结果（匹配分析、简历优化建议等），避免重复调用。"""
    __tablename__ = "ai_cache"
    __table_args__ = (UniqueConstraint("kind", "target_id", "prompt_hash", name="uq_ai_cache"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))  # match / resume_optimize / intro
    target_id: Mapped[int] = mapped_column(Integer)  # job_id 或 position_id
    prompt_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


# ---------- 爬虫日志 ----------

class SpiderLog(Base):
    __tablename__ = "spider_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))  # success / failed
    count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ran_at: Mapped[dt.datetime] = mapped_column(DateTime, default=func.now())


# ---------- 数据库引擎与会话 ----------

_engine = None
_SessionLocal = None


def get_db_backend() -> str:
    """返回当前数据库类型：postgresql 或 sqlite。"""
    settings = get_settings()
    if settings.db.url:
        return "postgresql"
    return "sqlite"


def validate_database_config() -> None:
    """云端部署必须配置 DATABASE_URL，否则每次重启都会丢失用户数据。"""
    import logging
    import os

    settings = get_settings()
    if settings.db.url:
        return
    if os.environ.get("ALLOW_SQLITE", "").lower() in ("1", "true", "yes"):
        logging.getLogger(__name__).warning(
            "ALLOW_SQLITE is enabled; user data is stored in ephemeral SQLite."
        )
        return
    if str(BASE_DIR) == "/app" or os.environ.get("SUPABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is not set. Without Supabase PostgreSQL, the app falls back to "
            "container SQLite and all registered users are lost on every redeploy. "
            "Add DATABASE_URL (Session pooler + ?sslmode=require) in SnapDeploy env vars."
        )


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        # Use PostgreSQL if DATABASE_URL is set (Koyeb), otherwise SQLite
        if settings.db.url:
            db_url = settings.db.url
            if db_url.startswith("postgres://"):
                db_url = "postgresql://" + db_url[len("postgres://"):]
        else:
            db_path = BASE_DIR / settings.db.path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"
        engine_kwargs = {"echo": False, "pool_pre_ping": True}
        if "sqlite" in db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs.update(pool_size=3, max_overflow=2, pool_recycle=280)
        _engine = create_engine(db_url, **engine_kwargs)
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def _migrate_db(engine) -> None:
    """轻量迁移：为已有数据库补充新字段。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        with engine.begin() as conn:
            if "phone" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(20)"))
            if "email" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(200)"))
            user_columns = {
                "avatar_type": "VARCHAR(20)",
                "avatar_url": "VARCHAR(500)",
                "avatar_emoji": "VARCHAR(32)",
                "bio": "TEXT",
                "school": "VARCHAR(120)",
                "major": "VARCHAR(120)",
                "graduation_year": "INTEGER",
                "target_roles": "JSON",
                "target_cities": "JSON",
                "is_admin": "BOOLEAN",
                "active_group_id": "INTEGER",
                "updated_at": "TIMESTAMP",
            }
            for name, sql_type in user_columns.items():
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
            conn.execute(text(
                "UPDATE users SET avatar_type = COALESCE(avatar_type, 'emoji'), "
                "avatar_emoji = COALESCE(avatar_emoji, '🌱'), "
                "is_admin = COALESCE(is_admin, false)"
            ))
    if "jobs" in insp.get_table_names():
        job_cols = {c["name"] for c in insp.get_columns("jobs")}
        with engine.begin() as conn:
            if "company_type" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN company_type VARCHAR(50)"))
            if "apply_rule" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN apply_rule VARCHAR(100)"))
            if "close_date_text" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN close_date_text VARCHAR(100)"))
            if "is_active" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN is_active BOOLEAN"))
                conn.execute(text("UPDATE jobs SET is_active = true WHERE is_active IS NULL"))
            if "updated_at" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN updated_at TIMESTAMP"))
            if "group_id" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN group_id INTEGER"))
            if "created_by_id" not in job_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN created_by_id INTEGER"))
    if "application_stages" in insp.get_table_names():
        stage_cols = {c["name"] for c in insp.get_columns("application_stages")}
        with engine.begin() as conn:
            if "schedule_type" not in stage_cols:
                conn.execute(text("ALTER TABLE application_stages ADD COLUMN schedule_type VARCHAR(20) DEFAULT 'exact'"))
            if "deadline_at" not in stage_cols:
                conn.execute(text("ALTER TABLE application_stages ADD COLUMN deadline_at TIMESTAMP"))
            conn.execute(text("UPDATE application_stages SET schedule_type = 'exact' WHERE schedule_type IS NULL OR schedule_type = ''"))
    if "todos" in insp.get_table_names():
        todo_cols = {c["name"] for c in insp.get_columns("todos")}
        with engine.begin() as conn:
            if "source_type" not in todo_cols:
                conn.execute(text("ALTER TABLE todos ADD COLUMN source_type VARCHAR(30)"))
            if "source_id" not in todo_cols:
                conn.execute(text("ALTER TABLE todos ADD COLUMN source_id INTEGER"))


def _ensure_query_indexes(engine) -> None:
    """为已存在的数据库补建查询索引。

    ``Base.metadata.create_all`` 只会可靠地为新建表创建索引；老用户的
    数据库需要显式补建，否则升级后仍然会走全表扫描。
    """
    from sqlalchemy import text

    statements = (
        "CREATE INDEX IF NOT EXISTS ix_jobs_group_active_close "
        "ON jobs (group_id, is_active, close_date)",
        "CREATE INDEX IF NOT EXISTS ix_jobs_group_created "
        "ON jobs (group_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_applications_user_updated "
        "ON applications (user_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_applications_user_applied "
        "ON applications (user_id, applied_at)",
        "CREATE INDEX IF NOT EXISTS ix_applications_user_status "
        "ON applications (user_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_application_stages_application "
        "ON application_stages (application_id)",
        "CREATE INDEX IF NOT EXISTS ix_application_stages_schedule "
        "ON application_stages (scheduled_at)",
        "CREATE INDEX IF NOT EXISTS ix_application_stages_deadline "
        "ON application_stages (stage, schedule_type, deadline_at)",
        "CREATE INDEX IF NOT EXISTS ix_todos_user_source "
        "ON todos (user_id, source_type, source_id)",
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _ensure_default_group(engine) -> None:
    """只做一次升级兼容，不把后续新用户加入旧的共享群组。

    旧版本没有个人岗位库，首次升级时需要把旧的无归属岗位放进系统群组。
    如果系统群组已经存在，则完整保留它现有的成员和信息；新用户会在注册或
    第一次访问时由 ``ensure_user_personal_group`` 创建自己的岗位库。
    """
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        group = db.query(Group).filter(Group.is_system.is_(True)).order_by(Group.id).first()
        users = db.query(User).order_by(User.id).all()
        if not group:
            owner = next((u for u in users if u.is_admin), users[0] if users else None)
            group = Group(name="默认岗位群", description="升级前的共享岗位库", owner_id=owner.id if owner else None, is_system=True)
            db.add(group)
            db.flush()
            # 只有真正创建旧系统群时，才把升级前已有用户迁入其中。
            for user in users:
                db.add(GroupMember(
                    group_id=group.id,
                    user_id=user.id,
                    role="owner" if user.id == group.owner_id else "member",
                ))
                if not user.active_group_id:
                    user.active_group_id = group.id
        db.query(Job).filter(Job.group_id.is_(None)).update(
            {Job.group_id: group.id}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def init_db():
    """建表。"""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_db(engine)
    _ensure_query_indexes(engine)
    _ensure_default_group(engine)


def get_db():
    """FastAPI 依赖：获取数据库会话。"""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
