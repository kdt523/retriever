"""Content-addressed JSON cache on disk (used for every LLM call)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runbook_retriever.io import stable_hash, write_text_atomic


class DiskCache:
    """Stores one JSON file per key under ``<dir>/<key[:2]>/<key>.json``."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def key(payload: Any) -> str:
        return stable_hash(payload)

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"corrupt cache entry {path}")
        return value

    def put(self, key: str, value: dict[str, Any]) -> None:
        write_text_atomic(self._path(key), json.dumps(value, ensure_ascii=False, indent=1))

    def __contains__(self, key: str) -> bool:
        return self._path(key).exists()
