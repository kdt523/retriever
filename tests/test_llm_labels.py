from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runbook_retriever.config import Paths
from runbook_retriever.corpus import Chunk
from runbook_retriever.freeze_testset import with_spot_check
from runbook_retriever.labeling import LabelStore
from runbook_retriever.llm_labels import (
    LabelFormatError,
    agreement,
    export,
    extract_json_lines,
    import_answers,
    make_spot_check,
    to_label,
)


def chunk(cid: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        doc_id=cid.split("#")[0],
        source="k8s_docs",
        source_path="x",
        url=None,
        title="Title",
        section="Section",
        text=f"text of {cid}",
        n_tokens=5,
    )


TEST_ITEM: dict[str, Any] = {
    "id": "t1",
    "query": "pod keeps crashing",
    "chunk_id": "k8s/a#000",
    "style": "symptom",
    "source": "k8s_docs",
    "candidates": ["k8s/b#000", "k8s/c#000"],
}
SO_ITEM: dict[str, Any] = {
    "id": "s1",
    "question": "Why does my pod crash?",
    "query": "Why does my pod crash?",
    "author": "u",
    "dataset_row": 7,
    "candidates": ["k8s/a#000", "k8s/b#000"],
}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(tmp_path)
    review = p.data / "review"
    write_jsonl(review / "test_pairs.jsonl", [TEST_ITEM, TEST_ITEM | {"id": "t2"}])
    write_jsonl(review / "so_questions.jsonl", [SO_ITEM])
    write_jsonl(review / "train_audit.jsonl", [])
    write_jsonl(review / "negatives_audit.jsonl", [])
    return p


def answer(p: Paths, name: str, text: str) -> None:
    path = p.data / "llm_labeling" / "answers" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_extract_json_lines_ignores_fences_and_prose() -> None:
    text = 'Here you go:\n```jsonl\n{"id": "a", "verdict": "wrong"},\n{"id": "b"}\n```\nDone.'
    assert [r["id"] for r in extract_json_lines(text)] == ["a", "b"]
    with pytest.raises(LabelFormatError, match="not valid JSON"):
        extract_json_lines('{"id": "a", verdict: wrong}')


def test_to_label_maps_letters_and_validates() -> None:
    label = to_label("test_pairs", TEST_ITEM, {"verdict": "Correct", "also_relevant": ["b"]})
    assert label["verdict"] == "correct" and label["also_relevant"] == ["k8s/c#000"]
    assert label["labeler"] == "claude"
    wrong = to_label("test_pairs", TEST_ITEM, {"verdict": "wrong", "also_relevant": ["A"]})
    assert wrong["also_relevant"] == []  # extras only kept for correct pairs
    so = to_label("so_questions", SO_ITEM, {"relevant": []})
    assert so["relevant"] == [] and so["dataset_row"] == 7
    for bad in (
        {"verdict": "yes", "also_relevant": []},
        {"verdict": "correct", "also_relevant": ["C"]},
        {"verdict": "correct", "also_relevant": ["AB"]},
        {"verdict": "correct"},
    ):
        with pytest.raises(LabelFormatError):
            to_label("test_pairs", TEST_ITEM, bad)


def test_export_writes_self_contained_batches(paths: Paths) -> None:
    chunks = {c: chunk(c) for c in ("k8s/a#000", "k8s/b#000", "k8s/c#000")}
    counts = export(paths, chunks, "INSTRUCTIONS")
    assert counts == {"test_pairs": 1, "so_questions": 1, "train_audit": 0, "negatives_audit": 0}
    text = (paths.data / "llm_labeling" / "batches" / "test_pairs-01.md").read_text(
        encoding="utf-8"
    )
    assert text.startswith("INSTRUCTIONS")
    assert '<item id="t1">' in text and '<candidate letter="B" id="k8s/c#000">' in text
    assert "text of k8s/a#000" in text


def test_import_saves_reports_errors_and_keeps_human_labels(paths: Paths) -> None:
    LabelStore(paths.data / "labels" / "test_pairs.jsonl").put("t2", {"verdict": "wrong"})  # human
    answer(
        paths,
        "batch1.txt",
        "```jsonl\n"
        '{"id": "t1", "verdict": "correct", "also_relevant": ["A"], "reason": "explains it"}\n'
        '{"id": "t2", "verdict": "correct", "also_relevant": [], "reason": "x"}\n'
        '{"id": "s1", "relevant": ["Z"], "reason": "bad letter"}\n'
        '{"id": "nope", "verdict": "correct"}\n'
        "```\n",
    )
    report = import_answers(paths)
    assert report["stats"] == {"saved": 1, "kept_human": 1}
    assert len(report["errors"]) == 2  # unknown id + bad letter
    assert report["missing"]["so_questions"]["batches_with_gaps"] == ["so_questions-01.md"]
    labels = LabelStore(paths.data / "labels" / "test_pairs.jsonl")
    assert labels.get("t1")["also_relevant"] == ["k8s/b#000"]  # type: ignore[index]
    assert labels.get("t2")["verdict"] == "wrong"  # type: ignore[index]
    assert import_answers(paths)["stats"] == {"unchanged": 1, "kept_human": 1}  # idempotent


def test_spot_check_agreement_and_freeze_override(paths: Paths) -> None:
    answer(
        paths,
        "a.jsonl",
        '{"id": "t1", "verdict": "correct", "also_relevant": [], "reason": "r"}\n'
        '{"id": "t2", "verdict": "correct", "also_relevant": [], "reason": "r"}\n',
    )
    import_answers(paths)
    assert make_spot_check(paths, n=5, seed=0) == 2
    spot = LabelStore(paths.data / "labels" / "spot_check.jsonl")
    spot.put("t1", {"verdict": "correct"})
    spot.put("t2", {"verdict": "wrong"})
    result = agreement(paths)
    assert result["n"] == 2 and result["agreement"] == 0.5 and result["disagreements"] == ["t2"]
    merged = with_spot_check(
        LabelStore(paths.data / "labels" / "test_pairs.jsonl").all(), spot.all()
    )
    assert merged["t2"]["verdict"] == "wrong" and merged["t2"]["labeler"] == "human"
    assert merged["t1"]["labeler"] == "human"
