from __future__ import annotations

from pathlib import Path

import pytest

from runbook_retriever.cache import DiskCache
from runbook_retriever.io import read_jsonl, sha256_file, stable_hash, write_jsonl


def test_jsonl_roundtrip_unicode(tmp_path: Path) -> None:
    rows = [{"q": "Back-off pulling image “app:v2”", "n": 1}, {"q": "OOMKilled", "n": 2}]
    path = tmp_path / "sub" / "x.jsonl"
    assert write_jsonl(path, rows) == 2
    assert list(read_jsonl(path)) == rows
    assert b"\r\n" not in path.read_bytes()


def test_read_jsonl_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\n{oops\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        list(read_jsonl(path))


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    write_jsonl(tmp_path / "x.jsonl", [{"a": 1}])
    assert [p.name for p in tmp_path.iterdir()] == ["x.jsonl"]


def test_stable_hash_ignores_key_order() -> None:
    assert stable_hash({"a": 1, "b": [1, 2]}) == stable_hash({"b": [1, 2], "a": 1})
    assert stable_hash({"a": 1}) != stable_hash({"a": 2})


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_disk_cache(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    key = DiskCache.key({"prompt": "p"})
    assert cache.get(key) is None
    assert key not in cache
    cache.put(key, {"text": "hello"})
    assert key in cache
    assert cache.get(key) == {"text": "hello"}
    assert (tmp_path / key[:2] / f"{key}.json").is_file()
