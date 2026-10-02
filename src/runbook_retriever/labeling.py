"""Storage and summaries for the human review queues (used by ``review/streamlit_app.py``).

Labels are append-only JSONL files in ``data/labels/<task>.jsonl``; the latest line for an
item id wins, so relabeling never loses history. Items are matched to labels by id, so
regenerating queues never invalidates finished work.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from runbook_retriever.io import read_jsonl

Task = Literal["test_pairs", "so_questions", "train_audit", "negatives_audit", "spot_check"]
TASKS: tuple[Task, ...] = (
    "test_pairs",
    "so_questions",
    "train_audit",
    "negatives_audit",
    "spot_check",
)

# Verdict values per task.
TEST_VERDICTS = ("correct", "wrong", "ambiguous")
AUDIT_VERDICTS = ("correct", "wrong")
NEGATIVE_VERDICTS = ("true_negative", "false_negative")


class LabelStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._labels: dict[str, dict[str, Any]] = {}
        if path.exists():
            for row in read_jsonl(path):
                self._labels[row["id"]] = row

    def get(self, item_id: str) -> dict[str, Any] | None:
        return self._labels.get(item_id)

    def put(self, item_id: str, label: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        row = {"id": item_id, "labeled_at": now, **label}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._labels[item_id] = row
        return row

    def labeled_ids(self) -> set[str]:
        return set(self._labels)

    def all(self) -> dict[str, dict[str, Any]]:
        return dict(self._labels)


def load_queue(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path)) if path.exists() else []


def first_unlabeled(queue: list[dict[str, Any]], labeled: set[str]) -> int:
    return next((i for i, item in enumerate(queue) if item["id"] not in labeled), len(queue))


@dataclass(frozen=True)
class TaskSummary:
    total: int
    labeled: int
    counts: dict[str, int]

    @property
    def done(self) -> bool:
        return self.total > 0 and self.labeled >= self.total


def summarize(queue: list[dict[str, Any]], labels: dict[str, dict[str, Any]]) -> TaskSummary:
    ids = {item["id"] for item in queue}
    mine = [lab for item_id, lab in labels.items() if item_id in ids]
    counts: dict[str, int] = {}
    for lab in mine:
        key = lab.get("verdict") or ("mapped" if lab.get("relevant") else "no_match")
        counts[key] = counts.get(key, 0) + 1
    return TaskSummary(total=len(queue), labeled=len(mine), counts=counts)


def rate(summary: TaskSummary, key: str) -> float | None:
    """Share of labeled items with verdict ``key`` (None until something is labeled)."""
    return summary.counts.get(key, 0) / summary.labeled if summary.labeled else None
