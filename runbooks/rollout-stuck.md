---
title: Deployment rollout stuck (ProgressDeadlineExceeded)
scope: A Deployment update does not finish because new pods never become available, or new pods cannot even be created.
tools: [kubectl rollout status, kubectl describe deployment, kubectl get rs, kubectl describe rs, kubectl get resourcequota]
cautions:
  - Pausing a rollout leaves mixed versions running; resume or undo it promptly.
  - Raising maxUnavailable to push a rollout through can take capacity offline.
related: [image-pull-backoff, readiness-probe-failing, pending-insufficient-resources, bad-release-5xx, resource-quota-exceeded]
---

A stuck rollout is a symptom; the new ReplicaSet's pods tell you the real cause.

## Symptoms

- `kubectl rollout status deployment/orders` keeps printing `Waiting for deployment "orders" rollout to finish: 1 out of 3 new replicas have been updated...` and finally `error: deployment "orders" exceeded its progress deadline`.
- `kubectl describe deployment` shows conditions `Available True MinimumReplicasAvailable` (old pods still serve) and `Progressing False ProgressDeadlineExceeded`, plus `NewReplicaSet: api-gateway-5d8f7c6b9d (1/1 replicas created)` next to `OldReplicaSets`.
- Old and new ReplicaSets both have pods; the new pods are stuck (for example `ErrImagePull`) and `UP-TO-DATE` stays below desired.
- ReplicaSet events may show `FailedCreate`: `Error creating: pods "etl-7c9b6d8f45-p2xnq" is forbidden: exceeded quota: team-quota, requested: limits.memory=1Gi,requests.memory=512Mi, used: limits.memory=3584Mi,requests.memory=2Gi, limited: limits.memory=4Gi,requests.memory=4Gi`.

## Checks

1. `kubectl describe deployment <name>` and read `Conditions` and events.
2. Find the new ReplicaSet: `kubectl get rs -l app=<name>`; then `kubectl describe rs <new-rs>` for `FailedCreate` events.
3. Inspect the new pods: are they Pending, ImagePullBackOff, CrashLoopBackOff, or Running but not Ready?
4. Check quotas: `kubectl describe resourcequota -n <ns>`.
5. Check whether admission webhooks rejected the pods (events mention `admission webhook ... denied the request`).

## Likely causes

- New pods failing: bad image, crash, failing readiness probe.
- Namespace ResourceQuota leaves no room for surge pods.
- Unschedulable new pods (insufficient resources, affinity).
- An admission policy rejecting the new pod spec.

## Fix

- Undo the rollout: `kubectl rollout undo deployment/<name>` restores the previous ReplicaSet.
- Then fix the underlying cause using the matching runbook (image pull, crash loop, readiness, pending).
- For quota problems, raise the quota or set `maxSurge: 0` with `maxUnavailable: 1`.

## Rollback / escalation

Rollback is the default action for a stuck rollout. Escalate to the service owner with the new ReplicaSet's pod events if the cause is not obvious.
