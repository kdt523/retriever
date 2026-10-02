from __future__ import annotations

from pathlib import Path

import pytest

from runbook_retriever.config import QUERY_PREFIX, REPO_ROOT, Settings, format_query


def test_query_prefix_is_the_bge_v15_instruction() -> None:
    # Guard against accidental edits: every model and number depends on this string.
    assert QUERY_PREFIX == "Represent this sentence for searching relevant passages: "


def test_format_query_adds_prefix_once() -> None:
    once = format_query("  pod OOMKilled exit code 137 ")
    assert once == QUERY_PREFIX + "pod OOMKilled exit code 137"
    assert format_query(once) == once


def test_repo_root_contains_pyproject() -> None:
    assert (REPO_ROOT / "pyproject.toml").is_file()


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RR_ROOT", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("RR_LLM_MODE", "cache_only")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.paths.corpus == tmp_path / "data" / "corpus.jsonl"
    assert s.gemini_api_key is not None
    assert s.gemini_api_key.get_secret_value() == "dummy"
    assert "dummy" not in repr(s)
    assert s.llm_mode == "cache_only"


def test_settings_reject_bad_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RR_LLM_MODE", "yolo")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_network_is_blocked_but_loopback_allowed() -> None:
    import socket

    with pytest.raises(RuntimeError, match="network access is disabled"):
        socket.create_connection(("example.com", 443), timeout=1)
    a, b = socket.socketpair()  # loopback, used by asyncio on Windows
    a.close()
    b.close()
