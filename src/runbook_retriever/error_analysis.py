"""Phase 5: the worst test queries for a retriever, with what it returned instead.

``python -m runbook_retriever.error_analysis`` writes ``results/worst_queries.json`` (the 30
test queries whose first relevant chunk is ranked lowest, with the top-3 retrieved chunks).
Hand-written tags live in ``docs/error_tags.json`` (qid -> {tag, note}); with tags present the
script also writes ``results/error_analysis.md`` and prints the tag counts.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import load_corpus
from runbook_retriever.evaluate import TOP_K, load_eval_set, make_retriever
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

TAGS = ("wrong_label", "ambiguous_query", "missing_doc", "chunk_too_long", "model_miss")
NOT_FOUND = TOP_K + 1


def worst_queries(spec: str, n: int) -> list[dict[str, Any]]:
    settings = get_settings()
    paths = settings.paths
    corpus = load_corpus(paths.corpus)
    eval_set = load_eval_set("test", paths, corpus)
    ids = [c.chunk_id for c in corpus]
    by_id = {c.chunk_id: c for c in corpus}
    rankings = make_retriever(spec, corpus, paths.cache / "emb")(
        [q["query"] for q in eval_set.queries]
    )
    rows: list[dict[str, Any]] = []
    for q, ranked in zip(eval_set.queries, rankings, strict=True):
        relevant = eval_set.relevant[q["qid"]]
        ranked_ids = [ids[i] for i in ranked]
        rank = next((r for r, cid in enumerate(ranked_ids, 1) if cid in relevant), NOT_FOUND)
        rows.append(
            {
                "qid": q["qid"],
                "slice": q.get("slice", ""),
                "query": q["query"],
                "rank": rank,
                "relevant": sorted(relevant)[:3],
                "relevant_count": len(relevant),
                "relevant_tokens": by_id[eval_set.positive[q["qid"]]].n_tokens,
                "top3": [
                    {"chunk_id": cid, "heading": by_id[cid].passage.split("\n", 1)[0]}
                    for cid in ranked_ids[:3]
                ],
            }
        )
    rows.sort(key=lambda r: (-r["rank"], r["qid"]))
    return rows[:n]


def write_report(rows: list[dict[str, Any]], tags: dict[str, dict[str, str]], out: Path) -> None:
    lines = ["# Error analysis: 30 worst test queries (tuned model)", ""]
    counts = Counter(tags[r["qid"]]["tag"] for r in rows if r["qid"] in tags)
    lines += ["| tag | count |", "| --- | --- |"]
    lines += [f"| {t} | {counts.get(t, 0)} |" for t in TAGS]
    lines.append("")
    for r in rows:
        tag = tags.get(r["qid"], {"tag": "untagged", "note": ""})
        rank = "not in top 100" if r["rank"] == NOT_FOUND else f"rank {r['rank']}"
        lines += [
            f"## {r['qid']} ({r['slice']}): {tag['tag']}, {rank}",
            "",
            f"Query: `{' '.join(r['query'].split())[:300]}`",
            "",
            f"Relevant: {', '.join(r['relevant'])}",
            "",
            "Top 3 returned: " + "; ".join(t["heading"] for t in r["top3"]),
            "",
            tag["note"],
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retriever", default="tuned")
    parser.add_argument("-n", type=int, default=30)
    args = parser.parse_args(argv)
    setup_logging()
    paths = get_settings().paths
    rows = worst_queries(args.retriever, args.n)
    out = paths.results / "worst_queries.json"
    out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n")
    log.info("wrote %s (worst rank %s)", out, rows[0]["rank"] if rows else "-")
    tags_path = paths.root / "docs" / "error_tags.json"
    if tags_path.exists():
        tags = json.loads(tags_path.read_text(encoding="utf-8"))
        missing = [r["qid"] for r in rows if r["qid"] not in tags]
        if missing:
            log.warning("%d worst queries have no tag yet", len(missing))
        write_report(rows, tags, paths.results / "error_analysis.md")
        log.info("tags: %s", dict(Counter(t["tag"] for t in tags.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
