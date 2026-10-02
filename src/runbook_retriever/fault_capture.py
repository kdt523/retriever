"""Inject real failures into a throwaway k3d cluster and record what Kubernetes prints.

Each scenario in ``faults/*.yaml`` creates objects in its own namespace, optionally runs
steps that break something, then polls a standard capture (pods, describe, events,
container logs) plus scenario extras until every ``expect`` regex matches. The capture
is saved to ``data/incidents/<id>.json`` (+ ``.txt``), so runbook text can be checked
against real output and the snapshots can serve as real incident queries.

Safety: every command is pinned to a ``k3d-`` kube context; nothing else is touched.

    python -m runbook_retriever.fault_capture            # all scenarios
    python -m runbook_retriever.fault_capture --only oom-killed,dns-wrong-service-name
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from runbook_retriever.config import get_settings
from runbook_retriever.io import write_text_atomic
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

DEFAULT_CONTEXT = "k3d-rr-faults"
AGENT_NODE = "k3d-rr-faults-agent-0"
SERVER_NODE = "k3d-rr-faults-server-0"
ALLOWED_PROGRAMS = ("kubectl", "k3d")
LOG_TAIL = 30
POLL_INTERVAL_S = 5.0


# --- Scenario schema -------------------------------------------------------------------


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # argv; the first element must be kubectl or k3d. kubectl gets --context injected.
    run: list[str] = Field(min_length=2)
    allow_fail: bool = False

    @field_validator("run")
    @classmethod
    def _program(cls, v: list[str]) -> list[str]:
        if v[0] not in ALLOWED_PROGRAMS:
            raise ValueError(f"step program must be one of {ALLOWED_PROGRAMS}, got {v[0]!r}")
        return v


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=50)
    runbook: str
    description: str
    manifests: str = ""
    steps: list[Step] = []
    expect: list[str] = Field(min_length=1)
    capture: list[list[str]] = []  # extra kubectl argv lists, output recorded as-is
    cleanup: list[Step] = []
    timeout_s: int = Field(default=180, ge=10, le=900)
    # Node-level scenarios (cordon, drain, stopping nodes) run one at a time, last.
    node_level: bool = False
    order: int = 0

    @field_validator("expect")
    @classmethod
    def _regexes_compile(cls, v: list[str]) -> list[str]:
        for pattern in v:
            re.compile(pattern)
        return v

    @property
    def namespace(self) -> str:
        return f"rr-{self.id}"[:63]


def load_scenarios(directory: Path) -> list[Scenario]:
    """Load ``faults/*.yaml``; files starting with ``_`` are metadata, not scenarios."""
    scenarios = [
        Scenario.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(directory.glob("*.yaml"))
        if not p.name.startswith("_")
    ]
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")
    return scenarios


# --- Running commands ------------------------------------------------------------------

Runner = Callable[[Sequence[str], str | None], "CmdResult"]


@dataclass(frozen=True)
class CmdResult:
    code: int
    out: str  # stdout + stderr, as an operator would see it


def subprocess_runner(argv: Sequence[str], stdin: str | None) -> CmdResult:
    proc = subprocess.run(
        list(argv), input=stdin, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return CmdResult(proc.returncode, (proc.stdout + proc.stderr).rstrip())


@dataclass
class Cluster:
    context: str
    run: Runner = subprocess_runner

    def __post_init__(self) -> None:
        if not self.context.startswith("k3d-"):
            raise ValueError(f"refusing to run against non-k3d context {self.context!r}")

    def kubectl(self, *args: str, stdin: str | None = None) -> CmdResult:
        return self.run(["kubectl", "--context", self.context, *args], stdin)

    def step(self, argv: Sequence[str], allow_fail: bool) -> CmdResult:
        argv = list(argv)
        result = self.kubectl(*argv[1:]) if argv[0] == "kubectl" else self.run(argv, None)
        if result.code != 0 and not allow_fail:
            raise RuntimeError(f"step {' '.join(argv)} failed:\n{result.out}")
        return result


def fill(text: str, scenario: Scenario) -> str:
    return (
        text.replace("{ns}", scenario.namespace)
        .replace("{agent}", AGENT_NODE)
        .replace("{server}", SERVER_NODE)
    )


# --- Capture ---------------------------------------------------------------------------


@dataclass
class Capture:
    sections: list[dict[str, str]] = field(default_factory=list)

    def add(self, title: str, command: str, output: str) -> None:
        self.sections.append({"title": title, "command": command, "output": output})

    @property
    def text(self) -> str:
        return "\n\n".join(
            f"### {s['title']}\n$ {s['command']}\n{s['output']}" for s in self.sections
        )


def _log_targets(pods: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(pod, container, previous) pairs worth reading: crashed or currently running."""
    targets: list[tuple[str, str, bool]] = []
    for pod in pods.get("items", []):
        name = pod["metadata"]["name"]
        status = pod.get("status", {})
        for cs in status.get("initContainerStatuses", []) + status.get("containerStatuses", []):
            if cs.get("restartCount", 0) > 0 or "terminated" in cs.get("lastState", {}):
                targets.append((name, cs["name"], True))
            state = cs.get("state", {})
            if "running" in state or "terminated" in state:
                targets.append((name, cs["name"], False))
    return targets


def capture_namespace(cluster: Cluster, scenario: Scenario) -> Capture:
    ns = scenario.namespace
    cap = Capture()

    def record(title: str, *args: str) -> None:
        result = cluster.kubectl(*args)
        cap.add(title, "kubectl " + " ".join(args), result.out)

    record("pods", "get", "pods", "-n", ns, "-o", "wide")
    pods_json = cluster.kubectl("get", "pods", "-n", ns, "-o", "json")
    pods = json.loads(pods_json.out) if pods_json.code == 0 and pods_json.out else {}
    if pods.get("items"):
        record("describe pods", "describe", "pods", "-n", ns)
    record("events", "get", "events", "-n", ns, "--sort-by=.lastTimestamp")
    for pod, container, previous in _log_targets(pods):
        args = ["logs", pod, "-n", ns, "-c", container, f"--tail={LOG_TAIL}"]
        if previous:
            args.append("--previous")
        record(f"logs {pod}/{container}{' (previous)' if previous else ''}", *args)
    for extra in scenario.capture:
        argv = [fill(a, scenario) for a in extra]
        record(" ".join(argv[:2]), *argv)
    return cap


def unmatched(scenario: Scenario, text: str) -> list[str]:
    return [p for p in scenario.expect if not re.search(p, text, re.MULTILINE)]


@dataclass
class Result:
    scenario: Scenario
    status: str  # ok | timeout | error
    capture: Capture
    missing: list[str]
    seconds: float
    error: str = ""


def run_scenario(
    cluster: Cluster,
    scenario: Scenario,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    keep: bool = False,
) -> Result:
    ns = scenario.namespace
    t0 = clock()
    cap = Capture()
    missing = list(scenario.expect)
    try:
        cluster.kubectl("delete", "namespace", ns, "--ignore-not-found", "--wait=true")
        cluster.step(["kubectl", "create", "namespace", ns], allow_fail=False)
        if scenario.manifests.strip():
            manifests = fill(scenario.manifests, scenario)
            res = cluster.kubectl("apply", "-n", ns, "-f", "-", stdin=manifests)
            if res.code != 0:
                raise RuntimeError(f"apply failed:\n{res.out}")
        for step in scenario.steps:
            cluster.step([fill(a, scenario) for a in step.run], step.allow_fail)
        while True:
            cap = capture_namespace(cluster, scenario)
            missing = unmatched(scenario, cap.text)
            if not missing:
                status = "ok"
                break
            if clock() - t0 > scenario.timeout_s:
                status = "timeout"
                break
            sleep(POLL_INTERVAL_S)
        return Result(scenario, status, cap, missing, clock() - t0)
    except Exception as e:  # report and move on; one broken scenario must not stop the run
        return Result(scenario, "error", cap, missing, clock() - t0, error=str(e))
    finally:
        for step in scenario.cleanup:
            cluster.step([fill(a, scenario) for a in step.run], allow_fail=True)
        if not keep:
            cluster.kubectl("delete", "namespace", ns, "--ignore-not-found", "--wait=false")


# --- Persistence -----------------------------------------------------------------------


def save(result: Result, out_dir: Path, versions: dict[str, str]) -> None:
    s = result.scenario
    record = {
        "id": s.id,
        "runbook": s.runbook,
        "description": s.description,
        "status": result.status,
        "missing": result.missing,
        "error": result.error,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seconds": round(result.seconds, 1),
        "versions": versions,
        "namespace": s.namespace,
        "sections": result.capture.sections,
    }
    write_text_atomic(
        out_dir / f"{s.id}.json", json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    )
    header = f"# {s.id} -> runbook/{s.runbook} [{result.status}]\n# {s.description}\n\n"
    write_text_atomic(out_dir / f"{s.id}.txt", header + result.capture.text + "\n")


def cluster_versions(cluster: Cluster) -> dict[str, str]:
    res = cluster.kubectl("version", "-o", "json")
    if res.code != 0:
        raise RuntimeError(f"cannot reach cluster {cluster.context}:\n{res.out}")
    data = json.loads(res.out[res.out.index("{") :])
    return {
        "client": data.get("clientVersion", {}).get("gitVersion", "?"),
        "server": data.get("serverVersion", {}).get("gitVersion", "?"),
    }


def run_all(
    cluster: Cluster, scenarios: list[Scenario], out_dir: Path, workers: int, keep: bool
) -> list[Result]:
    versions = cluster_versions(cluster)
    log.info("cluster %s: %s", cluster.context, versions)
    parallel = [s for s in scenarios if not s.node_level]
    serial = sorted((s for s in scenarios if s.node_level), key=lambda s: s.order)
    results: list[Result] = []

    def done(r: Result) -> None:
        save(r, out_dir, versions)
        level = logging.INFO if r.status == "ok" else logging.WARNING
        extra = f" missing={r.missing}" if r.missing else ""
        extra += f" error={r.error[:200]}" if r.error else ""
        log.log(level, "%-34s %-7s %5.0fs%s", r.scenario.id, r.status, r.seconds, extra)
        results.append(r)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in pool.map(lambda s: run_scenario(cluster, s, keep=keep), parallel):
            done(r)
    for s in serial:
        done(run_scenario(cluster, s, keep=keep))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--only", default="", help="comma-separated scenario ids")
    parser.add_argument("--context", default=DEFAULT_CONTEXT)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--keep", action="store_true", help="keep namespaces for debugging")
    args = parser.parse_args(argv)
    setup_logging()
    root = get_settings().root
    scenarios = load_scenarios(root / "faults")
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {s.id for s in scenarios}
        if unknown:
            parser.error(f"unknown scenario ids: {sorted(unknown)}")
        scenarios = [s for s in scenarios if s.id in wanted]
    results = run_all(
        Cluster(args.context), scenarios, root / "data" / "incidents", args.workers, args.keep
    )
    bad = [r.scenario.id for r in results if r.status != "ok"]
    log.info("%d/%d scenarios captured", len(results) - len(bad), len(results))
    if bad:
        log.warning("not captured: %s", ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
