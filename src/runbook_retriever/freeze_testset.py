"""Phase 2e: assemble and freeze the evaluation sets from reviewed labels.

Outputs in ``data/splits/`` (committed; never edited after freezing):
- ``test_queries.jsonl`` / ``test_qrels.jsonl``  hand-verified test set, one ``slice`` per query:
    generated styles (incident_snapshot, symptom, error_string, how_to, kubectl_output) that the
    reviewer marked correct; ``real_incident_heldout`` / ``real_incident_seen`` from real cluster
    captures (held-out vs training runbooks); ``stackoverflow`` real questions mapped by hand;
    ``handwritten`` optional queries from ``data/labels/handwritten.jsonl``.
- ``val_queries.jsonl`` / ``val_qrels.jsonl``    model-selection set: filtered val pairs plus
    val-runbook incident captures (not hand-checked).
- ``ood_val.jsonl`` / ``ood_test.jsonl``          out-of-scope questions (SO "no match"), split
    50/50: calibrate the no-match threshold on val, report it on test.
- ``MANIFEST.json``                               sha256 + counts of every file above.
Refuses to overwrite an existing manifest unless ``--force``.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from runbook_retriever.config import Paths, get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.io import read_jsonl, sha256_file, write_jsonl, write_text_atomic
from runbook_retriever.labeling import LabelStore, load_queue
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

FROZEN_FILES = (
    "test_queries.jsonl",
    "test_qrels.jsonl",
    "val_queries.jsonl",
    "val_qrels.jsonl",
    "ood_val.jsonl",
    "ood_test.jsonl",
)

Query = dict[str, Any]
Qrel = dict[str, Any]


def qrels_for(qid: str, chunk_ids: list[str]) -> list[Qrel]:
    return [{"qid": qid, "chunk_id": c, "relevance": 1} for c in dict.fromkeys(chunk_ids)]


def from_test_pairs(
    queue: list[dict[str, Any]], labels: dict[str, dict[str, Any]]
) -> tuple[list[Query], list[Qrel], Counter[str]]:
    queries: list[Query] = []
    qrels: list[Qrel] = []
    outcome: Counter[str] = Counter()
    for item in queue:
        label = labels.get(item["id"])
        verdict = label["verdict"] if label else "unlabeled"
        outcome[verdict] += 1
        if verdict != "correct":
            continue
        qid = f"gen/{item['id']}"
        queries.append(
            {"qid": qid, "query": item["query"], "slice": item["style"], "source": item["source"]}
        )
        qrels += qrels_for(qid, [item["chunk_id"], *label.get("also_relevant", [])])  # type: ignore[union-attr]
    return queries, qrels, outcome


def with_spot_check(
    labels: dict[str, dict[str, Any]], spot: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Blind human re-checks override the earlier (Claude) verdict on the same test pair."""
    out = dict(labels)
    for item_id, human in spot.items():
        if item_id in out:
            out[item_id] = out[item_id] | {"verdict": human["verdict"], "labeler": "human"}
    return out


