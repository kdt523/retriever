"""Phase 2e: prepare the four human-review queues used by ``review/streamlit_app.py``.

Writes to ``data/review/``:
- ``test_pairs.jsonl``     ~TEST_SAMPLE generated test queries (balanced over styles, at most
                           one per chunk, all runbook queries first) + 5 other candidate chunks
                           so the reviewer can mark extra relevant chunks;
- ``so_questions.jsonl``   SO_SAMPLE real Stack Overflow questions with up to 10 candidate
                           chunks (bge-base and BM25 merged by reciprocal rank fusion);
- ``train_audit.jsonl``    TRAIN_AUDIT random training pairs (label error rate);
- ``negatives_audit.jsonl`` NEG_AUDIT mined negatives (false-negative rate).
Queues are regenerated deterministically from the seed; labels live separately in
``data/labels/`` and are matched by item id, so regenerating never loses work.
"""

from __future__ import annotations

import argparse
import html
import logging
import random
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np

from runbook_retriever.bm25 import BM25Index
from runbook_retriever.config import get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.embed import encode_corpus, encode_queries, load_model
from runbook_retriever.io import read_jsonl, stable_hash, write_jsonl
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

TEST_SAMPLE = 220
SO_SAMPLE = 150
TRAIN_AUDIT = 100
NEG_AUDIT = 50
EXTRA_CANDIDATES = 5
SO_CANDIDATES = 10
RRF_K = 60
CANDIDATE_MODEL = "BAAI/bge-base-en-v1.5"
SO_DATASET = "mcipriano/stackoverflow-kubernetes-questions"

_TROUBLESHOOTING = re.compile(
    r"error|fail|crash|pending|not work|doesn'?t work|can'?t|cannot|unable|timeout|timed out|"
    r"refused|backoff|oom|evict|forbidden|denied|stuck|restart|not found|unhealthy|probe",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    text = re.sub(r"</(p|pre|li|h\d)>|<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = html.unescape(_TAG.sub("", text))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ln.rstrip() for ln in text.splitlines())).strip()


def item_id(*parts: str) -> str:
    return stable_hash(list(parts))[:16]


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion of several ranked id lists (best first)."""
    score: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            score[idx] += 1.0 / (k + rank)
    return sorted(score, key=lambda i: (-score[i], i))


def sample_test_pairs(
    candidates: list[dict[str, Any]], n: int, rng: random.Random
) -> list[dict[str, Any]]:
    """All runbook queries first (one per chunk), then k8s-doc queries round-robin over styles."""
    by_chunk: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        by_chunk[c["chunk_id"]].append(c)
    one_per_chunk = [
        rng.choice(sorted(v, key=lambda r: r["query"])) for _, v in sorted(by_chunk.items())
    ]
    rng.shuffle(one_per_chunk)
    picked = [r for r in one_per_chunk if r["source"] == "runbook"]
    by_style: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in one_per_chunk:
        if r["source"] != "runbook":
            by_style[r["style"]].append(r)
    styles = sorted(by_style)
    while len(picked) < n and any(by_style.values()):
        for style in styles:
            if by_style[style] and len(picked) < n:
                picked.append(by_style[style].pop())
    return picked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    out = paths.data / "review"
    rng = random.Random(settings.seed)
    corpus = load_corpus(paths.corpus)
    ids = [c.chunk_id for c in corpus]
    index = {cid: i for i, cid in enumerate(ids)}
    model = load_model(CANDIDATE_MODEL)
    corpus_vecs = encode_corpus(model, CANDIDATE_MODEL, corpus, paths.cache / "emb")

    def dense_top(queries: list[str], k: int) -> list[list[int]]:
        scores = encode_queries(model, CANDIDATE_MODEL, queries) @ corpus_vecs.T
        return [list(map(int, np.argsort(-row, kind="stable")[:k])) for row in scores]

    # 1. Test pairs
    test_candidates = list(read_jsonl(paths.data / "queries" / "test_candidates.jsonl"))
    test_items = sample_test_pairs(test_candidates, TEST_SAMPLE, rng)
    tops = dense_top([t["query"] for t in test_items], EXTRA_CANDIDATES + 1)
    rows = []
    for t, top in zip(test_items, tops, strict=True):
        extra = [ids[i] for i in top if ids[i] != t["chunk_id"]][:EXTRA_CANDIDATES]
        rows.append({"id": item_id("test", t["query"], t["chunk_id"]), **t, "candidates": extra})
    write_jsonl(out / "test_pairs.jsonl", rows)
    log.info("test_pairs: %d items", len(rows))

    # 2. Stack Overflow questions
    so_rows = build_so_queue(corpus, ids, dense_top, rng)
    write_jsonl(out / "so_questions.jsonl", so_rows)
    log.info("so_questions: %d items", len(so_rows))

    # 3. Train audit and 4. negatives audit
    train = list(read_jsonl(paths.splits / "train.jsonl"))
    audit = rng.sample(train, min(TRAIN_AUDIT, len(train)))
    write_jsonl(
        out / "train_audit.jsonl",
        (
            {
                "id": item_id("train", a["anchor"], a["chunk_id"]),
                "query": a["anchor"],
                "style": a["style"],
                "chunk_id": a["chunk_id"],
            }
            for a in audit
        ),
    )
    negs = rng.sample(train, min(NEG_AUDIT, len(train)))
    write_jsonl(
        out / "negatives_audit.jsonl",
        (
            {
                "id": item_id("neg", n["anchor"], n["negative_ids"][0]),
                "query": n["anchor"],
                "chunk_id": n["chunk_id"],
                "negative_id": n["negative_ids"][0],
            }
            for n in negs
        ),
    )
    log.info("train_audit: %d, negatives_audit: %d", len(audit), len(negs))
    assert all(r["chunk_id"] in index for r in rows)
    return 0


def build_so_queue(
    corpus: list[Chunk], ids: list[str], dense_top: Any, rng: random.Random
) -> list[dict[str, Any]]:
    from datasets import load_dataset

    paths = get_settings().paths
    ds = load_dataset(SO_DATASET, split="train", cache_dir=str(paths.raw / "hf"))
    pool = []
    for i, row in enumerate(ds):
        text = html_to_text(row["Question"])
        if 80 <= len(text) <= 2500 and _TROUBLESHOOTING.search(text):
            pool.append((i, text, row["QuestionAuthor"]))
    picked = rng.sample(pool, min(SO_SAMPLE, len(pool)))
    queries = [" ".join(text.split()[:200]) for _, text, _ in picked]
    bm25 = BM25Index([c.passage for c in corpus])
    dense = dense_top(queries, SO_CANDIDATES)
    rows = []
    for (row_idx, text, author), query, d in zip(picked, queries, dense, strict=True):
        fused = rrf([d, bm25.top_k(query, SO_CANDIDATES)])[:SO_CANDIDATES]
        rows.append(
            {
                "id": item_id("so", str(row_idx)),
                "dataset_row": row_idx,
                "author": author,
                "question": text,
                "query": query,
                "candidates": [ids[i] for i in fused],
            }
        )
    log.info(
        "stack overflow: %d troubleshooting questions in pool, sampled %d", len(pool), len(rows)
    )
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
