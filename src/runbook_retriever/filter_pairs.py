"""Phase 2c: filter generated (query, chunk) pairs and write the train / val / test-candidate sets.

Filters, applied in order (the first failing one is recorded as the drop reason):
1. duplicate     - same normalized query seen before for the same chunk;
   ambiguous     - same normalized query generated for different chunks (label unclear);
2. overlap       - too many query words appear in the passage (too easy, teaches nothing).
                   Error-string and kubectl-output queries quote messages on purpose, so
                   they get a higher threshold;
3. near_duplicate - cosine > NEAR_DUP_COS to an earlier query of the same chunk;
4. round_trip    - base bge-base does not rank the source chunk in its top ROUND_TRIP_K
                   (query is probably vague or mislabeled).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.embed import encode_corpus, encode_queries, load_model, rank_of
from runbook_retriever.io import read_jsonl, write_jsonl, write_text_atomic
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.runlog import RunTracker

log = logging.getLogger(__name__)

ROUND_TRIP_MODEL = "BAAI/bge-base-en-v1.5"
ROUND_TRIP_K = 50
NEAR_DUP_COS = 0.95
# Max share of query content words found in the passage. Observation styles must not read
# like the doc; how-to questions legitimately reuse its vocabulary, so only near-copies are
# dropped. error_string / kubectl_output are verbatim text by design: no cap (round trip only).
OVERLAP_MAX: dict[str, float | None] = {
    "incident_snapshot": 0.6,
    "symptom": 0.75,
    "how_to": 0.9,
    "error_string": None,
    "kubectl_output": None,
}

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from how i if in is it its my of on or
    our so that the their there this to was we what when where which why will with you your not
    no""".split()
)


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 1 and w not in _STOPWORDS}


def overlap(query: str, passage: str) -> float:
    """Fraction of the query's content words that also appear in the passage."""
    q = content_words(query)
    return len(q & content_words(passage)) / len(q) if q else 1.0


def normalize(query: str) -> str:
    return " ".join(_WORD.findall(query.lower()))


def dedupe(rows: list[dict[str, Any]]) -> None:
    """Mark exact duplicates (normalized) in place."""
    chunks_by_norm: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        chunks_by_norm[normalize(r["query"])].add(r["chunk_id"])
    seen: set[str] = set()
    for r in rows:
        norm = normalize(r["query"])
        if len(chunks_by_norm[norm]) > 1:
            r["drop"] = "ambiguous"
        elif norm in seen:
            r["drop"] = "duplicate"
        seen.add(norm)


def apply_filters(
    rows: list[dict[str, Any]],
    chunks: dict[str, Chunk],
    corpus_ids: list[str],
    query_vecs: np.ndarray,
    corpus_vecs: np.ndarray,
) -> None:
    """Fill drop / overlap / rt_rank on each row, in place. Rows and query_vecs align."""
    dedupe(rows)
    index = {cid: i for i, cid in enumerate(corpus_ids)}
    kept_by_chunk: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        r["overlap"] = round(overlap(r["query"], chunks[r["chunk_id"]].passage), 3)
        r["rt_rank"] = rank_of(query_vecs[i] @ corpus_vecs.T, index[r["chunk_id"]])
        if r.get("drop"):
            continue
        cap = OVERLAP_MAX[r["style"]]
        if cap is not None and r["overlap"] > cap:
            r["drop"] = "overlap"
            continue
        siblings = kept_by_chunk[r["chunk_id"]]
        if siblings and float((query_vecs[siblings] @ query_vecs[i]).max()) > NEAR_DUP_COS:
            r["drop"] = "near_duplicate"
            continue
        if r["rt_rank"] > ROUND_TRIP_K:
            r["drop"] = "round_trip"
            continue
        siblings.append(i)
        r["drop"] = ""


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in ("train", "val", "test"):
        sub = [r for r in rows if r["split"] == split]
        kept = [r for r in sub if not r["drop"]]
        out[split] = {
            "generated": len(sub),
            "kept": len(kept),
            "dropped": dict(Counter(r["drop"] for r in sub if r["drop"])),
            "kept_by_style": dict(Counter(r["style"] for r in kept)),
            "kept_chunks": len({r["chunk_id"] for r in kept}),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    corpus = load_corpus(paths.corpus)
    chunks = {c.chunk_id: c for c in corpus}
    rows = [dict(r) for r in read_jsonl(paths.data / "queries" / "generated.jsonl")]
    config = {
        "round_trip_model": ROUND_TRIP_MODEL,
        "round_trip_k": ROUND_TRIP_K,
        "near_dup_cos": NEAR_DUP_COS,
        "overlap_max": OVERLAP_MAX,
    }
    with RunTracker(
        phase="2", name="filter_pairs", config=config, seed=settings.seed, runs_csv=paths.runs_csv
    ) as run:
        model = load_model(ROUND_TRIP_MODEL)
        corpus_vecs = encode_corpus(model, ROUND_TRIP_MODEL, corpus, paths.cache / "emb")
        query_vecs = encode_queries(model, ROUND_TRIP_MODEL, [r["query"] for r in rows])
        apply_filters(rows, chunks, [c.chunk_id for c in corpus], query_vecs, corpus_vecs)
        summary = stats(rows)
        run.metrics = summary

    write_jsonl(paths.data / "queries" / "filtered.jsonl", rows)
    fields = ("query", "style", "chunk_id", "doc_id", "source")
    kept = [r for r in rows if not r["drop"]]
    write_jsonl(
        paths.splits / "train_pairs.jsonl",
        ({k: r[k] for k in fields} for r in kept if r["split"] == "train"),
    )
    write_jsonl(
        paths.splits / "val_pairs.jsonl",
        ({k: r[k] for k in fields} for r in kept if r["split"] == "val"),
    )
    write_jsonl(
        paths.data / "queries" / "test_candidates.jsonl",
        ({k: r[k] for k in (*fields, "rt_rank")} for r in kept if r["split"] == "test"),
    )
    write_text_atomic(paths.results / "filter_stats.json", json.dumps(summary, indent=2) + "\n")
    for split, s in summary.items():
        log.info("%-5s kept %5d / %5d  dropped %s", split, s["kept"], s["generated"], s["dropped"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
