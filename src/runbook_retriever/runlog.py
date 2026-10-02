"""Append every run's config, wall-clock time, peak RAM/VRAM and metrics to results/runs.csv."""

from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import psutil

from runbook_retriever.config import REPO_ROOT

log = logging.getLogger(__name__)

RUNS_COLUMNS = (
    "run_id",
    "started_at",
    "phase",
    "name",
    "status",
    "git_sha",
    "seed",
    "wall_seconds",
    "peak_ram_mb",
    "peak_gpu_mb",
    "config",
    "metrics",
    "notes",
)


def git_sha(cwd: Path = REPO_ROOT) -> str:
    """Short HEAD sha, suffixed ``-dirty`` when the tree has uncommitted changes."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "nogit"
    return f"{sha}-dirty" if dirty else sha


def peak_rss_mb() -> float:
    """Peak resident memory of this process so far, in MiB."""
    info = psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None)  # Windows
    if peak is not None:
        return float(peak) / 2**20
    if sys.platform != "win32":
        import resource

        ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru_maxrss / 2**20 if sys.platform == "darwin" else ru_maxrss / 1024
    return float(info.rss) / 2**20


def _torch_cuda() -> Any | None:
    torch = sys.modules.get("torch")
    if torch is None or not torch.cuda.is_available():
        return None
    return torch.cuda


def append_run(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f), [])
        if tuple(header) != RUNS_COLUMNS:
            raise ValueError(f"{path} has unexpected columns {header}; expected {RUNS_COLUMNS}")
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUNS_COLUMNS, lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in RUNS_COLUMNS})


class RunTracker:
    """Context manager that logs one row to ``runs.csv``, including failed runs.

    >>> with RunTracker(phase="4", name="train", config=cfg, seed=42, runs_csv=p) as run:
    ...     run.metrics["ndcg@10"] = 0.71
    """

    def __init__(
        self,
        *,
        phase: str,
        name: str,
        config: Mapping[str, Any],
        seed: int | None,
        runs_csv: Path,
    ) -> None:
        self.phase = phase
        self.name = name
        self.config = dict(config)
        self.seed = seed
        self.runs_csv = runs_csv
        self.run_id = uuid.uuid4().hex[:12]
        self.metrics: dict[str, Any] = {}
        self.notes = ""
        self._t0 = 0.0
        self._started_at = ""

    def __enter__(self) -> Self:
        self._started_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._t0 = time.perf_counter()
        cuda = _torch_cuda()
        if cuda is not None:
            cuda.reset_peak_memory_stats()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        cuda = _torch_cuda()
        peak_gpu = cuda.max_memory_allocated() / 2**20 if cuda is not None else None
        status = "ok" if exc_type is None else f"failed:{exc_type.__name__}"
        row = {
            "run_id": self.run_id,
            "started_at": self._started_at,
            "phase": self.phase,
            "name": self.name,
            "status": status,
            "git_sha": git_sha(),
            "seed": "" if self.seed is None else self.seed,
            "wall_seconds": f"{time.perf_counter() - self._t0:.1f}",
            "peak_ram_mb": f"{peak_rss_mb():.0f}",
            "peak_gpu_mb": "" if peak_gpu is None else f"{peak_gpu:.0f}",
            "config": json.dumps(self.config, sort_keys=True, default=str),
            "metrics": json.dumps(self.metrics, sort_keys=True, default=str),
            "notes": self.notes,
        }
        append_run(self.runs_csv, row)
        log.info("logged run %s (%s) to %s", self.run_id, status, self.runs_csv)
