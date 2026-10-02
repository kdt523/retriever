---
title: Pods Pending due to taints, node selectors or affinity
scope: Nodes have capacity, but the pod's scheduling constraints (nodeSelector, node affinity, pod anti-affinity, missing tolerations) rule every node out.
tools: [kubectl describe pod, kubectl get nodes --show-labels, kubectl describe node, kubectl get deployment -o yaml]
cautions:
  - Removing a taint from a node affects every workload, not just this one.
  - Do not add a blanket toleration for control-plane taints to application pods.
related: [pending-insufficient-resources, node-not-ready]
---

The scheduler message names each filter that failed. Read it carefully; it usually points straight at the cause.

## Symptoms

- `STATUS Pending` with `FailedScheduling` events like `0/2 nodes are available: 2 node(s) didn't match Pod's node affinity/selector. no new claims to deallocate, preemption: 0/2 nodes are available: 2 Preemption is not helpful for scheduling.`
- Mixed causes are listed together: `0/3 nodes are available: 1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 2 node(s) didn't match Pod's node affinity/selector.`
- Anti-affinity: `0/2 nodes are available: 2 node(s) didn't match pod anti-affinity rules. ... preemption: 0/2 nodes are available: 2 No preemption victims found for incoming pod.`
- Or `1 node(s) had untolerated taint {node.kubernetes.io/unreachable: }`.
- New replicas stay Pending even though `kubectl top nodes` shows free CPU and memory.

## Checks

1. Read the full `FailedScheduling` message in `kubectl describe pod <pod>`.
2. List node labels: `kubectl get nodes --show-labels` and compare with the pod's `nodeSelector` and `affinity` (`kubectl get deploy <name> -o yaml`).
3. List node taints: `kubectl describe node <node> | grep Taints` and compare with the pod's `tolerations`.
4. For anti-affinity, count replicas versus eligible nodes: a required anti-affinity on hostname with 4 replicas cannot fit on 3 nodes.

## Likely causes

- A deploy added a `nodeSelector` for a label no node has (for example `disktype: ssd`).
- A node pool was replaced and lost its labels.
- Nodes were tainted for maintenance (`kubectl cordon` or `kubectl taint`), or are tainted unreachable.
- `requiredDuringSchedulingIgnoredDuringExecution` anti-affinity with more replicas than nodes.

## Fix

- Wrong selector or affinity from a deploy: `kubectl rollout undo deployment/<name>`.
- Missing node labels: relabel the intended nodes, `kubectl label node <node> disktype=ssd`.
- Maintenance taints: `kubectl uncordon <node>` when maintenance is done.
- Switch hard anti-affinity to `preferredDuringSchedulingIgnoredDuringExecution`, or use topology spread constraints.

## Rollback / escalation

Roll back manifest changes first. Escalate to the platform team for node pool labels and taints; they are shared infrastructure.
