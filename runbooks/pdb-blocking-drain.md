---
title: Node drain blocked by a PodDisruptionBudget
scope: kubectl drain or a node upgrade cannot evict a pod because its PodDisruptionBudget currently allows zero disruptions.
tools: [kubectl get pdb, kubectl describe pdb, kubectl drain, kubectl get pods -o wide, kubectl uncordon]
cautions:
  - Deleting a PDB or using drain --disable-eviction bypasses availability guarantees; the protected app can go fully down.
  - A drained node stays cordoned (SchedulingDisabled) after a failed drain until you uncordon it.
related: [node-not-ready, pending-insufficient-resources]
---

The PDB is doing its job. The fix is almost always more replicas or a looser budget, not forcing the eviction.

## Symptoms

- `kubectl drain` loops on `error when evicting pods/"search-indexer-6f7d8c9b54-w4n2k" -n "search" (will retry after 5s): Cannot evict pod as it would violate the pod's disruption budget.`
- With a timeout it ends in `error: unable to drain node "worker-2" due to error: error when evicting pods/"search-indexer-..." -n "search": global timeout reached: 20s, continuing command...`.
- `kubectl get pdb` shows `ALLOWED DISRUPTIONS 0`, for example `search-indexer 1 N/A 0`.
- Cluster or node-pool upgrades stall on one node; the node shows `Ready,SchedulingDisabled`.

## Checks

1. Find the blocking pods in the drain output and their PDB: `kubectl get pdb -n <ns>`.
2. `kubectl describe pdb <name>`: compare `Min available` / `Max unavailable` with current healthy pods.
3. Check replicas: a single-replica Deployment with `minAvailable: 1` can never be evicted voluntarily.
4. Check whether the other replicas are unhealthy, which also brings allowed disruptions to zero.
5. Check where the replicas run: all on the node being drained means a drain will always block.

## Likely causes

- `minAvailable` equal to the replica count (often 1 with 1 replica).
- Other replicas not Ready, so the budget is already used up.
- All replicas scheduled on the same node.

## Fix

- Scale the workload up so one pod can move: `kubectl scale deployment/search-indexer --replicas=2 -n search`, then retry the drain.
- Use `maxUnavailable: 1` instead of `minAvailable` equal to the replica count.
- Fix unhealthy replicas first; then the budget allows a disruption.
- Spread replicas with topology spread constraints or anti-affinity.
- After maintenance or a failed drain: `kubectl uncordon <node>`.

## Rollback / escalation

Uncordon the node if the maintenance is postponed. Escalate to the app owner before deleting a PDB or force-deleting pods.
