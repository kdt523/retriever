---
title: PersistentVolumeClaim stuck Pending
scope: A PVC is never bound to a volume, so pods that mount it stay Pending.
tools: [kubectl get pvc, kubectl describe pvc, kubectl get storageclass, kubectl get pv]
cautions:
  - Never delete a PVC or PV that holds data without a confirmed backup; reclaim policy Delete destroys the disk.
  - Do not change the default StorageClass without checking every workload that relies on it.
related: [volume-mount-failure, pending-insufficient-resources]
---

Check first whether Pending is expected: with `WaitForFirstConsumer`, a PVC stays Pending until a pod uses it.

## Symptoms

- `kubectl get pvc` shows `STATUS Pending` for minutes.
- The pod is `Pending` with `FailedScheduling: 0/2 nodes are available: pod has unbound immediate PersistentVolumeClaims. not found`.
- The PVC has a `Warning ProvisioningFailed` event from `persistentvolume-controller`: `storageclass.storage.k8s.io "premium-rwo" not found`, or `no persistent volumes available for this claim and no storage class is set`.
- Or `ProvisioningFailed` with a cloud error such as quota exceeded or an unsupported zone.
- Normal and harmless: `waiting for first consumer to be created before binding`.

## Checks

1. `kubectl describe pvc <name>` and read the events.
2. Check the requested StorageClass exists: `kubectl get storageclass`; the default one is marked `(default)`.
3. For static provisioning, check a PV with matching size, access mode and class exists: `kubectl get pv`.
4. Check the access mode: `ReadWriteMany` is not supported by most block storage drivers.
5. Check the provisioner (CSI driver) pods are running in `kube-system`.

## Likely causes

- The manifest names a StorageClass that does not exist in this cluster.
- No default StorageClass and none specified.
- Access mode or size that no available PV or driver supports.
- The CSI driver is not installed or is crashing; cloud disk quota exhausted.

## Fix

- Use an existing StorageClass name in the PVC (PVC specs are immutable; recreate the PVC if it holds no data).
- Mark a suitable class default: `kubectl annotate storageclass <name> storageclass.kubernetes.io/is-default-class=true`.
- Switch to `ReadWriteOnce` if shared access is not needed.
- Fix or install the CSI driver.

## Rollback / escalation

Roll back the deploy that introduced the claim if the workload worked before. Escalate to the platform team for driver failures and cloud quotas.
