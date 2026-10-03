"""Phase 5: turn results/ablations_{val,test}.csv into results/ablations.md (tables only).

Seeds 42/43/44 are the main configuration trained with different seeds (``tuned`` is seed 42);
the table shows their mean and sample standard deviation. Every other row is a single run.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

from runbook_retriever.config import get_settings

COLS = ("hit@1", "hit@5", "hit@10", "mrr@10", "ndcg@10")
LABELS = {
    "bge-small": "bge-small, no training",
    "tuned": "tuned (seed 42)",
    "seed43": "tuned (seed 43)",
    "seed44": "tuned (seed 44)",
    "no-hard-negatives": "no hard negatives",
    "data-25pct": "25% of training pairs",
    "data-50pct": "50% of training pairs",
    "epochs-1": "1 epoch (instead of 3)",
}
SEEDS = ("tuned", "seed43", "seed44")


def load_all_rows(path: Path, slice_name: str = "all") -> dict[str, dict[str, float]]:
    """retriever key (last path component) -> metrics for ``slice_name``."""
    out: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["slice"] == slice_name:
                key = row["retriever"].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                out[key] = {c: float(row[c]) for c in COLS}
    return out


def render(rows: dict[str, dict[str, float]], title: str) -> list[str]:
    lines = [f"### {title}", "", "| Variant | " + " | ".join(COLS) + " |"]
    lines.append("| --- |" + " --- |" * len(COLS))
    for key, label in LABELS.items():
        if key in rows:
            lines.append(f"| {label} | " + " | ".join(f"{rows[key][c]:.3f}" for c in COLS) + " |")
    seeds = [rows[s] for s in SEEDS if s in rows]
    if len(seeds) > 1:
        cells = []
        for c in COLS:
            values = [s[c] for s in seeds]
            cells.append(f"{statistics.mean(values):.3f} ± {statistics.stdev(values):.3f}")
        lines.append(f"| **mean ± sd over {len(seeds)} seeds** | " + " | ".join(cells) + " |")
    return [*lines, ""]


def main() -> int:
    results = get_settings().paths.results
    lines = ["# Phase 5 ablations and seed spread", ""]
    for split, title in (("test", "Frozen test set (269 queries)"), ("val", "Val set (715)")):
        path = results / f"ablations_{split}.csv"
        lines += render(load_all_rows(path), title)
    (results / "ablations.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print((results / "ablations.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
