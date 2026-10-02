---
title: Pods Pending due to insufficient CPU or memory
scope: The scheduler cannot find a node with enough unreserved CPU or memory to satisfy a pod's resource requests.
tools: [kubectl describe pod, kubectl describe nodes, kubectl top nodes, kubectl get resourcequota]
cautions:
  - Lowering requests below real usage causes throttling and OOM kills later.
  - Requests, not actual usage, decide scheduling; a node can look idle and still be full.
related: [pending-taints-affinity, rollout-stuck, hpa-not-scaling]
---

A pod stays in Pending because the sum of requests on every node leaves no room for it.

## Symptoms

- `kubectl get pods` shows `STATUS Pending` with no node assigned for minutes.
- A `Warning FailedScheduling` event from `default-scheduler`: `0/2 nodes are available: 2 Insufficient memory. no new claims to deallocate, preemption: 0/2 nodes are available: 2 Preemption is not helpful for scheduling.`
- Or `3 Insufficient cpu`; when lower-priority pods could be evicted, the preemption part says `No preemption victims found for incoming pod` instead.
- A scale-up or rollout stalls with new pods Pending while old ones keep running.

## Checks

1. Read the scheduler message: `kubectl describe pod <pod>` under `Events`; it says which resource is short and on how many nodes.
2. Compare the pod's requests with node capacity: `kubectl describe nodes | grep -A 8 "Allocated resources"`.
3. Check what the pod asks for: `kubectl get pod <pod> -o jsonpath='{.spec.containers[*].resources}'`. A typo such as `memory: 64Gi` instead of `64Mi` is common.
4. Check namespace quotas: `kubectl describe resourcequota -n <ns>`.
5. If the cluster has an autoscaler, check whether it is adding nodes or has hit its maximum.

## Likely causes

- A deploy raised requests (or added a replica) beyond remaining capacity.
- Too many replicas for a small cluster.
- Requests set far above real usage across many workloads.
- A node was removed or became NotReady, shrinking capacity.

## Fix

- If a recent change raised requests by mistake, roll back: `kubectl rollout undo deployment/<name>`.
- Right-size requests to observed usage: `kubectl set resources deployment/<name> --requests=cpu=100m,memory=128Mi`.
- Add capacity: scale the node group, or free room by scaling down non-critical workloads.
- Use a PriorityClass so critical pods can preempt less important ones.

## Rollback / escalation

Rollback is safe; old replicas are still running. Escalate to the platform team when the cluster is genuinely full and needs more nodes.
