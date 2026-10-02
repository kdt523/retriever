"""Single source of project constants, paths and env-driven settings.

Everything that must be identical across training, evaluation and serving lives
here (most importantly ``QUERY_PREFIX``). Settings come from ``RR_*`` env vars
or a git-ignored ``.env`` at the repo root; nothing else reads ``os.environ``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

# --- Model constants (shared by train / eval / serve) ---------------------------------

BASE_MODEL: Final = "BAAI/bge-small-en-v1.5"

# BGE v1.5 retrieval instruction. Applied to queries only, never to corpus chunks.
# Changing this invalidates every trained model and every reported number.
QUERY_PREFIX: Final = "Represent this sentence for searching relevant passages: "

# Upper bound for a full chunk (title + section + text) in model tokens. Chunks are
# built to fit, so nothing is silently truncated at encode time.
MAX_SEQ_LENGTH: Final = 256


def format_query(query: str) -> str:
    """Return ``query`` with the BGE retrieval prefix (idempotent)."""
    query = query.strip()
    return query if query.startswith(QUERY_PREFIX) else QUERY_PREFIX + query


# --- Paths ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def splits(self) -> Path:
        return self.data / "splits"

    @property
    def corpus(self) -> Path:
        return self.data / "corpus.jsonl"

    @property
    def runbooks(self) -> Path:
        return self.root / "runbooks"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def runs_csv(self) -> Path:
        return self.results / "runs.csv"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def configs(self) -> Path:
        return self.root / "configs"


# --- Settings ------------------------------------------------------------------------

LLMMode = Literal["live", "cache_only"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RR_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root: Path = REPO_ROOT
    seed: int = 42

    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("RR_GEMINI_API_KEY", "GEMINI_API_KEY")
    )
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    # live: call the API on cache miss. cache_only: never touch the network (tests, reruns).
    llm_mode: LLMMode = "live"
    # Free-tier limits are low and change over time; stay under them by default.
    llm_rpm: int = Field(default=8, ge=1)
    # Hard cap on API calls per process, so a bug can't burn the daily quota.
    llm_max_calls: int = Field(default=200, ge=0)

    @property
    def paths(self) -> Paths:
        return Paths(self.root)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
