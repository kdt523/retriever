"""Phase 2a: assign whole documents to train / val / test before any query exists.

Documents are split separately per source (k8s docs, runbooks) so the small runbook
stratum still lands in every split. Assignment is a seeded shuffle of sorted doc_ids,
so it is reproducible. The result is written once to ``data/splits/doc_splits.json``
and refused afterwards unless ``--force`` is given: once queries are generated
from it, changing it would leak test documents into training.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.io import sha256_file, write_text_atomic
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

Split = Literal["train", "val", "test"]
FRACTIONS: dict[Split, float] = {"train": 0.8, "val": 0.1, "test": 0.1}
MIN_HELD_OUT = 3  # per stratum, for val and test


def split_docs(doc_ids: Iterable[str], seed: int) -> dict[str, Split]:
    """Shuffle one stratum and cut it 80/10/10 (at least MIN_HELD_OUT in val and test)."""
    docs = sorted(set(doc_ids))
    random.Random(seed).shuffle(docs)
    n = len(docs)
    if n < 2 * MIN_HELD_OUT + 1:
        raise ValueError(f"stratum too small to split: {n} docs")
    n_test = max(MIN_HELD_OUT, round(n * FRACTIONS["test"]))
    n_val = max(MIN_HELD_OUT, round(n * FRACTIONS["val"]))
    out: dict[str, Split] = {}
    for i, doc in enumerate(docs):
        out[doc] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return out


def make_splits(chunks: list[Chunk], seed: int) -> dict[str, Split]:
    by_source: dict[str, set[str]] = {}
    for c in chunks:
        by_source.setdefault(c.source, set()).add(c.doc_id)
    assignment: dict[str, Split] = {}
    for source in sorted(by_source):
        assignment |= split_docs(by_source[source], seed)
    return assignment


def load_doc_splits(path: Path) -> dict[str, Split]:
    data = json.loads(path.read_text(encoding="utf-8"))
    splits: dict[str, Split] = data["docs"]
    return splits


def summarize(chunks: list[Chunk], assignment: dict[str, Split]) -> dict[str, dict[str, int]]:
    docs: Counter[tuple[str, str]] = Counter()
    chunk_counts: Counter[tuple[str, str]] = Counter()
    for doc, split in assignment.items():
        docs[(doc.split("/", 1)[0], split)] += 1
    for c in chunks:
        chunk_counts[(c.doc_id.split("/", 1)[0], assignment[c.doc_id])] += 1
    return {
        f"{src}/{split}": {"docs": docs[(src, split)], "chunks": chunk_counts[(src, split)]}
        for src, split in sorted(docs)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing split")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    out = paths.splits / "doc_splits.json"
    if out.exists() and not args.force:
        log.error("%s exists; splits are frozen once queries are generated (use --force)", out)
        return 1
    chunks = load_corpus(paths.corpus)
    assignment = make_splits(chunks, settings.seed)
    summary = summarize(chunks, assignment)
    record = {
        "seed": settings.seed,
        "fractions": FRACTIONS,
        "corpus_sha256": sha256_file(paths.corpus),
        "summary": summary,
        "docs": dict(sorted(assignment.items())),
    }
    write_text_atomic(out, json.dumps(record, indent=1) + "\n")
    for key, val in summary.items():
        log.info("%-18s %4d docs %5d chunks", key, val["docs"], val["chunks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
