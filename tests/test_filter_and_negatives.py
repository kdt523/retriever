from __future__ import annotations

import random
from typing import Any

import numpy as np

from runbook_retriever.corpus import Chunk
from runbook_retriever.filter_pairs import apply_filters, dedupe, overlap
from runbook_retriever.mine_negatives import is_neighbour, pick_negatives


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
        n_tokens=50,
    )


# --- filters -------------------------------------------------------------------------


def test_overlap_ignores_stopwords_and_case() -> None:
    passage = "Pods restart when the liveness probe times out"
    assert overlap("The pods RESTART on probe timeout", passage) == 3 / 4  # pods restart probe
    assert overlap("ImagePullBackOff from private registry", passage) == 0.0


def test_dedupe_marks_duplicates_and_ambiguous() -> None:
    rows: list[dict[str, Any]] = [
        {"query": "Pods keep restarting!", "chunk_id": "a#000"},
        {"query": "pods keep restarting", "chunk_id": "a#000"},  # same chunk -> duplicate
        {"query": "where is my image", "chunk_id": "a#000"},
        {"query": "Where is my image?", "chunk_id": "b#000"},  # other chunk -> ambiguous
    ]
    dedupe(rows)
    assert [r.get("drop", "") for r in rows] == ["", "duplicate", "ambiguous", "ambiguous"]


def test_apply_filters_reasons_in_order() -> None:
    chunks = {
        "a#000": chunk("a#000", "liveness probe timeout restarts the container"),
        "b#000": chunk("b#000", "image pull back off private registry credentials"),
    }
    ids = ["a#000", "b#000"]
    corpus_vecs = np.eye(2, dtype=np.float32)
    rows: list[dict[str, Any]] = [
        {
            "query": "app killed every few seconds under load",
            "style": "symptom",
            "chunk_id": "a#000",
        },
        {
            "query": "liveness probe timeout restarts container",
            "style": "symptom",
            "chunk_id": "a#000",
        },
        {
            "query": "app killed repeatedly when traffic spikes",
            "style": "symptom",
            "chunk_id": "a#000",
        },
        {
            "query": "deploy stuck pulling from our registry",
            "style": "symptom",
            "chunk_id": "b#000",
        },
    ]
    q = np.array(
        [[1.0, 0.0], [1.0, 0.0], [0.999, 0.04], [1.0, 0.0]],  # last one points at the wrong chunk
        dtype=np.float32,
    )
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    apply_filters(rows, chunks, ids, q, corpus_vecs)
    assert [r["drop"] for r in rows] == ["", "overlap", "near_duplicate", ""]
    assert rows[3]["rt_rank"] == 2  # rank 2 of 2 still passes the top-50 round trip


def test_verbatim_styles_have_no_overlap_cap() -> None:
    chunks = {"a#000": chunk("a#000", "Back-off restarting failed container app in pod web")}
    rows: list[dict[str, Any]] = [
        {
            "query": "Back-off restarting failed container",
            "style": "error_string",
            "chunk_id": "a#000",
        },
        {
            "query": "restarting failed container app back-off",
            "style": "how_to",
            "chunk_id": "a#000",
        },
    ]
    q = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)  # not near-duplicates
    apply_filters(rows, chunks, ["a#000"], q, np.ones((1, 2), dtype=np.float32))
    assert rows[0]["overlap"] == rows[1]["overlap"] == 1.0
    assert [r["drop"] for r in rows] == ["", "overlap"]


# --- negatives -----------------------------------------------------------------------


def test_is_neighbour() -> None:
    assert is_neighbour("k8s/a#004", "k8s/a#005")
    assert not is_neighbour("k8s/a#004", "k8s/a#006")
    assert not is_neighbour("k8s/a#004", "k8s/b#005")


def test_pick_negatives_respects_window_margin_neighbours_and_pool() -> None:
    n = 40
    ids = [f"k8s/d{i // 10}#{i % 10:03d}" for i in range(n)]
    scores = np.linspace(1.0, 0.1, n).astype(np.float32)  # index 0 best ... 39 worst
    pos = 0
    pool = np.array([i for i in range(n) if i != 25])  # 25 is not in the train split
    negs, window = pick_negatives(scores, pos, pool, ids, random.Random(0))
    assert window == "main" and 1 <= len(negs) <= 3
    order = [i for i in np.argsort(-scores) if i in set(pool.tolist()) and i != pos]
    allowed = set(order[9:30])  # ranks 10..30, 1-based, positive excluded
    for i in negs:
        assert i in allowed and i != 25
        assert scores[i] <= 0.95 * scores[pos]
        assert not is_neighbour(ids[i], ids[pos])


def test_pick_negatives_margin_can_empty_the_window() -> None:
    ids = [f"k8s/d{i}#000" for i in range(70)]
    scores = np.full(70, 0.99, dtype=np.float32)
    scores[0] = 1.0  # everything scores above 95% of the positive -> likely false negatives
    negs, window = pick_negatives(scores, 0, np.arange(70), ids, random.Random(0))
    assert (negs, window) == ([], "none")
