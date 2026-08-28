"""配置加载：读取 config.yaml，支持环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class LLMProviderConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class LLMConfig(BaseModel):
    provider: str = "kimi"
    kimi: LLMProviderConfig = LLMProviderConfig()
    deepseek: LLMProviderConfig = LLMProviderConfig()
    qwen: LLMProviderConfig = LLMProviderConfig()
    openai: LLMProviderConfig = LLMProviderConfig()
    ollama: LLMProviderConfig = LLMProviderConfig()


class SpiderConfig(BaseModel):
    enabled: bool = True
    cron_hour: int = 2
    cron_minute: int = 0
    sources: dict[str, bool] = {}


class AppConfig(BaseModel):
    name: str = "WLB大作战"
    host: str = "127.0.0.1"
    port: int = 8000
    jwt_secret: str = "development-only-change-me-please-32bytes"
    jwt_expire_days: int = 30
    admin_emails: list[str] = []


class DBConfig(BaseModel):
    path: str = "data/app.db"
    url: str = ""  # PostgreSQL connection URL from env var


class StorageConfig(BaseModel):
    resume_dir: str = "data/resumes"
    avatar_dir: str = "data/avatars"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "avatars"


class FeishuConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    spreadsheet_token: str = ""  # 表格链接或 token
    sheet_id: str = ""  # 留空则取第一个工作表
    sync_enabled: bool = False
    sync_hour: int = 6
    sync_minute: int = 0


class JobsConfig(BaseModel):
    excel_path: str = ""
    feishu: FeishuConfig = FeishuConfig()


class SmtpConfig(BaseModel):
    host: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    from_addr: str = ""
    from_name: str = "WLB大作战"
    use_ssl: bool = True
    use_tls: bool = False


class EmailConfig(BaseModel):
    code_ttl: int = 300
    code_length: int = 6
    send_interval: int = 60
    smtp: SmtpConfig = SmtpConfig()


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    llm: LLMConfig = LLMConfig()
    spider: SpiderConfig = SpiderConfig()
    db: DBConfig = DBConfig()
    storage: StorageConfig = StorageConfig()
    jobs: JobsConfig = JobsConfig()
    email: EmailConfig = EmailConfig()

    def llm_provider_config(self) -> LLMProviderConfig:
        """返回当前 provider 的配置。"""
        return getattr(self.llm, self.llm.provider)


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
        # 环境变量覆盖（部署时用，避免提交 API Key 到代码仓库）
        # 支持的 env vars:
        #   LLM_PROVIDER       - 覆盖 llm.provider
        #   LLM_API_KEY        - 覆盖当前 provider 的 api_key
        #   LLM_BASE_URL       - 覆盖当前 provider 的 base_url
        #   LLM_MODEL          - 覆盖当前 provider 的 model
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider:
            _settings.llm.provider = env_provider
        env_api_key = os.environ.get("LLM_API_KEY")
        if env_api_key:
            getattr(_settings.llm, _settings.llm.provider).api_key = env_api_key
        env_base_url = os.environ.get("LLM_BASE_URL")
        if env_base_url:
            getattr(_settings.llm, _settings.llm.provider).base_url = env_base_url
        env_model = os.environ.get("LLM_MODEL")
        if env_model:
            getattr(_settings.llm, _settings.llm.provider).model = env_model
        # PostgreSQL override from Koyeb
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
        for env_key, attr in (
            ("SMTP_HOST", "host"),
            ("SMTP_USER", "username"),
            ("SMTP_PASSWORD", "password"),
            ("SMTP_FROM", "from_addr"),
            ("SMTP_FROM_NAME", "from_name"),
        ):
            env_val = os.environ.get(env_key)
            if env_val:
                setattr(_settings.email.smtp, attr, env_val)
        env_smtp_port = os.environ.get("SMTP_PORT")
        if env_smtp_port:
            _settings.email.smtp.port = int(env_smtp_port)
        for env_key, attr in (
            ("FEISHU_APP_ID", "app_id"),
            ("FEISHU_APP_SECRET", "app_secret"),
            ("FEISHU_SPREADSHEET_TOKEN", "spreadsheet_token"),
            ("FEISHU_SHEET_ID", "sheet_id"),
        ):
            env_val = os.environ.get(env_key)
            if env_val:
                setattr(_settings.jobs.feishu, attr, env_val)
        env_feishu_sync = os.environ.get("FEISHU_SYNC_ENABLED")
        if env_feishu_sync:
            _settings.jobs.feishu.sync_enabled = env_feishu_sync.lower() in {"1", "true", "yes", "on"}
        if os.environ.get("FEISHU_SYNC_HOUR"):
            _settings.jobs.feishu.sync_hour = int(os.environ["FEISHU_SYNC_HOUR"])
        if os.environ.get("FEISHU_SYNC_MINUTE"):
            _settings.jobs.feishu.sync_minute = int(os.environ["FEISHU_SYNC_MINUTE"])
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()
