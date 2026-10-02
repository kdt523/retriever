"""Phase 2d: mine one hard negative per training pair with base bge-small.

For each training query, rank the corpus with the base model and pick a negative from
ranks RANK_MIN..RANK_MAX (1-based, positive excluded), never:
- a chunk outside the train split (no test/val text may enter training),
- a neighbouring chunk of the positive (overlapping text, likely also relevant),
- a chunk scoring above MARGIN x the positive's score (probably a false negative).
If the window has no valid candidate, the next window down is tried once.
Writes ``data/splits/train.jsonl`` (anchor, positive, negative + ids) and a sample for
spot-checking to ``results/negatives_sample.md``.
"""

from __future__ import annotations

import argparse
import logging
import random
from collections import Counter
from typing import Any

import numpy as np

from runbook_retriever.config import BASE_MODEL, get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.embed import encode_corpus, encode_queries, load_model
from runbook_retriever.io import read_jsonl, write_jsonl, write_text_atomic
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.runlog import RunTracker
from runbook_retriever.splits import load_doc_splits

log = logging.getLogger(__name__)

RANK_MIN, RANK_MAX = 10, 30
FALLBACK = (31, 60)
MARGIN = 0.95
NUM_KEPT = 3  # extra negatives stored for n-tuple experiments
SAMPLE_SIZE = 50


def chunk_position(chunk_id: str) -> tuple[str, int]:
    doc, num = chunk_id.rsplit("#", 1)
    return doc, int(num)


def is_neighbour(a: str, b: str) -> bool:
    (doc_a, n_a), (doc_b, n_b) = chunk_position(a), chunk_position(b)
    return doc_a == doc_b and abs(n_a - n_b) <= 1


def pick_negatives(
    scores: np.ndarray,
    pos: int,
    pool: np.ndarray,
    ids: list[str],
    rng: random.Random,
) -> tuple[list[int], str]:
    """Valid negatives for one query (best-first window), and which window produced them."""
    order = pool[np.argsort(-scores[pool], kind="stable")]
    order = order[order != pos]
    limit = MARGIN * float(scores[pos])
    for name, (lo, hi) in (("main", (RANK_MIN, RANK_MAX)), ("fallback", FALLBACK)):
        window = [
            int(i)
            for i in order[lo - 1 : hi]
            if float(scores[i]) <= limit and not is_neighbour(ids[i], ids[pos])
        ]
        if window:
            rng.shuffle(window)
            return window[:NUM_KEPT], name
    return [], "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    corpus = load_corpus(paths.corpus)
    ids = [c.chunk_id for c in corpus]
    index = {cid: i for i, cid in enumerate(ids)}
    doc_splits = load_doc_splits(paths.splits / "doc_splits.json")
    pool = np.array([i for i, c in enumerate(corpus) if doc_splits[c.doc_id] == "train"])
    pairs = list(read_jsonl(paths.splits / "train_pairs.jsonl"))
    rng = random.Random(settings.seed)
    config = {
        "model": BASE_MODEL,
        "rank_window": [RANK_MIN, RANK_MAX],
        "fallback": FALLBACK,
        "margin": MARGIN,
        "pool": "train-split chunks only, neighbours of the positive excluded",
    }
    with RunTracker(
        phase="2", name="mine_negatives", config=config, seed=settings.seed, runs_csv=paths.runs_csv
    ) as run:
        model = load_model(BASE_MODEL)
        corpus_vecs = encode_corpus(model, BASE_MODEL, corpus, paths.cache / "emb")
        query_vecs = encode_queries(model, BASE_MODEL, [p["query"] for p in pairs])
        rows: list[dict[str, Any]] = []
        outcome: Counter[str] = Counter()
        for p, qv in zip(pairs, query_vecs, strict=True):
            pos = index[p["chunk_id"]]
            negs, window = pick_negatives(corpus_vecs @ qv, pos, pool, ids, rng)
            outcome[window] += 1
            if not negs:
                continue
            rows.append(
                {
                    "anchor": p["query"],
                    "positive": corpus[pos].passage,
                    "negative": corpus[negs[0]].passage,
                    "style": p["style"],
                    "chunk_id": p["chunk_id"],
                    "negative_ids": [ids[n] for n in negs],
                }
            )
        run.metrics = {"pairs": len(pairs), "triplets": len(rows), "windows": dict(outcome)}

    write_jsonl(paths.splits / "train.jsonl", rows)
    write_sample(rows, {c.chunk_id: c for c in corpus}, rng)
    log.info("%d triplets from %d pairs; windows %s", len(rows), len(pairs), dict(outcome))
    return 0


def write_sample(rows: list[dict[str, Any]], chunks: dict[str, Chunk], rng: random.Random) -> None:
    """Markdown sample of (query, positive, negative) for a human false-negative check."""
    sample = rng.sample(rows, min(SAMPLE_SIZE, len(rows)))
    parts = ["# Hard-negative spot check\n", "Mark any negative that actually answers the query.\n"]
    for i, r in enumerate(sample, 1):
        neg = chunks[r["negative_ids"][0]]
        parts.append(
            f"## {i}. [{r['style']}] {r['anchor']}\n\n"
            f"**Positive** `{r['chunk_id']}`\n\n> {r['positive'][:500].replace(chr(10), ' ')}\n\n"
            f"**Negative** `{neg.chunk_id}`\n\n> {neg.passage[:500].replace(chr(10), ' ')}\n\n"
            "- [ ] negative is actually relevant\n"
        )
    path = get_settings().paths.results / "negatives_sample.md"
    write_text_atomic(path, "\n".join(parts))
    log.info("wrote spot-check sample to %s", path)


if __name__ == "__main__":
    raise SystemExit(main())
