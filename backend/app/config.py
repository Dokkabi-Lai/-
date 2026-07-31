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


class DBConfig(BaseModel):
    path: str = "data/app.db"
    url: str = ""  # PostgreSQL connection URL from env var


class StorageConfig(BaseModel):
    resume_dir: str = "data/resumes"


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    llm: LLMConfig = LLMConfig()
    spider: SpiderConfig = SpiderConfig()
    db: DBConfig = DBConfig()
    storage: StorageConfig = StorageConfig()

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
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()
