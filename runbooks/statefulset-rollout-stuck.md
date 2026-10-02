---
title: StatefulSet rolling update stuck
scope: A StatefulSet update stops partway because an updated pod never becomes Ready, and the ordered update strategy refuses to continue or roll back on its own.
tools: [kubectl rollout status statefulset, kubectl describe statefulset, kubectl get pods -o wide, kubectl rollout undo statefulset, kubectl get controllerrevisions]
cautions:
  - Do not delete PVCs of a StatefulSet to unstick it; that deletes the data of that replica.
  - Force-deleting a StatefulSet pod on an unreachable node can start two copies of the same member.
related: [rollout-stuck, crashloop-app-error, image-pull-backoff, pod-stuck-terminating]
---

StatefulSets update one pod at a time from the highest ordinal down. If the first updated pod is broken, the update waits forever, and a known limitation means fixing the template does not replace the broken pod automatically.

## Symptoms

- `kubectl rollout status statefulset/db` keeps printing `Waiting for 1 pods to be ready...` (with a timeout: `error: timed out waiting for the condition`), or `waiting for statefulset rolling update to complete 1 pods at revision db-6f9d7c8b4...`.
- The highest-ordinal pod (for example `db-2`) is `CrashLoopBackOff`, `ImagePullBackOff` or `0/1 Running`, while `db-0` and `db-1` still run the old revision.
- `kubectl get statefulset db` shows `READY 2/3`; `currentRevision` and `updateRevision` differ in `kubectl get sts db -o yaml`.
- After rolling the template back, `db-2` stays broken until it is deleted.

## Checks

1. Identify the stuck pod and why it fails: `kubectl describe pod db-2` and `kubectl logs db-2 --previous`.
2. Compare revisions: `kubectl get controllerrevisions -l app=db` and `kubectl rollout history statefulset/db`.
3. Check `spec.updateStrategy` (`RollingUpdate` with `partition`, or `OnDelete`) and `podManagementPolicy`.
4. Check the pod's PVC is Bound and mounted (`kubectl get pvc -l app=db`).

## Likely causes

- A bad image, config or probe in the new revision, so the first updated pod never becomes Ready.
- A data migration in the new version failing on existing data.
- A `partition` value left set, so only some ordinals are meant to update.

## Fix

- Roll the template back: `kubectl rollout undo statefulset/db`.
- Then delete the stuck pod so it is recreated from the restored template: `kubectl delete pod db-2` (its PVC and data are kept).
- Fix the new version and roll out again, optionally with `partition` to canary one ordinal first.

## Rollback / escalation

Undo plus deleting the broken pod is the standard rollback. Escalate to the database or service owner before deleting pods of a quorum-based system (etcd, ZooKeeper, Kafka), and never delete PVCs during the incident.
