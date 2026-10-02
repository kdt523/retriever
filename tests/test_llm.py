from __future__ import annotations

from pathlib import Path

import pytest

from runbook_retriever.cache import DiskCache
from runbook_retriever.config import Settings
from runbook_retriever.llm import (
    BadRequestError,
    CachedLLM,
    CacheMissError,
    CallBudgetExceededError,
    LLMError,
    RateLimitedError,
    RateLimiter,
    TransientLLMError,
    parse_json,
)


class FakeTransport:
    """Scripted transport: each entry is a response string or an exception to raise."""

    def __init__(self, script: list[str | Exception]) -> None:
        self.script = list(script)
        self.calls: list[str] = []

    def __call__(self, *, model: str, prompt: str, temperature: float, json_output: bool) -> str:
        self.calls.append(model)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make_llm(
    tmp_path: Path, script: list[str | Exception], **kw: object
) -> tuple[CachedLLM, FakeTransport, FakeClock]:
    transport = FakeTransport(script)
    clock = FakeClock()
    llm = CachedLLM(
        cache=DiskCache(tmp_path),
        transport=transport,
        models=["primary", "fallback"],
        rpm=60,
        sleep=clock.sleep,
        clock=clock,
        **kw,  # type: ignore[arg-type]
    )
    return llm, transport, clock


def test_cache_hit_skips_transport(tmp_path: Path) -> None:
    llm, transport, _ = make_llm(tmp_path, ['{"q": 1}'])
    first = llm.generate("p")
    second = llm.generate("p")
    assert (first.cached, second.cached) == (False, True)
    assert second.text == '{"q": 1}' and second.model == "primary"
    assert transport.calls == ["primary"]


def test_cache_key_depends_on_temperature(tmp_path: Path) -> None:
    llm, transport, _ = make_llm(tmp_path, ["a", "b"])
    assert llm.generate("p", temperature=0.2).text == "a"
    assert llm.generate("p", temperature=0.9).text == "b"
    assert len(transport.calls) == 2


def test_retries_then_fails_over(tmp_path: Path) -> None:
    script: list[str | Exception] = [RateLimitedError("429"), RateLimitedError("429"), "ok"]
    llm, transport, clock = make_llm(tmp_path, script, max_attempts=2)
    result = llm.generate("p")
    assert result.model == "fallback"
    assert transport.calls == ["primary", "primary", "fallback"]
    assert 4.0 in clock.sleeps and 8.0 in clock.sleeps  # exponential backoff


def test_fallback_answer_is_reused_from_cache(tmp_path: Path) -> None:
    llm, _, _ = make_llm(tmp_path, [TransientLLMError("503"), "ok"], max_attempts=1)
    llm.generate("p")
    llm2, transport2, _ = make_llm(tmp_path, [])
    assert llm2.generate("p").model == "fallback"
    assert transport2.calls == []


def test_bad_request_is_not_retried(tmp_path: Path) -> None:
    llm, transport, _ = make_llm(tmp_path, [BadRequestError("400")])
    with pytest.raises(BadRequestError):
        llm.generate("p")
    assert transport.calls == ["primary"]


def test_all_models_failing_raises(tmp_path: Path) -> None:
    llm, _, _ = make_llm(tmp_path, [TransientLLMError("x")] * 2, max_attempts=1)
    with pytest.raises(LLMError, match="all models failed"):
        llm.generate("p")


def test_call_budget(tmp_path: Path) -> None:
    llm, _, _ = make_llm(tmp_path, ["a", "b"], max_calls=1)
    llm.generate("p1")
    with pytest.raises(CallBudgetExceededError):
        llm.generate("p2")


def test_cache_only_mode_never_calls(tmp_path: Path) -> None:
    llm, transport, _ = make_llm(tmp_path, ["a"], mode="cache_only")
    with pytest.raises(CacheMissError):
        llm.generate("p")
    assert transport.calls == []


def test_from_settings_requires_key_only_in_live_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("RR_GEMINI_API_KEY", raising=False)
    live = Settings(_env_file=None, root=tmp_path, llm_mode="live")  # type: ignore[call-arg]
    with pytest.raises(LLMError, match="RR_GEMINI_API_KEY"):
        CachedLLM.from_settings(live, "queries")
    offline = Settings(_env_file=None, root=tmp_path, llm_mode="cache_only")  # type: ignore[call-arg]
    llm = CachedLLM.from_settings(offline, "queries")
    assert llm.cache.directory == tmp_path / "data" / "cache" / "queries"
    with pytest.raises(CacheMissError):
        llm.generate("p")


def test_rate_limiter_spaces_calls() -> None:
    clock = FakeClock()
    limiter = RateLimiter(rpm=6, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.wait()
    assert clock.sleeps == [10.0, 10.0]


def test_parse_json_handles_fences() -> None:
    assert parse_json('```json\n{"a": [1]}\n```') == {"a": [1]}
    assert parse_json('[{"q": "x"}]') == [{"q": "x"}]
