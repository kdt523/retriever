---
title: Pods Evicted by node memory or disk pressure
scope: The kubelet evicts pods because the node is low on memory, disk or ephemeral storage, or a pod exceeds its ephemeral-storage limit.
tools: [kubectl get pods --field-selector status.phase=Failed, kubectl describe pod, kubectl describe node, kubectl top pods]
cautions:
  - Evicted pod objects stay around as Failed; deleting them is cleanup, not a fix.
  - BestEffort pods (no requests) are evicted first; giving everything requests changes eviction order cluster-wide.
related: [oomkilled, node-not-ready, pending-insufficient-resources]
---

Eviction is the kubelet protecting the node. The pod's message says which resource ran low.

## Symptoms

- Evicted pods end in phase `Failed`; `kubectl get pods` shows `STATUS Evicted`, or `ContainerStatusUnknown` with `Exit Code: 137` and `Message: The container could not be located when the pod was terminated`. A replacement pod is created.
- A `Warning Evicted` event from the kubelet, for example `Pod ephemeral local storage usage exceeds the total limit of containers 20Mi.`
- Or `The node was low on resource: memory. Threshold quantity: 100Mi, available: 87Mi. Container app was using 1.2Gi, request is 256Mi, has larger consumption of memory.`
- Or `The node had condition: [DiskPressure].`
- `kubectl describe node` shows `MemoryPressure True` or `DiskPressure True`, and taints such as `node.kubernetes.io/memory-pressure:NoSchedule`.

## Checks

1. Read the eviction message: `kubectl describe pod <evicted-pod>` under `Message`.
2. Check node conditions: `kubectl describe node <node>`.
3. Find the heavy consumers on that node: `kubectl top pods -A --sort-by=memory` filtered to the node.
4. For disk pressure, check large container logs, image cache and `emptyDir` volumes; on the host, `df -h` and `crictl images`.
5. Compare usage with requests: pods using far above their requests are evicted first.

## Likely causes

- Pods with memory requests far below real usage packed onto one node.
- Apps writing logs or temp files to the container filesystem or `emptyDir` without limits.
- Unused images filling the node disk.
- A memory leak in one workload pushing the node over the threshold.

## Fix

- Set realistic requests and limits so the scheduler spreads load correctly.
- Add `resources.limits.ephemeral-storage` and log rotation; use `emptyDir.sizeLimit`.
- Free disk: prune unused images (`crictl rmi --prune`), clean old logs.
- Clean up evicted pods afterwards: `kubectl delete pods --field-selector status.phase=Failed -n <ns>`.

## Rollback / escalation

If a recent deploy increased memory or disk use, roll it back. Escalate to the platform team when nodes are simply too small for the workload mix.
