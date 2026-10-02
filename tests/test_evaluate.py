from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from runbook_retriever.config import Paths
from runbook_retriever.corpus import Chunk
from runbook_retriever.evaluate import (
    EvalSet,
    evaluate,
    query_metrics,
    top_k,
    verify_frozen,
    write_table,
)
from runbook_retriever.freeze_testset import FROZEN_FILES
from runbook_retriever.io import sha256_file


def chunk(cid: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        doc_id=cid.split("#")[0],
        source="k8s_docs",
        source_path="x",
        url=None,
        title="T",
        section="S",
        text=text,
        n_tokens=10,
    )


def test_query_metrics_single_relevant() -> None:
    m = query_metrics(["a", "b", "c"], {"c"})
    assert (m["hit@1"], m["hit@5"], m["hit@10"]) == (0.0, 1.0, 1.0)
    assert m["mrr@10"] == pytest.approx(1 / 3)
    assert m["ndcg@10"] == pytest.approx(1 / math.log2(4))


def test_query_metrics_several_relevant_and_miss() -> None:
    m = query_metrics(["x", "a", "b"], {"a", "b"})
    assert m["hit@1"] == 0.0 and m["mrr@10"] == 0.5
    ideal = 1 + 1 / math.log2(3)
    assert m["ndcg@10"] == pytest.approx((1 / math.log2(3) + 1 / math.log2(4)) / ideal)
    miss = query_metrics([str(i) for i in range(20)], {"19"})  # relevant only at rank 20
    assert all(v == 0.0 for v in miss.values())


def test_top_k_orders_by_score_then_index() -> None:
    scores = np.array([0.1, 0.9, 0.5, 0.9, 0.2], dtype=np.float32)
    assert top_k(scores, 3) == [1, 3, 2]
    assert top_k(scores, 10) == [1, 3, 2, 4, 0]


def test_evaluate_slices_and_low_overlap() -> None:
    corpus = [
        chunk("d#000", "liveness probe failures restart the container"),
        chunk("e#000", "image pull back off from a private registry"),
    ]
    queries = [
        # shares no words with its passage -> low_overlap
        {"qid": "q1", "query": "app killed every few seconds", "slice": "symptom"},
        # copies its passage -> not low_overlap
        {"qid": "q2", "query": "image pull back off private registry", "slice": "error_string"},
        {"qid": "q3", "query": "pods restarting", "slice": "real_incident_heldout"},
    ]
    eval_set = EvalSet(
        "val",
        queries,
        relevant={"q1": {"d#000"}, "q2": {"e#000"}, "q3": {"d#000", "e#000"}},
        positive={"q1": "d#000", "q2": "e#000", "q3": "d#000"},
    )
    rankings = {"app killed every few seconds": [1, 0]}  # q1 misses rank 1, others are perfect
    table = evaluate(
        lambda qs: [rankings.get(q, [0, 1] if "pods" in q else [1, 0]) for q in qs],
        eval_set,
        corpus,
    )
    assert table["all"]["n"] == 3 and table["all"]["hit@1"] == pytest.approx(2 / 3)
    assert table["symptom"]["mrr@10"] == 0.5
    assert table["low_overlap"]["n"] == 1  # only q1; real incidents are never in it
    assert table["real_incident_heldout"]["ndcg@10"] == 1.0


def test_write_table_orders_slices(tmp_path: Path) -> None:
    row = {"n": 2.0, "hit@1": 0.5, "hit@5": 1.0, "hit@10": 1.0, "mrr@10": 0.75, "ndcg@10": 0.8}
    out = tmp_path / "t.csv"
    write_table(out, "val", {"bm25": {"how_to": row, "all": row, "stackoverflow": row}})
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "split,retriever,slice,n,hit@1,hit@5,hit@10,mrr@10,ndcg@10"
    assert [line.split(",")[2] for line in lines[1:]] == ["all", "how_to", "stackoverflow"]


def test_verify_frozen_detects_edits(tmp_path: Path) -> None:
    paths = Paths(tmp_path)
    with pytest.raises(SystemExit, match="not frozen"):
        verify_frozen(paths)
    paths.splits.mkdir(parents=True)
    paths.corpus.write_text("corpus\n", encoding="utf-8")
    for name in FROZEN_FILES:
        (paths.splits / name).write_text(f"{name}\n", encoding="utf-8")
    manifest = {
        "corpus_sha256": sha256_file(paths.corpus),
        "files": {n: {"sha256": sha256_file(paths.splits / n)} for n in FROZEN_FILES},
    }
    (paths.splits / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    verify_frozen(paths)  # untouched -> fine
    (paths.splits / "test_qrels.jsonl").write_text("edited\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"test_qrels.jsonl changed"):
        verify_frozen(paths)