def labelers(labels: dict[str, dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(lab.get("labeler", "human") for lab in labels.values()))


def from_incidents(
    rows: list[dict[str, Any]], doc_chunks: dict[str, list[str]], split: str
) -> tuple[list[Query], list[Qrel]]:
    queries: list[Query] = []
    qrels: list[Qrel] = []
    for r in rows:
        if split == "val" and r["runbook_split"] != "val":
            continue
        if split == "test" and r["runbook_split"] == "val":
            continue
        slice_ = (
            "real_incident_heldout"
            if r["runbook_split"] in ("test", "val")
            else "real_incident_seen"
        )
        queries.append({"qid": r["qid"], "query": r["query"], "slice": slice_, "source": "runbook"})
        qrels += qrels_for(r["qid"], [c for d in r["relevant_docs"] for c in doc_chunks[d]])
    return queries, qrels


def from_stackoverflow(
    queue: list[dict[str, Any]], labels: dict[str, dict[str, Any]], seed: int
) -> tuple[list[Query], list[Qrel], list[Query], list[Query]]:
    queries: list[Query] = []
    qrels: list[Qrel] = []
    no_match: list[Query] = []
    for item in queue:
        label = labels.get(item["id"])
        if label is None:
            continue
        qid = f"so/{item['dataset_row']}"
        q = {
            "qid": qid,
            "query": item["query"],
            "slice": "stackoverflow",
            "source": "stackoverflow",
            "author": item["author"],
        }
        if label["relevant"]:
            queries.append(q)
            qrels += qrels_for(qid, label["relevant"])
        else:
            no_match.append(q | {"slice": "out_of_scope"})
    random.Random(seed).shuffle(no_match)
    half = len(no_match) // 2
    return queries, qrels, no_match[:half], no_match[half:]


def from_val_pairs(pairs: list[dict[str, Any]]) -> tuple[list[Query], list[Qrel]]:
    queries: list[Query] = []
    qrels: list[Qrel] = []
    for i, p in enumerate(pairs):
        qid = f"val/{i:05d}"
        queries.append(
            {"qid": qid, "query": p["query"], "slice": p["style"], "source": p["source"]}
        )
        qrels += qrels_for(qid, [p["chunk_id"]])
    return queries, qrels


def from_handwritten(path: Path) -> tuple[list[Query], list[Qrel]]:
    if not path.exists():
        return [], []
    queries: list[Query] = []
    qrels: list[Qrel] = []
    for i, row in enumerate(read_jsonl(path)):
        qid = f"hand/{i:03d}"
        queries.append(
            {"qid": qid, "query": row["query"], "slice": "handwritten", "source": "human"}
        )
        qrels += qrels_for(qid, row["relevant"])
    return queries, qrels


def doc_chunk_ids(corpus: list[Chunk]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for c in corpus:
        out[c.doc_id].append(c.chunk_id)
    return out


def build_val_set(paths: Paths, corpus: list[Chunk]) -> tuple[list[Query], list[Qrel]]:
    """Model-selection set; needs no human labels, so it can be built before freezing."""
    incidents = list(read_jsonl(paths.data / "queries" / "incident_queries.jsonl"))
    val_q, val_r = from_val_pairs(list(read_jsonl(paths.splits / "val_pairs.jsonl")))
    inc_q, inc_r = from_incidents(incidents, doc_chunk_ids(corpus), "val")
    return val_q + inc_q, val_r + inc_r


def validate(queries: list[Query], qrels: list[Qrel], known_chunks: set[str]) -> None:
    qids = [q["qid"] for q in queries]
    if len(qids) != len(set(qids)):
        raise ValueError("duplicate qids")
    with_qrels = {r["qid"] for r in qrels}
    missing = set(qids) - with_qrels
    if missing:
        raise ValueError(f"queries without relevant chunks: {sorted(missing)[:5]}")
    unknown = {r["chunk_id"] for r in qrels} - known_chunks
    if unknown:
        raise ValueError(f"qrels reference unknown chunks: {sorted(unknown)[:5]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing frozen set")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    manifest_path = paths.splits / "MANIFEST.json"
    if manifest_path.exists() and not args.force:
        log.error(
            "test set already frozen (%s); never edit it after baselines exist", manifest_path
        )
        return 1

    corpus = load_corpus(paths.corpus)
    doc_chunks = doc_chunk_ids(corpus)
    labels_dir = paths.data / "labels"
    review_dir = paths.data / "review"
    incidents = list(read_jsonl(paths.data / "queries" / "incident_queries.jsonl"))

    test_labels = with_spot_check(
        LabelStore(labels_dir / "test_pairs.jsonl").all(),
        LabelStore(labels_dir / "spot_check.jsonl").all(),
    )
    so_labels = LabelStore(labels_dir / "so_questions.jsonl").all()
    gen_q, gen_r, outcome = from_test_pairs(
        load_queue(review_dir / "test_pairs.jsonl"), test_labels
    )
    inc_q, inc_r = from_incidents(incidents, doc_chunks, "test")
    so_q, so_r, ood_val, ood_test = from_stackoverflow(
        load_queue(review_dir / "so_questions.jsonl"),
        so_labels,
        settings.seed,
    )
    hand_q, hand_r = from_handwritten(labels_dir / "handwritten.jsonl")
    test_q = gen_q + inc_q + so_q + hand_q
    test_r = gen_r + inc_r + so_r + hand_r
    val_q, val_r = build_val_set(paths, corpus)

    known = {c.chunk_id for c in corpus}
    validate(test_q, test_r, known)
    validate(val_q, val_r, known)
    if outcome["unlabeled"]:
        log.warning("%d test pairs are still unlabeled and are excluded", outcome["unlabeled"])

    outputs = {
        "test_queries.jsonl": test_q,
        "test_qrels.jsonl": test_r,
        "val_queries.jsonl": val_q,
        "val_qrels.jsonl": val_r,
        "ood_val.jsonl": ood_val,
        "ood_test.jsonl": ood_test,
    }
    for name, rows in outputs.items():
        write_jsonl(paths.splits / name, rows)
    manifest = {
        "corpus_sha256": sha256_file(paths.corpus),
        "test_pair_review": dict(outcome),
        "labelers": {"test_pairs": labelers(test_labels), "so_questions": labelers(so_labels)},
        "test_slices": dict(Counter(q["slice"] for q in test_q)),
        "val_slices": dict(Counter(q["slice"] for q in val_q)),
        "files": {
            name: {"sha256": sha256_file(paths.splits / name), "rows": len(rows)}
            for name, rows in outputs.items()
        },
    }
    write_text_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")
    log.info("frozen test set: %s", manifest["test_slices"])
    log.info("val set: %d queries; ood val/test: %d/%d", len(val_q), len(ood_val), len(ood_test))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
