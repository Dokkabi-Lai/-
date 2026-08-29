"""配置加载：读取 config.yaml，支持环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class AppConfig(BaseModel):
    name: str = "WLB大作战"
    host: str = "127.0.0.1"
    port: int = 8000
    jwt_secret: str = "development-only-change-me-please-32bytes"
    jwt_expire_days: int = 30
    admin_emails: list[str] = []


class DBConfig(BaseModel):
    path: str = "data/app.db"
    url: str = ""


class StorageConfig(BaseModel):
    avatar_dir: str = "data/avatars"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "avatars"


class JobsConfig(BaseModel):
    excel_path: str = ""


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    db: DBConfig = DBConfig()
    storage: StorageConfig = StorageConfig()
    jobs: JobsConfig = JobsConfig()


def _load_yaml() -> dict[str, Any]:
    cfg_path = BASE_DIR / "config.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        data = _load_yaml()
        _settings = Settings(**data)
        env_db_url = os.environ.get("DATABASE_URL")
        if env_db_url:
            _settings.db.url = env_db_url
        env_jwt_secret = os.environ.get("JWT_SECRET")
        if env_jwt_secret:
            _settings.app.jwt_secret = env_jwt_secret
        env_admins = os.environ.get("ADMIN_EMAILS")
        if env_admins:
            _settings.app.admin_emails = [
                value.strip().lower() for value in env_admins.split(",") if value.strip()
            ]
        for env_key, attr in (
            ("SUPABASE_URL", "supabase_url"),
            ("SUPABASE_SERVICE_ROLE_KEY", "supabase_service_role_key"),
            ("SUPABASE_STORAGE_BUCKET", "supabase_bucket"),
        ):
            env_val = os.environ.get(env_key)
            if env_val:
                setattr(_settings.storage, attr, env_val)
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()
