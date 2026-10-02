from __future__ import annotations

import json
from typing import Any

import pytest

from runbook_retriever.config import REPO_ROOT
from runbook_retriever.freeze_testset import (
    from_incidents,
    from_stackoverflow,
    from_test_pairs,
    validate,
)
from runbook_retriever.io import sha256_file

DOC_CHUNKS = {
    "runbook/oom": ["runbook/oom#000", "runbook/oom#001"],
    "runbook/crash": ["runbook/crash#000"],
}


def test_only_correct_pairs_enter_the_test_set_with_extra_relevant() -> None:
    queue = [
        {
            "id": "a",
            "query": "q1",
            "style": "symptom",
            "source": "k8s_docs",
            "chunk_id": "k8s/x#000",
        },
        {
            "id": "b",
            "query": "q2",
            "style": "how_to",
            "source": "k8s_docs",
            "chunk_id": "k8s/y#000",
        },
        {
            "id": "c",
            "query": "q3",
            "style": "how_to",
            "source": "k8s_docs",
            "chunk_id": "k8s/z#000",
        },
    ]
    labels: dict[str, dict[str, Any]] = {
        "a": {"verdict": "correct", "also_relevant": ["k8s/x#001"]},
        "b": {"verdict": "ambiguous"},
    }
    queries, qrels, outcome = from_test_pairs(queue, labels)
    assert [q["qid"] for q in queries] == ["gen/a"]
    assert {r["chunk_id"] for r in qrels} == {"k8s/x#000", "k8s/x#001"}
    assert outcome == {"correct": 1, "ambiguous": 1, "unlabeled": 1}


def test_incidents_split_by_runbook_split() -> None:
    rows = [
        {"qid": "i1", "query": "q", "runbook_split": "test", "relevant_docs": ["runbook/oom"]},
        {
            "qid": "i2",
            "query": "q",
            "runbook_split": "train",
            "relevant_docs": ["runbook/crash", "runbook/oom"],
        },
        {"qid": "i3", "query": "q", "runbook_split": "val", "relevant_docs": ["runbook/crash"]},
    ]
    test_q, test_r = from_incidents(rows, DOC_CHUNKS, "test")
    assert [(q["qid"], q["slice"]) for q in test_q] == [
        ("i1", "real_incident_heldout"),
        ("i2", "real_incident_seen"),
    ]
    assert len([r for r in test_r if r["qid"] == "i2"]) == 3  # every chunk of both runbooks
    val_q, _ = from_incidents(rows, DOC_CHUNKS, "val")
    assert [q["qid"] for q in val_q] == ["i3"]


def test_stackoverflow_no_match_is_split_for_calibration() -> None:
    queue = [{"id": str(i), "query": f"q{i}", "dataset_row": i, "author": "u"} for i in range(5)]
    labels: dict[str, dict[str, Any]] = {
        "0": {"relevant": ["k8s/a#000"]},
        "1": {"relevant": []},
        "2": {"relevant": []},
        "3": {"relevant": []},
        "4": {"relevant": []},
    }
    q, r, ood_val, ood_test = from_stackoverflow(queue, labels, seed=1)
    assert [x["qid"] for x in q] == ["so/0"] and r[0]["chunk_id"] == "k8s/a#000"
    assert len(ood_val) == 2 and len(ood_test) == 2
    assert not {x["qid"] for x in ood_val} & {x["qid"] for x in ood_test}


def test_validate_catches_broken_sets() -> None:
    with pytest.raises(ValueError, match="without relevant"):
        validate([{"qid": "a"}], [], {"k8s/x#000"})
    with pytest.raises(ValueError, match="unknown chunks"):
        validate([{"qid": "a"}], [{"qid": "a", "chunk_id": "nope"}], {"k8s/x#000"})


def test_frozen_files_match_manifest() -> None:
    """Once frozen, the evaluation files may never change (leakage / moving-goalpost guard)."""
    manifest = REPO_ROOT / "data" / "splits" / "MANIFEST.json"
    if not manifest.exists():
        pytest.skip("test set not frozen yet")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for name, meta in data["files"].items():
        assert sha256_file(REPO_ROOT / "data" / "splits" / name) == meta["sha256"], (
            f"{name} was edited"
        )
