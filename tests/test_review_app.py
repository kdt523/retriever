"""Headless UI tests for the review app (streamlit.testing AppTest, no browser)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from runbook_retriever.config import REPO_ROOT, get_settings

APP = str(REPO_ROOT / "review" / "streamlit_app.py")
PAGES = [
    "app_pages/overview.py",
    "app_pages/test_pairs.py",
    "app_pages/so_questions.py",
    "app_pages/train_audit.py",
    "app_pages/negatives.py",
]


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A throwaway project root with a 2-chunk corpus and small review queues."""
    chunk: dict[str, Any] = {
        "source": "k8s_docs",
        "source_path": "x",
        "url": None,
        "title": "Debug Pods",
        "n_tokens": 20,
        "meta": {},
    }
    write_jsonl(
        tmp_path / "data" / "corpus.jsonl",
        [
            chunk
            | {
                "chunk_id": "k8s/a#000",
                "doc_id": "k8s/a",
                "section": "Crash",
                "text": "Pods crash, cost $5",
            },
            chunk
            | {
                "chunk_id": "k8s/b#000",
                "doc_id": "k8s/b",
                "section": "Pull",
                "text": "Image pull fails",
            },
        ],
    )
    review = tmp_path / "data" / "review"
    item = {"query": "pod keeps crashing", "chunk_id": "k8s/a#000"}
    write_jsonl(
        review / "test_pairs.jsonl",
        [
            item
            | {"id": "t1", "style": "symptom", "source": "k8s_docs", "candidates": ["k8s/b#000"]}
        ],
    )
    write_jsonl(
        review / "train_audit.jsonl",
        [item | {"id": "a1", "style": "symptom"}, item | {"id": "a2", "style": "how_to"}],
    )
    write_jsonl(review / "negatives_audit.jsonl", [item | {"id": "n1", "negative_id": "k8s/b#000"}])
    write_jsonl(
        review / "so_questions.jsonl",
        [
            {
                "id": "s1",
                "question": "Pod crashes",
                "query": "pod crashes",
                "author": "u",
                "dataset_row": 7,
                "candidates": ["k8s/a#000", "k8s/b#000"],
            }
        ],
    )
    monkeypatch.setenv("RR_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(REPO_ROOT / "review"))
    _reset()
    yield tmp_path
    _reset()


def _reset() -> None:
    """Forget settings, Streamlit caches (process-wide) and the imported page helpers."""
    get_settings.cache_clear()
    st.cache_data.clear()
    st.cache_resource.clear()
    sys.modules.pop("common", None)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(project: Path, page: str) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page(page).run()
    assert not at.exception, at.exception


def test_train_audit_click_saves_label_and_advances(project: Path) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page("app_pages/train_audit.py").run()
    at.button(key="a_wrong").click().run()
    assert not at.exception
    labels = (project / "data" / "labels" / "train_audit.jsonl").read_text(encoding="utf-8")
    row = json.loads(labels.splitlines()[0])
    assert (row["id"], row["verdict"]) == ("a1", "wrong")
    assert at.session_state["train_audit_idx"] == 1  # moved to the next unlabeled item


def test_test_pair_saves_extra_relevant_chunk(project: Path) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page("app_pages/test_pairs.py").run()
    at.checkbox(key="extra::t1::k8s/b#000").check().run()
    at.button(key="v_correct").click().run()
    assert not at.exception
    row = json.loads((project / "data" / "labels" / "test_pairs.jsonl").read_text(encoding="utf-8"))
    assert row["verdict"] == "correct" and row["also_relevant"] == ["k8s/b#000"]


def test_so_save_without_selection_does_not_save(project: Path) -> None:
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.switch_page("app_pages/so_questions.py").run()
    at.button(key="so_save").click().run()
    assert not at.exception
    assert not (project / "data" / "labels" / "so_questions.jsonl").exists()
    at.button(key="so_none").click().run()
    row = json.loads(
        (project / "data" / "labels" / "so_questions.jsonl").read_text(encoding="utf-8")
    )
    assert row["relevant"] == [] and row["dataset_row"] == 7
