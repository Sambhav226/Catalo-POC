from __future__ import annotations

import json
import logging
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.tools.cache import Cache

log = logging.getLogger("llm")

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, model: str | None = None, cache: Cache | None = None):
        self.model = model or settings.openai_model
        self.cache = cache or Cache(settings.cache_dir)
        self._offline = settings.is_offline()
        self._client = None
        self.total_in_tokens = 0
        self.total_out_tokens = 0

        if not self._offline:
            from openai import OpenAI
            kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = OpenAI(**kwargs)

    def usage(self) -> dict:
        return {"input_tokens": self.total_in_tokens, "output_tokens": self.total_out_tokens}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _call_raw(self, system: str, user: str, json_mode: bool) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.1}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        if resp.usage:
            self.total_in_tokens += resp.usage.prompt_tokens or 0
            self.total_out_tokens += resp.usage.completion_tokens or 0
        return resp.choices[0].message.content or ""

    def chat(self, system: str, user: str) -> str:
        cache_key = f"chat::{system}\n---\n{user}"
        cached = self.cache.get_llm(self.model, cache_key)
        if cached is not None:
            return cached
        if self._offline:
            return _offline_stub_chat(system, user)
        out = self._call_raw(system, user, json_mode=False)
        self.cache.set_llm(self.model, cache_key, out)
        return out

    def structured_call(self, system: str, user: str, response_model: Type[T]) -> T:
        schema_str = json.dumps(response_model.model_json_schema(), indent=2)
        user_with_schema = (
            f"{user}\n\n"
            f"Return ONLY valid JSON matching this JSON Schema:\n{schema_str}"
        )
        cache_key = f"structured::{response_model.__name__}::{system}\n---\n{user_with_schema}"
        cached = self.cache.get_llm(self.model, cache_key)
        if cached is not None:
            try:
                return response_model.model_validate_json(cached)
            except ValidationError:
                pass

        if self._offline:
            fake = _offline_stub_structured(response_model, system, user)
            self.cache.set_llm(self.model, cache_key, fake.model_dump_json())
            return fake

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                raw = self._call_raw(system, user_with_schema, json_mode=True)
                obj = response_model.model_validate_json(raw)
                self.cache.set_llm(self.model, cache_key, obj.model_dump_json())
                return obj
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                user_with_schema += (
                    f"\n\nYour previous response failed validation: {e}. "
                    f"Return ONLY valid JSON."
                )
                log.warning("structured_call retry %d: %s", attempt + 1, e)
        raise RuntimeError(f"structured_call failed after 3 attempts: {last_err}")


def _offline_stub_chat(system: str, user: str) -> str:
    return "[offline-mode] LLM disabled. Set OPENAI_API_KEY to enable."


def _offline_stub_structured(model: Type[T], system: str, user: str) -> T:
    from src.tools.offline_stubs import build_offline_response
    return build_offline_response(model, system, user)
