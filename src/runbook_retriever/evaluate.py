"""Phase 3/5: score retrievers over the whole corpus on the frozen test set (or val).

Retriever specs: ``bm25``; a model alias (``minilm``, ``bge-small``, ``bge-base``) or any
sentence-transformers name / local path; ``hybrid:<model>`` = RRF of that model and BM25.

Metrics per query (binary relevance; a query may have several relevant chunks, e.g. every
chunk of the right runbook for real incidents), averaged per slice:
- ``hit@k``   at least one relevant chunk in the top k (= recall@k with one relevant chunk);
              fractional recall would punish runbook queries for not returning every chunk
- ``mrr@10``  reciprocal rank of the first relevant chunk
- ``ndcg@10`` binary-gain NDCG
Slices: each query's own ``slice``, ``all``, and ``low_overlap`` (generated queries sharing
at most half their content words with the positive passage: the hardest synthetic ones).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from runbook_retriever.bm25 import BM25Index
from runbook_retriever.build_review_sets import rrf
from runbook_retriever.config import REPO_ROOT, Paths, get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.embed import encode_corpus, encode_queries, load_model
from runbook_retriever.filter_pairs import overlap
from runbook_retriever.freeze_testset import FROZEN_FILES, build_val_set
from runbook_retriever.io import read_jsonl, sha256_file
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.runlog import RunTracker

log = logging.getLogger(__name__)

TOP_K = 100  # depth kept per retriever (RRF input); metrics use the top 10
KS = (1, 5, 10)
METRICS = (*(f"hit@{k}" for k in KS), "mrr@10", "ndcg@10")
GENERATED_SLICES = frozenset(
    {"incident_snapshot", "symptom", "error_string", "how_to", "kubectl_output"}
)
LOW_OVERLAP_MAX = 0.5
ALIASES = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "bge-small": "BAAI/bge-small-en-v1.5",
    "bge-base": "BAAI/bge-base-en-v1.5",
    "tuned": str(REPO_ROOT / "models" / "bge-small-rr"),  # `make train` output
}
DEFAULT_RETRIEVERS = ("bm25", "minilm", "bge-small", "bge-base", "hybrid:bge-small")


@dataclass(frozen=True)
class EvalSet:
    split: str
    queries: list[dict[str, Any]]
    relevant: dict[str, set[str]]  # qid -> relevant chunk ids
    positive: dict[str, str]  # qid -> first-listed relevant chunk (the generating chunk)


# --- metrics ---------------------------------------------------------------------------


def query_metrics(ranked: Sequence[str], relevant: set[str]) -> dict[str, float]:
    hits = [cid in relevant for cid in ranked[:10]]
    first = next((i for i, h in enumerate(hits) if h), None)
    dcg = sum(1.0 / math.log2(i + 2) for i, h in enumerate(hits) if h)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), 10)))
    out = {f"hit@{k}": float(any(hits[:k])) for k in KS}
    out["mrr@10"] = 0.0 if first is None else 1.0 / (first + 1)
    out["ndcg@10"] = dcg / idcg if idcg else 0.0
    return out


def query_slices(eval_set: EvalSet, chunks: Mapping[str, Chunk]) -> dict[str, list[str]]:
    """qid -> the slices it is reported in."""
    out: dict[str, list[str]] = {}
    for q in eval_set.queries:
        names = ["all", q["slice"]]
        if q["slice"] in GENERATED_SLICES:
            positive = chunks[eval_set.positive[q["qid"]]].passage
            if overlap(q["query"], positive) <= LOW_OVERLAP_MAX:
                names.append("low_overlap")
        out[q["qid"]] = names
    return out


def aggregate(
    per_query: Mapping[str, Mapping[str, float]], slices: Mapping[str, list[str]]
) -> dict[str, dict[str, float]]:
    """slice -> mean of each metric, plus ``n``."""
    groups: dict[str, list[str]] = defaultdict(list)
    for qid, names in slices.items():
        for name in names:
            groups[name].append(qid)
    table: dict[str, dict[str, float]] = {}
    for name, qids in groups.items():
        row = {m: float(np.mean([per_query[q][m] for q in qids])) for m in METRICS}
        table[name] = {"n": float(len(qids)), **row}
    return table


# --- data ------------------------------------------------------------------------------


def _from_rows(split: str, queries: list[dict[str, Any]], qrels: list[dict[str, Any]]) -> EvalSet:
    relevant: dict[str, set[str]] = defaultdict(set)
    positive: dict[str, str] = {}
    for r in qrels:
        relevant[r["qid"]].add(r["chunk_id"])
        positive.setdefault(r["qid"], r["chunk_id"])
    return EvalSet(split, queries, dict(relevant), positive)


def verify_frozen(paths: Paths) -> None:
    """Refuse to score a test set that changed after freezing (or a different corpus)."""
    manifest_path = paths.splits / "MANIFEST.json"
    if not manifest_path.exists():
        raise SystemExit("test set is not frozen yet: label the review queues, then `make freeze`")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_file(paths.corpus) != manifest["corpus_sha256"]:
        raise SystemExit("corpus changed since the test set was frozen")
    for name in FROZEN_FILES:
        if sha256_file(paths.splits / name) != manifest["files"][name]["sha256"]:
            raise SystemExit(f"{name} changed since it was frozen")


def load_eval_set(split: str, paths: Paths, corpus: list[Chunk]) -> EvalSet:
    if split == "test":
        verify_frozen(paths)
        return _from_rows(
            split,
            list(read_jsonl(paths.splits / "test_queries.jsonl")),
            list(read_jsonl(paths.splits / "test_qrels.jsonl")),
        )
    frozen = paths.splits / "val_queries.jsonl"
    if frozen.exists():
        return _from_rows(
            split, list(read_jsonl(frozen)), list(read_jsonl(paths.splits / "val_qrels.jsonl"))
        )
    return _from_rows(split, *build_val_set(paths, corpus))


# --- retrieval -------------------------------------------------------------------------

Retrieve = Callable[[list[str]], list[list[int]]]


def top_k(scores: np.ndarray, k: int) -> list[int]:
    k = min(k, scores.shape[0])
    part = np.argpartition(-scores, k - 1)[:k]
    return [int(i) for i in part[np.lexsort((part, -scores[part]))]]


def bm25_retriever(corpus: list[Chunk]) -> Retrieve:
    index = BM25Index([c.passage for c in corpus])
    return lambda queries: [top_k(index.scores(q), TOP_K) for q in queries]


def dense_retriever(model_name: str, corpus: list[Chunk], cache_dir: Path) -> Retrieve:
    model = load_model(model_name)
    corpus_vecs = encode_corpus(model, model_name, corpus, cache_dir)

    def run(queries: list[str]) -> list[list[int]]:
        scores = encode_queries(model, model_name, queries) @ corpus_vecs.T
        return [top_k(row, TOP_K) for row in scores]

    return run


def make_retriever(spec: str, corpus: list[Chunk], cache_dir: Path) -> Retrieve:
    if spec == "bm25":
        return bm25_retriever(corpus)
    if spec.startswith("hybrid:"):
        dense = make_retriever(spec.removeprefix("hybrid:"), corpus, cache_dir)
        sparse = bm25_retriever(corpus)
        return lambda qs: [rrf([d, s])[:TOP_K] for d, s in zip(dense(qs), sparse(qs), strict=True)]
    return dense_retriever(ALIASES.get(spec, spec), corpus, cache_dir)


def evaluate(
    retrieve: Retrieve, eval_set: EvalSet, corpus: list[Chunk]
) -> dict[str, dict[str, float]]:
    ids = [c.chunk_id for c in corpus]
    rankings = retrieve([q["query"] for q in eval_set.queries])
    per_query = {
        q["qid"]: query_metrics([ids[i] for i in ranked], eval_set.relevant[q["qid"]])
        for q, ranked in zip(eval_set.queries, rankings, strict=True)
    }
    return aggregate(per_query, query_slices(eval_set, {c.chunk_id: c for c in corpus}))


# --- report ----------------------------------------------------------------------------

SLICE_ORDER = (
    "all",
    "incident_snapshot",
    "error_string",
    "symptom",
    "how_to",
    "kubectl_output",
    "low_overlap",
    "real_incident_heldout",
    "real_incident_seen",
    "stackoverflow",
    "handwritten",
)


def write_table(
    path: Path, split: str, results: Mapping[str, Mapping[str, Mapping[str, float]]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    order = {s: i for i, s in enumerate(SLICE_ORDER)}
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["split", "retriever", "slice", "n", *METRICS])
        for retriever, table in results.items():
            for name in sorted(table, key=lambda s: (order.get(s, len(order)), s)):
                row = table[name]
                w.writerow(
                    [split, retriever, name, int(row["n"]), *(f"{row[m]:.4f}" for m in METRICS)]
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retrievers", nargs="*", default=list(DEFAULT_RETRIEVERS))
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--out", type=Path, help="CSV path (default results/baseline[_val].csv)")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    out = args.out or paths.root / "results" / (
        "baseline.csv" if args.split == "test" else "baseline_val.csv"
    )

    corpus = load_corpus(paths.corpus)
    eval_set = load_eval_set(args.split, paths, corpus)
    log.info("%s set: %d queries over %d chunks", args.split, len(eval_set.queries), len(corpus))
    results: dict[str, dict[str, dict[str, float]]] = {}
    for spec in args.retrievers:
        config = {"split": args.split, "retriever": spec, "queries": len(eval_set.queries)}
        with RunTracker(
            phase="3", name=f"evaluate:{spec}", config=config, seed=None, runs_csv=paths.runs_csv
        ) as run:
            results[spec] = evaluate(
                make_retriever(spec, corpus, paths.cache / "emb"), eval_set, corpus
            )
            run.metrics = {m: round(results[spec]["all"][m], 4) for m in METRICS}
        all_ = results[spec]["all"]
        log.info(
            "%-18s hit@1 %.3f  hit@10 %.3f  mrr@10 %.3f  ndcg@10 %.3f",
            spec,
            all_["hit@1"],
            all_["hit@10"],
            all_["mrr@10"],
            all_["ndcg@10"],
        )
    write_table(out, args.split, results)
    log.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
