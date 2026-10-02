from __future__ import annotations

from typing import Any

from runbook_retriever.config import REPO_ROOT
from runbook_retriever.incident_queries import (
    build_queries,
    describe_lines,
    event_lines,
    iter_rows,
    log_lines,
    problem_pods,
)
from runbook_retriever.splits import load_doc_splits

PODS = """NAME                         READY   STATUS             RESTARTS      AGE   IP
cart-5d8f7c6b9d-x2k4l        0/1     CrashLoopBackOff   4 (12s ago)   2m    10.42.1.5
cart-5d8f7c6b9d-q9w8e        1/1     Running            0             2m    10.42.1.6
"""
EVENTS = """LAST SEEN   TYPE      REASON      OBJECT                      MESSAGE
2m          Normal    Scheduled   pod/cart-5d8f7c6b9d-x2k4l   Successfully assigned rr-crash-demo/cart-5d8f7c6b9d-x2k4l to k3d-rr-faults-agent-0
5s          Warning   BackOff     pod/cart-5d8f7c6b9d-x2k4l   Back-off restarting failed container cart in pod cart-5d8f7c6b9d-x2k4l_rr-crash-demo(1234)
"""
DESCRIBE = """Name:  cart-5d8f7c6b9d-x2k4l
Status:           Running
    State:          Waiting
      Reason:       CrashLoopBackOff
    Last State:     Terminated
      Reason:       Error
      Exit Code:    1
"""
LOGS = "2026/10/02 [notice] start worker process 36\nKeyError: 'CART_DB_URL'\n"


def record(**sections: str) -> dict[str, Any]:
    return {
        "id": "crash-demo",
        "namespace": "rr-crash-demo",
        "status": "ok",
        "sections": [{"title": t, "command": "", "output": o} for t, o in sections.items()],
    }


def test_problem_pods_keeps_only_unhealthy_rows_with_full_restart_column() -> None:
    assert problem_pods(PODS) == ["cart-5d8f7c6b9d-x2k4l 0/1 CrashLoopBackOff 4 (12s ago)"]


def test_event_lines_drop_routine_events() -> None:
    lines = event_lines(EVENTS)
    assert len(lines) == 1 and lines[0].startswith("Warning BackOff Back-off restarting")


def test_describe_lines_skip_running_and_dedupe() -> None:
    assert describe_lines(DESCRIBE) == [
        "State: Waiting",
        "Reason: CrashLoopBackOff",
        "Last State: Terminated",
        "Reason: Error",
        "Exit Code: 1",
    ]


def test_log_lines_ignore_startup_chatter() -> None:
    assert log_lines(LOGS) == ["KeyError: 'CART_DB_URL'"]
    assert log_lines("2026/10/02 [notice] start worker process 36\n") == []


def test_queries_are_anonymized_and_consistent() -> None:
    rec = record(
        pods=PODS,
        **{"describe pods": DESCRIBE, "events": EVENTS, "logs cart/cart": LOGS},
    )
    queries = build_queries(rec)
    for text in queries.values():
        assert "rr-crash-demo" not in text and "k3d-" not in text and "rr-faults" not in text
        assert "x2k4l" not in text, "pod hash must be re-randomized"
    full = queries["full"]
    pod = full.split()[0]
    assert f"{pod}_prod(" in full, "event must reference the same renamed pod"
    assert "KeyError: 'CART_DB_URL'" in full and "[notice]" not in full
    assert queries["brief"].count("|") == 1 and "Warning BackOff" in queries["brief"]


def test_real_captures_produce_labelled_queries() -> None:
    splits = load_doc_splits(REPO_ROOT / "data" / "splits" / "doc_splits.json")
    rows = list(iter_rows(REPO_ROOT / "data" / "incidents", REPO_ROOT / "faults", dict(splits)))
    assert len(rows) == 2 * len(list((REPO_ROOT / "data" / "incidents").glob("*.json")))
    for r in rows:
        assert r["query"].strip(), r["qid"]
        assert r["doc_id"] in r["relevant_docs"]
        # Real reason strings like "OOMKilled" may match a runbook name; that is the symptom,
        # not a leak. The scenario id (namespace) must never appear.
        assert "rr-" + r["scenario"] not in r["query"], f"{r['qid']} leaks its scenario id"
