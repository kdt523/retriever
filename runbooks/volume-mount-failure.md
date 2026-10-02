---
title: Volume attach or mount failures (FailedMount, Multi-Attach)
scope: A pod is scheduled but stays in ContainerCreating because a volume cannot be attached to the node or mounted into the pod.
tools: [kubectl describe pod, kubectl get volumeattachment, kubectl get pvc, kubectl get events]
cautions:
  - Force-detaching a disk that is still in use by another node can corrupt data.
  - Do not delete the old pod with --force on a node that is still running; the disk may still be written.
related: [pvc-pending, create-container-config-error, node-not-ready]
---

The pod waits in ContainerCreating; the events say which volume failed and why.

## Symptoms

- `STATUS ContainerCreating` for several minutes.
- `Multi-Attach error for volume "pvc-3f2a..." Volume is already exclusively attached to one node and can't be attached to another`.
- `Warning FailedMount` from the kubelet: `MountVolume.SetUp failed for volume "config" : configmap "exporter-config" not found` (pod `State: Waiting, Reason: ContainerCreating`).
- `Unable to attach or mount volumes: unmounted volumes=[data], unattached volumes=[data kube-api-access-x]: timed out waiting for the condition`.
- `FailedAttachVolume` or `FailedMount` events.

## Checks

1. `kubectl describe pod <pod>` and read the volume events.
2. For Multi-Attach, find where the volume is attached: `kubectl get volumeattachment | grep <pv-name>`, and check whether an old pod still runs on that node.
3. For ConfigMap/Secret volumes, check the object exists in the namespace.
4. Check the node and CSI driver health: `kubectl get pods -n kube-system` for the driver's node plugin on that node.

## Likely causes

- A `ReadWriteOnce` disk still attached to the node of a previous pod (common during rolling updates of single-replica stateful apps, or after a node failure).
- A ConfigMap or Secret volume that does not exist.
- A slow or broken CSI node plugin.
- Volume in a different availability zone than the node.

## Fix

- For RWO volumes with Deployments, use `strategy: Recreate` so the old pod releases the disk first.
- Wait for the old pod to terminate; if its node is gone, follow the node-not-ready runbook before detaching.
- Create the missing ConfigMap or Secret, or roll back the reference.
- Restart the CSI node plugin on the affected node.

## Rollback / escalation

Escalate to the platform team for stuck VolumeAttachments and zone mismatches. Never force-detach without confirming the old node is down.
