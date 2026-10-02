"""Cached, rate-limited Gemini client for offline data generation.

Every response is cached on disk keyed by (prompt, temperature, output mode), so
reruns are free and deterministic. The cache key deliberately excludes the model
name: if the fallback model answered, a rerun reuses that answer instead of
spending quota again. The model that answered is stored in the cache entry.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from runbook_retriever.cache import DiskCache
from runbook_retriever.config import LLMMode, Settings

log = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1


class LLMError(Exception):
    """Base class for LLM failures."""


class CacheMissError(LLMError):
    """Raised in ``cache_only`` mode when a prompt was never generated."""


class AllModelsExhaustedError(LLMError):
    """Every configured model hit its daily quota or is unavailable; stop the run."""


class CallBudgetExceededError(LLMError):
    """Raised when this process has used up ``llm_max_calls``."""


class RateLimitedError(LLMError):
    """HTTP 429 / RESOURCE_EXHAUSTED. Retried with backoff, then fails over."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


_RETRY_IN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.IGNORECASE)


def parse_retry_after(message: str) -> float | None:
    """Seconds from Gemini's "Please retry in 14h7m22.8s" hint, if present."""
    m = _RETRY_IN.search(message)
    if not m or not any(m.groups()):
        return None
    hours, minutes, seconds = (float(g) if g else 0.0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


class TransientLLMError(LLMError):
    """5xx or timeout. Retried with backoff, then fails over."""


class BadRequestError(LLMError):
    """4xx other than 429. Never retried."""


class ModelUnavailableError(LLMError):
    """404: the model does not exist for this key. Skip it and try the next model."""


# A 429 asking to wait longer than this is a daily quota, not a per-minute limit.
DAILY_QUOTA_RETRY_S = 300.0


class Transport(Protocol):
    def __call__(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float,
        json_output: bool,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Send one prompt and return the raw text response."""
        ...


class GeminiTransport:
    """Real transport over ``google-genai``. The client is created lazily."""

    def __init__(self, api_key: str, timeout_s: float = 120.0) -> None:
        self._api_key = api_key
        self._timeout_ms = int(timeout_s * 1000)
        self._client: Any = None

    def __call__(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float,
        json_output: bool,
        schema: dict[str, Any] | None = None,
    ) -> str:
        from google import genai
        from google.genai import errors, types

        if self._client is None:
            self._client = genai.Client(
                api_key=self._api_key, http_options=types.HttpOptions(timeout=self._timeout_ms)
            )
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if json_output else "text/plain",
            response_json_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = self._client.models.generate_content(
                model=model, contents=prompt, config=config
            )
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code == 429:
                raise RateLimitedError(str(e), parse_retry_after(str(e))) from e
            if code == 404:
                raise ModelUnavailableError(str(e)) from e
            if isinstance(code, int) and 400 <= code < 500:
                raise BadRequestError(str(e)) from e
            raise TransientLLMError(str(e)) from e
        except TimeoutError as e:
            raise TransientLLMError(str(e)) from e
        text = response.text
        if not text:
            raise TransientLLMError(f"empty response from {model}")
        return str(text)


class RateLimiter:
    """Spaces calls at least ``60 / rpm`` seconds apart. Thread-safe: each caller reserves
    the next free slot under a lock, then sleeps outside it."""

    def __init__(
        self,
        rpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = 60.0 / rpm
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = now if self._last is None else max(now, self._last + self.interval)
            self._last = slot
        if slot > now:
            self._sleep(slot - now)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    cached: bool


class CachedLLM:
    TRIP_AFTER = 2

    def __init__(
        self,
        *,
        cache: DiskCache,
        transport: Transport | None,
        models: Sequence[str],
        mode: LLMMode = "live",
        rpm: int = 8,
        max_calls: int = 200,
        max_attempts: int = 4,
        backoff_base_s: float = 4.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not models:
            raise ValueError("at least one model is required")
        self.cache = cache
        self.transport = transport
        self.models = list(models)
        self.mode = mode
        self.max_calls = max_calls
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.calls_made = 0
        self._budget_lock = threading.Lock()
        self.tripped: set[str] = set()
        self._rate_limit_streak: dict[str, int] = {}
        self._sleep = sleep
        self._limiter = RateLimiter(rpm, clock=clock, sleep=sleep)

    @classmethod
    def from_settings(cls, settings: Settings, namespace: str) -> CachedLLM:
        """Build a client whose cache lives in ``data/cache/<namespace>``."""
        transport: Transport | None = None
        if settings.llm_mode == "live":
            if settings.gemini_api_key is None:
                raise LLMError("RR_GEMINI_API_KEY is not set (or use RR_LLM_MODE=cache_only)")
            transport = GeminiTransport(settings.gemini_api_key.get_secret_value())
        return cls(
            cache=DiskCache(settings.paths.cache / namespace),
            transport=transport,
            models=settings.gemini_models,
            mode=settings.llm_mode,
            rpm=settings.llm_rpm,
            max_calls=settings.llm_max_calls,
        )

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        json_output: bool = True,
        schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "v": CACHE_SCHEMA_VERSION,
            "prompt": prompt,
            "temperature": temperature,
            "json_output": json_output,
        }
        if schema is not None:
            payload["schema"] = schema
        key = DiskCache.key(payload)
        hit = self.cache.get(key)
        if hit is not None:
            return LLMResult(text=str(hit["text"]), model=str(hit["model"]), cached=True)
        if self.mode == "cache_only" or self.transport is None:
            raise CacheMissError(f"no cached response for key {key[:12]}")

        last_error: LLMError | None = None
        for model in self.models:
            if model in self.tripped:
                continue
            rate_limited_every_attempt = True
            for attempt in range(self.max_attempts):
                with self._budget_lock:
                    if self.calls_made >= self.max_calls:
                        raise CallBudgetExceededError(f"reached llm_max_calls={self.max_calls}")
                    self.calls_made += 1
                self._limiter.wait()
                try:
                    text = self.transport(
                        model=model,
                        prompt=prompt,
                        temperature=temperature,
                        json_output=json_output,
                        schema=schema,
                    )
                except ModelUnavailableError as e:
                    last_error = e
                    self._trip(model, "not available for this key (404)")
                    break
                except (RateLimitedError, TransientLLMError) as e:
                    last_error = e
                    rate_limited_every_attempt &= isinstance(e, RateLimitedError)
                    retry_after = getattr(e, "retry_after_s", None)
                    if retry_after is not None and retry_after > DAILY_QUOTA_RETRY_S:
                        self._trip(
                            model, f"daily quota exhausted (retry in {retry_after / 3600:.1f}h)"
                        )
                        break
                    delay = min(self.backoff_base_s * 2**attempt, 60.0)
                    log.warning(
                        "llm %s attempt %d failed (%s); retrying in %.0fs",
                        model,
                        attempt + 1,
                        type(e).__name__,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                self.cache.put(key, {"text": text, "model": model, "prompt": prompt})
                with self._budget_lock:
                    self._rate_limit_streak[model] = 0
                return LLMResult(text=text, model=model, cached=False)
            if model in self.tripped:
                continue
            self._record_exhausted(model, rate_limited_every_attempt)
            log.warning("llm %s exhausted retries; failing over", model)
        if set(self.models) <= self.tripped:
            raise AllModelsExhaustedError(
                f"every model is out of quota or unavailable: {last_error}"
            )
        raise LLMError(f"all models failed; last error: {last_error}")

    def _trip(self, model: str, reason: str) -> None:
        with self._budget_lock:
            if model not in self.tripped:
                self.tripped.add(model)
                log.warning("llm %s %s; skipping it for this run", model, reason)

    def _record_exhausted(self, model: str, rate_limited: bool) -> None:
        """Circuit breaker: a model that is rate-limited on every attempt of TRIP_AFTER
        consecutive requests has most likely hit its daily quota; stop calling it."""
        with self._budget_lock:
            streak = self._rate_limit_streak.get(model, 0) + 1 if rate_limited else 0
            self._rate_limit_streak[model] = streak
            if streak >= self.TRIP_AFTER and model not in self.tripped:
                self.tripped.add(model)
                log.warning("llm %s keeps returning 429; skipping it for this run", model)

    def generate_json(
        self, prompt: str, *, temperature: float = 0.7, schema: dict[str, Any] | None = None
    ) -> Any:
        result = self.generate(prompt, temperature=temperature, json_output=True, schema=schema)
        return parse_json(result.text)


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_json(text: str) -> Any:
    """Parse model JSON output, tolerating a surrounding Markdown code fence."""
    match = _FENCE.match(text)
    return json.loads(match.group(1) if match else text)
