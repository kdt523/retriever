"""Typed loader for ``configs/corpus.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from runbook_retriever.config import MAX_SEQ_LENGTH


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class K8sDocsConfig(_Strict):
    repo: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    docs_root: str
    examples_root: str
    include: list[str] = Field(min_length=1)
    exclude: list[str] = []


class ChunkingConfig(_Strict):
    max_tokens: int = Field(gt=0, le=MAX_SEQ_LENGTH)
    overlap_tokens: int = Field(ge=0)
    min_tokens: int = Field(ge=0)
    exclude_sections: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> ChunkingConfig:
        if self.overlap_tokens >= self.max_tokens // 2:
            raise ValueError("overlap_tokens must be < max_tokens / 2")
        return self


class CorpusConfig(_Strict):
    k8s_docs: K8sDocsConfig
    chunking: ChunkingConfig


def load_corpus_config(path: Path) -> CorpusConfig:
    return CorpusConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
