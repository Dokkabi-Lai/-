"""LLM 抽象层。

所有实现都走 OpenAI 兼容的 chat/completions 接口格式，
换模型只需改 config.yaml 的 provider + api_key，代码不动。

用法:
    from app.llm import get_llm
    llm = get_llm()
    reply = llm.chat([{"role": "user", "content": "你好"}])
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from ..config import get_settings


class LLMError(Exception):
    pass


class BaseLLM:
    """统一接口。所有子类实现 chat()。"""

    name: str = "base"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        raise NotImplementedError


class OpenAICompatibleLLM(BaseLLM):
    """OpenAI 兼容格式客户端。

    Kimi / DeepSeek / 通义 / OpenAI / Ollama 都兼容此格式，
    区别仅在 base_url / api_key / model。所以用一个类即可覆盖全部。
    """

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        if not self.api_key:
            raise LLMError(
                f"未配置 {self.name} 的 api_key，请在 backend/config.yaml 中填写。"
            )
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            # 不同厂商字段名略有差异，多数兼容 response_format
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise LLMError(f"{self.name} API 返回错误 {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            raise LLMError(f"{self.name} API 请求失败: {e}") from e


# ---------- 工厂 ----------

_llm_cache: dict[str, BaseLLM] = {}


def get_llm() -> BaseLLM:
    """根据 config.yaml 当前 provider 返回 LLM 实例（带缓存）。"""
    settings = get_settings()
    provider = settings.llm.provider
    if provider in _llm_cache:
        return _llm_cache[provider]

    cfg = settings.llm_provider_config()
    llm = OpenAICompatibleLLM(
        name=provider,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
    )
    _llm_cache[provider] = llm
    return llm


def clear_llm_cache():
    """切换配置后清缓存。"""
    _llm_cache.clear()


# ---------- 便捷封装 ----------

def ask(
    prompt: str,
    system: str = "你是一个有用的助手。",
    temperature: float = 0.7,
    json_mode: bool = False,
) -> str:
    """单轮提问便捷方法。"""
    llm = get_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    return llm.chat(messages, temperature=temperature, json_mode=json_mode)


def ask_json(prompt: str, system: str = "你是一个有用的助手。请返回合法 JSON。") -> Any:
    """提问并解析 JSON 返回。若 json_mode 不被支持则尝试从文本提取。"""
    llm = get_llm()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    text = llm.chat(messages, temperature=0.3, json_mode=True)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取 ```json ... ``` 块
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise LLMError(f"无法解析为 JSON: {text[:200]}")
