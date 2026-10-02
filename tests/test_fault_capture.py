from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from runbook_retriever.config import REPO_ROOT
from runbook_retriever.fault_capture import (
    Cluster,
    CmdResult,
    Scenario,
    _log_targets,
    load_scenarios,
    run_scenario,
)
from runbook_retriever.runbooks import load_runbooks

FAULTS = REPO_ROOT / "faults"
INCIDENTS = REPO_ROOT / "data" / "incidents"


# --- Scenario files ------------------------------------------------------------------


def test_scenarios_reference_existing_runbooks() -> None:
    runbooks = {rb.id for rb in load_runbooks(REPO_ROOT / "runbooks")}
    scenarios = load_scenarios(FAULTS)
    assert len(scenarios) >= 30
    assert {s.runbook for s in scenarios} <= runbooks


def test_every_runbook_is_verified_or_explained() -> None:
    runbooks = {rb.id for rb in load_runbooks(REPO_ROOT / "runbooks")}
    covered = {s.runbook for s in load_scenarios(FAULTS)}
    unverified = yaml.safe_load((FAULTS / "_unverified.yaml").read_text(encoding="utf-8"))
    assert set(unverified) <= runbooks, "unknown runbook in _unverified.yaml"
    assert not set(unverified) & covered, "runbook is both verified and listed as unverified"
    assert runbooks == covered | set(unverified), (
        f"unaccounted: {runbooks - covered - set(unverified)}"
    )


def test_every_scenario_has_a_successful_capture() -> None:
    for s in load_scenarios(FAULTS):
        path = INCIDENTS / f"{s.id}.json"
        assert path.is_file(), f"no capture for {s.id}; run make faults"
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["status"] == "ok", f"{s.id}: capture status {record['status']}"


# --- Leakage guard -------------------------------------------------------------------
# Captures become real "incident snapshot" test queries. Runbooks must use the real
# Kubernetes message formats but never the scenario-specific identifiers, or retrieval
# scores on that slice would be inflated by copied strings.

# Controller-generated names: ReplicaSets / revisions ("frontend-7979df944d") and pods.
_GENERATED_NAME = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[a-f0-9]{8,10}(?:-[a-z0-9]{5})?\b")
_CLUSTER_IP = re.compile(r"\b10\.4[23]\.\d{1,3}\.\d{1,3}\b")
# "/healthz" is the de-facto standard probe path, used throughout the k8s docs corpus.
_GENERIC_VALUES = {
    "local-path",
    "ReadWriteOnce",
    "postgres",
    "redis",
    "info",
    "python",
    "sh",
    "-c",
    "/healthz",
}
_IDENTIFIER_KEYS = {
    "name", "claimName", "image", "key", "value", "policyName", "serviceName",
    "loadBalancerClass", "storageClassName", "message", "command", "path",
}  # fmt: skip


def _manifest_identifiers(manifests: str) -> set[str]:
    found: set[str] = set()

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif (
            isinstance(node, str)
            and key in _IDENTIFIER_KEYS | {"finalizers"}
            and ("-" in node or ":" in node or "/" in node or len(node) >= 12)
            and node not in _GENERIC_VALUES
            and not node.startswith("kubernetes.io/")
        ):
            found.add(node.removesuffix("-NS"))

    # Templated names ("max-replicas-{ns}") are checked by their fixed stem.
    text = manifests.replace("{ns}", "NS").replace("{agent}", "NODE").replace("{server}", "NODE")
    for doc in yaml.safe_load_all(text):
        walk(doc)
    return found


def scenario_fingerprints(scenario: Scenario) -> set[str]:
    tokens = _manifest_identifiers(scenario.manifests) if scenario.manifests else set()
    # Distinctive strings inside inline scripts (log messages, URLs, env names).
    tokens |= set(re.findall(r"[\"']([^\"'{}]{12,})[\"']", scenario.manifests))
    tokens = {
        t
        for t in tokens
        if t not in _GENERIC_VALUES and not t.startswith(("http.server", "kubernetes.io"))
    }
    path = INCIDENTS / f"{scenario.id}.json"
    if path.is_file():
        for sec in json.loads(path.read_text(encoding="utf-8"))["sections"]:
            out = sec["output"]
            tokens |= set(_GENERATED_NAME.findall(out)) | set(_CLUSTER_IP.findall(out))
            if sec["title"].startswith("logs"):
                tokens |= {ln.strip() for ln in out.splitlines() if len(ln.strip()) >= 15}
    return tokens


