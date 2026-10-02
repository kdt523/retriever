---
title: Error rate spike after a release (bad deploy)
scope: Pods run and pass health checks, but a new version returns HTTP 5xx errors for real requests.
tools: [kubectl rollout history, kubectl rollout undo, kubectl logs, error_rate metric, kubectl get rs]
cautions:
  - Health checks passing does not mean the release is good; compare error rates by version.
  - Roll back first and investigate after; do not debug a bad release in production.
related: [rollout-stuck, crashloop-app-error, dependency-down, ingress-502-503-504]
---

The strongest evidence is timing: an error spike that begins right after a new ReplicaSet appears.

## Symptoms

- HTTP 5xx rate jumps (for example from 0.1% to 30%) shortly after a rollout.
- Pods are `Running` and `Ready`; restarts are flat.
- Logs from new pods show exceptions on request handling, for example `500 Internal Server Error`, `NullPointerException`, `TypeError: 'NoneType' object is not subscriptable`.
- Alerts like `HighErrorRate` fire for the service.

## Checks

1. Correlate timing: `kubectl rollout history deployment/<name>` and the ReplicaSet creation time (`kubectl get rs -l app=<name>`) against the start of the error spike.
2. Compare revisions: `kubectl rollout history deployment/<name> --revision=<n>` for image tag and env var changes.
3. Read logs from a new pod: `kubectl logs <new-pod> --tail=200` and look for exceptions on request paths.
4. Check whether errors come only from new pods (per-pod or per-version metrics if available).
5. Rule out dependencies: if the same errors appear on old pods too, look at downstream services instead.

## Likely causes

- A code bug in the new version.
- An incompatible change with a dependency (API contract, schema migration).
- Changed configuration (feature flag, endpoint URL) shipped with the release.

## Fix

- Roll back: `kubectl rollout undo deployment/<name>` (or `--to-revision=<n>` for a specific known-good revision).
- Watch the error rate return to baseline over the next few minutes.
- File a ticket with the failing revision, the error rate graph and sample stack traces.

## Rollback / escalation

Rollback is always the first action for a release-correlated error spike. Escalate to the service owner if the error rate does not recover after rollback; that means the cause is elsewhere.
