"""JSONL and hashing helpers. Writes are atomic so a crash never leaves half a file."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {e}") from e
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno}: expected an object, got {type(row).__name__}")
            yield row


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Atomically write ``rows`` as JSONL. Returns the number of rows written."""
    count = 0

    def lines() -> Iterator[str]:
        nonlocal count
        for row in rows:
            count += 1
            yield json.dumps(row, ensure_ascii=False) + "\n"

    write_text_atomic(path, "".join(lines()))
    return count


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stable_hash(payload: Any) -> str:
    """sha256 of the canonical JSON form of ``payload`` (key order independent)."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
