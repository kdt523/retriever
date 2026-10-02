"""The corpus record and its loader (``data/corpus.jsonl``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from runbook_retriever.config import format_passage
from runbook_retriever.io import read_jsonl

Source = Literal["k8s_docs", "runbook"]


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str  # "<doc_id>#<nnn>"
    doc_id: str  # unit for train/val/test splits: "k8s/<path>" or "runbook/<id>"
    source: Source
    source_path: str  # path in its source repo, POSIX style
    url: str | None  # public page for citations (k8s docs only)
    title: str
    section: str  # heading trail inside the page, "" for the intro
    text: str  # body only; embed format_passage(...) instead
    n_tokens: int  # tokens of the full passage incl. [CLS]/[SEP]
    meta: dict[str, Any] = {}  # runbook front matter (scope, tools, cautions, related)

    @property
    def passage(self) -> str:
        """Exactly what gets embedded."""
        return format_passage(self.title, self.section, self.text)


def load_corpus(path: Path) -> list[Chunk]:
    chunks = [Chunk.model_validate(row) for row in read_jsonl(path)]
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate chunk_id values")
    return chunks
