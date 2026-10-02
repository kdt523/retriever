# Decision log

Short records of choices not spelled out in [PLAN.md](PLAN.md). Newest last.

## D1: Python 3.12 + uv instead of 3.11 + venv (2026-10-02)
`uv.lock` pins every dependency, so anyone can reproduce the results table exactly.
3.12 is fully supported by torch and sentence-transformers.

## D2: Train on the local GPU (2026-10-02)
The laptop has an RTX 3050 (4 GB). bge-small trains in fp16 with `CachedMultipleNegativesRankingLoss`
within that budget, so seeds and ablations run locally; Kaggle is a fallback only.

## D3: Library package + per-phase modules (2026-10-02)
PLAN.md lists flat scripts in `src/`. They live in `src/runbook_retriever/` instead and run as
`python -m runbook_retriever.<phase>`, so shared code (config, cache, run log) is importable and
unit-testable. Make targets hide the module paths.

## D4: Chunks are capped in model tokens (2026-10-02)
PLAN.md caps chunks at ~300 tokens but trains with `max_seq_length=256`, which would truncate
chunks silently. The full chunk (title + section + text) is capped at `MAX_SEQ_LENGTH`
model tokens, counted with the bge tokenizer.

## D5: LLM cache key excludes the model name (2026-10-02)
If the fallback model answered a prompt, reruns reuse that answer instead of spending quota.
The model that answered is stored in each cache entry and can be reported per query.

## D6: Corpus scope and size (2026-10-02)
kubernetes/website pinned at `7a1c866f`. Included: debugging tasks, pod/container configuration,
workloads, configuration, containers, services/networking, scheduling/eviction, storage, nodes,
jobs, the hand-written kubectl reference pages, and the DNS debugging page. Excluded: generated
kubectl command pages (mostly flag tables). Result: 3,292 chunks (above PLAN's 1,500-3,000).
Kept in full because a larger search space makes retrieval harder and the evaluation more honest;
Phase 2 can generate queries for a subset to stay inside Gemini quotas.

## D7: 27 runbooks with a fixed shape (2026-10-02)
One file per failure mode in `runbooks/`, YAML front matter (title, scope, tools, cautions,
related) plus sections Symptoms / Checks / Likely causes / Fix / Rollback / escalation, validated
by `runbooks.py` and a test. 27 (not 15-25) so the runbook stratum still has several documents
in val and test after the doc-level split. Front matter is stored in the chunk's `meta` and is
not embedded.

## D8: Short sections are merged, not dropped (2026-10-02)
PLAN says drop chunks under ~40 tokens. Short sections are instead folded into the next section
(with their heading as a lead-in line), so intro paragraphs and short troubleshooting tips survive.
A document is dropped only if all of it is under the minimum.

## D9: Code-heavy chunks stay in the corpus (2026-10-02)
Long manifests and command output split into chunks that are mostly YAML. They stay in the
corpus (they are realistic distractors and carry exact identifiers), but Phase 2 should skip
query generation for chunks that are almost entirely code.

## D10: Runbooks verified against a real cluster (2026-10-02)
`make cluster-up faults` injects 36 failures into a throwaway k3d cluster (k3s v1.35.5) and
records what Kubernetes really prints to `data/incidents/` (committed). A scenario only counts
as captured when its `expect` patterns appear in the real output. Runbook symptom text was
corrected against these captures; notable differences from commonly documented behaviour:
- crash loops show `STATUS Error` between restarts, not only `CrashLoopBackOff`;
- scheduler messages now append `no new claims to deallocate, preemption: ...`, and the
  insufficient-resources case says `Preemption is not helpful for scheduling`;
- the volume zone/node conflict now reads `didn't match PersistentVolume's node affinity`;
- NetworkPolicy blocks surface as `Connection refused` on kube-router (k3s) but as timeouts on
  Calico/Cilium, so the runbook no longer claims "always a timeout";
- Python on Alpine reports unknown hosts as `gaierror(-3, 'Try again')`;
- evicted pods can show `ContainerStatusUnknown` with exit code 137.
5 runbooks cannot be reproduced locally (metrics-, cert-manager-, ingress- or Helm-dependent);
they are listed with reasons in `faults/_unverified.yaml`, and a test enforces that every
runbook is either verified or listed there.

## D11: Leakage guard between captures and runbooks (2026-10-02)
Captures will serve as real "incident snapshot" test queries in Phase 2. Runbooks therefore use
the real Kubernetes message formats but different identifiers (pod names, IPs, ConfigMap names,
app log lines). `tests/test_fault_capture.py::test_runbooks_do_not_copy_capture_identifiers`
fails if any scenario-specific string appears in a runbook.

## D12: 35 runbooks (2026-10-02)
Added resource-quota-exceeded, rbac-forbidden, admission-denied, pdb-blocking-drain,
loadbalancer-pending, volume-node-affinity-conflict, statefulset-rollout-stuck and
helm-upgrade-failed to cover common production failures beyond pod crashes.
Corpus is now 3,340 chunks (165 from runbooks).
