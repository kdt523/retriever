from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from runbook_retriever.runlog import RUNS_COLUMNS, RunTracker, append_run, peak_rss_mb


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_tracker_logs_successful_run(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "runs.csv"
    with RunTracker(phase="4", name="train", config={"lr": 2e-5}, seed=7, runs_csv=runs) as run:
        run.metrics["recall@5"] = 0.8
    (row,) = read_rows(runs)
    assert row["status"] == "ok"
    assert row["seed"] == "7"
    assert json.loads(row["config"]) == {"lr": 2e-5}
    assert json.loads(row["metrics"]) == {"recall@5": 0.8}
    assert float(row["wall_seconds"]) >= 0
    assert float(row["peak_ram_mb"]) > 0


def test_tracker_logs_failed_run_and_reraises(tmp_path: Path) -> None:
    runs = tmp_path / "runs.csv"
    with (
        pytest.raises(KeyError),
        RunTracker(phase="3", name="eval", config={}, seed=None, runs_csv=runs),
    ):
        raise KeyError("boom")
    with RunTracker(phase="3", name="eval", config={}, seed=None, runs_csv=runs):
        pass
    rows = read_rows(runs)
    assert [r["status"] for r in rows] == ["failed:KeyError", "ok"]


def test_append_run_rejects_foreign_header(tmp_path: Path) -> None:
    runs = tmp_path / "runs.csv"
    runs.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected columns"):
        append_run(runs, {c: "" for c in RUNS_COLUMNS})


def test_peak_rss_positive() -> None:
    assert peak_rss_mb() > 1
