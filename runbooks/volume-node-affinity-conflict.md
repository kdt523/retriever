---
title: Pod Pending with volume node affinity conflict
scope: A pod that uses an existing PersistentVolume cannot be scheduled because the volume is pinned to a zone or node where the pod cannot run.
tools: [kubectl describe pod, kubectl get pv -o yaml, kubectl get nodes -L topology.kubernetes.io/zone, kubectl describe storageclass]
cautions:
  - Deleting the PVC to get a new volume in the right zone loses its data unless it is backed up or snapshotted.
  - Local PersistentVolumes are tied to one node; their data cannot follow the pod elsewhere.
related: [pvc-pending, pending-taints-affinity, node-not-ready]
---

Block volumes such as EBS or Persistent Disk live in one availability zone, and local volumes live on one node. A pod using them can only run there.

## Symptoms

- The pod is `Pending` with `Warning FailedScheduling`. Current Kubernetes versions word it `0/2 nodes are available: 1 node(s) didn't match PersistentVolume's node affinity, 1 node(s) didn't match Pod's node affinity/selector. no new claims to deallocate, preemption: 0/2 nodes are available: 2 Preemption is not helpful for scheduling.`
- Older versions say `0/3 nodes are available: 3 node(s) had volume node affinity conflict.`
- `kubectl get pvc` shows the claim `Bound`; the PV's node affinity (zone or `kubernetes.io/hostname`) names a node the pod is not allowed on.
- Often after a node group change, a zone outage, or when a StatefulSet pod is rescheduled after its node was removed.

## Checks

1. Find the volume: `kubectl get pvc <claim> -o jsonpath='{.spec.volumeName}'`.
2. Read its affinity: `kubectl get pv <pv> -o yaml` under `spec.nodeAffinity` (zone or hostname).
3. List nodes per zone: `kubectl get nodes -L topology.kubernetes.io/zone`, and check whether any schedulable node matches.
4. Check the pod's own nodeSelector, affinity and tolerations, which may exclude the only matching nodes.
5. Check the StorageClass `volumeBindingMode`; `Immediate` can create volumes in a zone with no suitable nodes.

## Likely causes

- No healthy, schedulable node left in the volume's zone (scaled down, cordoned, zone outage).
- The pod's own constraints exclude every node in that zone.
- A local PV whose node was deleted.
- A StorageClass with `Immediate` binding that provisioned the volume in the wrong zone.

## Fix

- Add or uncordon a node in the volume's zone.
- Relax pod constraints that exclude that zone.
- For new volumes, use `volumeBindingMode: WaitForFirstConsumer` so volumes are created where the pod is scheduled.
- To move data to another zone, restore from a snapshot into a new PVC.

## Rollback / escalation

Revert node-group or affinity changes that removed the zone. Escalate to the platform team for zone capacity and data migration.
