from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import diskcache


class Cache:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._urls = diskcache.Cache(str(self.root / "urls"))
        self._llm = diskcache.Cache(str(self.root / "llm"))

    @staticmethod
    def _key(*parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def get_url(self, url: str) -> str | None:
        return self._urls.get(url)

    def set_url(self, url: str, html: str, ttl_seconds: int = 86400) -> None:
        self._urls.set(url, html, expire=ttl_seconds)

    def get_llm(self, model: str, prompt: str) -> Any | None:
        return self._llm.get(self._key(model, prompt))

    def set_llm(self, model: str, prompt: str, response: Any) -> None:
        self._llm.set(self._key(model, prompt), response)