def test_runbooks_do_not_copy_capture_identifiers() -> None:
    texts = {
        rb.id: rb.path.read_text(encoding="utf-8") for rb in load_runbooks(REPO_ROOT / "runbooks")
    }
    leaks = [
        f"{rb_id}: {token!r} (from {s.id})"
        for s in load_scenarios(FAULTS)
        for token in sorted(scenario_fingerprints(s))
        for rb_id, text in texts.items()
        if token in text
    ]
    assert not leaks, "runbooks contain scenario-specific strings:\n  " + "\n  ".join(leaks)


# --- Runner logic (fake kubectl, no cluster) ------------------------------------------


class FakeRunner:
    """Answers `get pods -o json` with no pods and `get events` with scripted outputs."""

    def __init__(self, events: list[str]) -> None:
        self.events = list(events)
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], stdin: str | None) -> CmdResult:
        argv = list(argv)
        self.calls.append(argv)
        if "json" in argv:
            return CmdResult(0, '{"items": []}')
        if "events" in argv:
            return CmdResult(0, self.events.pop(0) if len(self.events) > 1 else self.events[0])
        return CmdResult(0, "")


def scenario(**kw: Any) -> Scenario:
    base: dict[str, Any] = {
        "id": "demo",
        "runbook": "oomkilled",
        "description": "d",
        "expect": ["OOMKilled", r"Exit Code:\s+137"],
        "timeout_s": 30,
    }
    return Scenario.model_validate(base | kw)


def test_run_scenario_polls_until_all_patterns_match() -> None:
    runner = FakeRunner(["nothing yet", "Reason: OOMKilled", "OOMKilled\nExit Code:   137"])
    clock = iter(range(0, 1000, 5))
    result = run_scenario(
        Cluster("k3d-test", runner), scenario(), sleep=lambda _: None, clock=lambda: next(clock)
    )
    assert result.status == "ok" and result.missing == []
    assert all(c[:3] == ["kubectl", "--context", "k3d-test"] for c in runner.calls)
    cleanup = ["delete", "namespace", "rr-demo", "--ignore-not-found", "--wait=false"]
    assert ["kubectl", "--context", "k3d-test", *cleanup] in runner.calls


def test_run_scenario_times_out_with_missing_patterns() -> None:
    runner = FakeRunner(["Reason: OOMKilled"])
    clock = iter(range(0, 1000, 10))
    result = run_scenario(
        Cluster("k3d-test", runner), scenario(), sleep=lambda _: None, clock=lambda: next(clock)
    )
    assert result.status == "timeout"
    assert result.missing == [r"Exit Code:\s+137"]


def test_refuses_non_k3d_context() -> None:
    with pytest.raises(ValueError, match="non-k3d"):
        Cluster("prod-eks")


def test_steps_only_allow_kubectl_and_k3d() -> None:
    with pytest.raises(ValueError, match="step program"):
        scenario(steps=[{"run": ["bash", "-c", "rm -rf /"]}])


def test_log_targets_prefers_previous_for_restarted_containers() -> None:
    pods = {
        "items": [
            {
                "metadata": {"name": "p"},
                "status": {
                    "initContainerStatuses": [{"name": "init", "state": {"running": {}}}],
                    "containerStatuses": [
                        {"name": "app", "restartCount": 2, "state": {"waiting": {}}},
                    ],
                },
            }
        ]
    }
    assert _log_targets(pods) == [("p", "init", False), ("p", "app", True)]


def test_scenario_namespace_is_prefixed(tmp_path: Path) -> None:
    assert scenario(id="oom-killed").namespace == "rr-oom-killed"
