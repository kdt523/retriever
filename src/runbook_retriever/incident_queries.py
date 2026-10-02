"""Turn real cluster captures (``data/incidents/*.json``) into incident-snapshot queries.

Each capture yields two queries, shaped like what an on-call engineer or agent pastes:
- ``full``:  problem pod rows + key ``describe`` fields + non-routine events + error log
             lines + error lines from scenario-specific commands;
- ``brief``: problem pod row + the single most telling event / error line.

Captures are anonymized first: the namespace (``rr-<scenario-id>``, which names the
answer), node names and pod hashes are replaced, so nothing but the symptoms remains.
The label is the scenario's runbook (all of its chunks are relevant).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from runbook_retriever.config import get_settings
from runbook_retriever.fault_capture import load_scenarios
from runbook_retriever.gen_queries import randomize_names
from runbook_retriever.io import write_jsonl
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.splits import load_doc_splits

log = logging.getLogger(__name__)

MAX_WORDS = 160
ROUTINE_EVENTS = frozenset(
    """Scheduled SuccessfulCreate ScalingReplicaSet Pulled Pulling Created Started
    SuccessfulDelete SandboxChanged Completed RegisteredNode Starting""".split()
)
_ERRORISH = re.compile(
    r"error|fail|forbidden|denied|cannot|can't|not found|refused|timed out|timeout|exceeded|"
    r"unknown|notready|pending|waiting|evict|oom|back-?off|unhealthy|invalid|unable|traceback|"
    r"exception|panic|no such|permission",
    re.IGNORECASE,
)
_STANDARD = ("pods", "describe pods", "events")


def anonymize(text: str, namespace: str) -> str:
    text = text.replace(namespace, "prod")
    text = re.sub(r"k3d-rr-faults-agent-0", "worker-1", text)
    text = re.sub(r"k3d-rr-faults-server-0", "worker-2", text)
    text = text.replace("rr-faults", "cluster")
    return randomize_names(text)


def _rows(table: str) -> list[list[str]]:
    lines = [ln for ln in table.splitlines() if ln.strip()]
    return [ln.split() for ln in lines[1:]] if len(lines) > 1 else []


def problem_pods(table: str) -> list[str]:
    """``NAME READY STATUS RESTARTS`` of pods that are not fully ready and running."""
    out = []
    for cols in _rows(table):
        if len(cols) < 4 or "/" not in cols[1]:
            continue
        ready, total = cols[1].split("/", 1)
        restarts = f"{cols[3]} {cols[4]} {cols[5]}" if cols[4].startswith("(") else cols[3]
        if ready != total or cols[2] != "Running" or restarts != "0":
            out.append(f"{cols[0]} {cols[1]} {cols[2]} {restarts}")
    return out[:3]


def describe_lines(text: str) -> list[str]:
    keep = re.compile(r"^\s*(Status|State|Reason|Exit Code|Message|Last State):\s*(.+)$")
    out: list[str] = []
    for line in text.splitlines():
        m = keep.match(line)
        if m and m.group(2).strip() not in ("Running", "<none>"):
            item = f"{m.group(1)}: {' '.join(m.group(2).split())}"
            if item not in out:
                out.append(item)
    return out[:8]


def event_lines(table: str) -> list[str]:
    out: list[str] = []
    for line in table.splitlines()[1:]:
        cols = line.split(None, 4)
        if len(cols) < 5 or cols[2] in ROUTINE_EVENTS:
            continue
        item = f"{cols[1]} {cols[2]} {cols[4]}"
        if item not in out:
            out.append(item)
    return out[:4]


def log_lines(text: str) -> list[str]:
    """Error-like log lines only (startup chatter such as nginx notices is not a symptom)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.startswith(("unable to retrieve", "Error from server"))]
    return [ln for ln in lines if _ERRORISH.search(ln)][-2:]


def build_queries(record: dict[str, Any]) -> dict[str, str]:
    """``{"full": ..., "brief": ...}`` for one capture record."""
    sections = {s["title"]: s["output"] for s in record["sections"]}
    pods = problem_pods(sections.get("pods", ""))
    describe = describe_lines(sections.get("describe pods", ""))
    events = event_lines(sections.get("events", ""))
    logs = list(
        dict.fromkeys(
            ln
            for title, out in sections.items()
            if title.startswith("logs")
            for ln in log_lines(out)
        )
    )[:2]
    extra_lines = [
        ln.strip()
        for title, out in sections.items()
        if title not in _STANDARD and not title.startswith("logs")
        for ln in out.splitlines()
        if _ERRORISH.search(ln) or re.search(r"<pending>|<unknown>|NotReady", ln)
    ]
    # Strong errors first, so the 4-line cap never drops the decisive line.
    strong = re.compile(r"error|forbidden|denied|cannot|failed", re.IGNORECASE)
    extras = sorted(dict.fromkeys(extra_lines), key=lambda ln: not strong.search(ln))[:4]

    full_parts = pods + describe + [f"event: {e}" for e in events]
    full_parts += [f"log: {ln}" for ln in logs] + extras
    warnings = [e for e in events if e.startswith("Warning")]
    candidates = warnings + [f"log: {ln}" for ln in logs] + extras + events + describe
    brief_parts = pods[:1] + candidates[:1]

    def finish(parts: list[str]) -> str:
        text = " | ".join(dict.fromkeys(p for p in parts if p))
        words = anonymize(" ".join(text.split()), record["namespace"]).split()
        return " ".join(words[:MAX_WORDS])

    return {"full": finish(full_parts), "brief": finish(brief_parts)}


def iter_rows(
    incidents_dir: Path, faults_dir: Path, doc_splits: dict[str, str]
) -> Iterator[dict[str, Any]]:
    scenarios = {s.id: s for s in load_scenarios(faults_dir)}
    for path in sorted(incidents_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        scenario = scenarios[record["id"]]
        if record["status"] != "ok":
            log.warning("skipping %s: capture status %s", record["id"], record["status"])
            continue
        for variant, query in build_queries(record).items():
            yield {
                "qid": f"incident/{record['id']}/{variant}",
                "query": query,
                "variant": variant,
                "scenario": record["id"],
                "doc_id": f"runbook/{record['runbook']}",
                "relevant_docs": [
                    f"runbook/{rb}" for rb in [scenario.runbook, *scenario.also_relevant]
                ],
                "runbook_split": doc_splits[f"runbook/{record['runbook']}"],
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    setup_logging()
    paths = get_settings().paths
    doc_splits = load_doc_splits(paths.splits / "doc_splits.json")
    rows = list(iter_rows(paths.data / "incidents", paths.root / "faults", dict(doc_splits)))
    out = paths.data / "queries" / "incident_queries.jsonl"
    write_jsonl(out, rows)
    log.info("wrote %d incident queries to %s", len(rows), out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
