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
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import BASE_DIR, get_settings


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now()


# ---------- 用户 ----------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)  # bcrypt hashed
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    # relationships
    resumes: Mapped[list["Resume"]] = relationship("Resume", back_populates="user")
    preferences: Mapped[list["Preference"]] = relationship("Preference", back_populates="user")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user")


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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

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
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="preferences")


# ---------- 岗位 ----------

class Job(Base):
    """秋招岗位（全局共享的爬虫数据）。"""
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_job_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # nowcoder / company_xxx / manual
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    salary: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    open_date: Mapped[Optional[dt.date]] = mapped_column(DateTime, nullable=True)
    close_date: Mapped[Optional[dt.date]] = mapped_column(DateTime, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    referrer_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 内推码
    favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)  # 标记不感兴趣
    batch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 批次：27届秋招、27届提前批等
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 原始抓取数据
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ---------- 投递记录 ----------

class Application(Base):
    """投递记录。"""
    __tablename__ = "applications"

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
    applied_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    rejected_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 被淘汰的环节
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="applications")
    stages: Mapped[list["ApplicationStage"]] = relationship(
        "ApplicationStage", backref="application", cascade="all, delete-orphan"
    )


# ---------- 投递流程阶段 ----------

class ApplicationStage(Base):
    """投递流程中的每个阶段。"""
    __tablename__ = "application_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50))  # "投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer", "入职"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "pending" / "current" / "completed" / "skipped"
    scheduled_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)  # 安排的时间（同步到日历）
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    form: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 现场/线上
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ---------- 爬虫日志 ----------

class SpiderLog(Base):
    __tablename__ = "spider_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))  # success / failed
    count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ran_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


# ---------- 引擎与会话 ----------

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_path = BASE_DIR / settings.db.path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def init_db():
    """建表。"""
    Base.metadata.create_all(get_engine())


def get_db():
    """FastAPI 依赖：获取数据库会话。"""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
