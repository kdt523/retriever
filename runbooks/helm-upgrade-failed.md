---
title: Helm upgrade failed or release stuck
scope: A helm install or upgrade fails, times out with --wait, or leaves the release in a pending state that blocks further upgrades.
tools: [helm status, helm history, helm rollback, helm get values, kubectl get events, kubectl get pods]
cautions:
  - Deleting Helm's release Secrets (sh.helm.release.v1.*) to clear a pending state is a last resort; it loses release history.
  - helm uninstall deletes every resource of the release, including PVCs created by the chart unless they are kept by policy.
related: [rollout-stuck, image-pull-backoff, crashloop-app-error, admission-denied]
---

Helm only reports what the Kubernetes API and the workloads did. The real cause is usually in the pods or events of the release.

## Symptoms

- `Error: UPGRADE FAILED: context deadline exceeded` (with `--wait`), or `Error: UPGRADE FAILED: timed out waiting for the condition`.
- `Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress` after a previous run was interrupted.
- `helm history <release>` shows the latest revision as `failed`, `pending-upgrade` or `pending-install`.
- `Error: INSTALLATION FAILED: cannot re-use a name that is still in use`.
- Or a server-side rejection passed through, for example `Error: UPGRADE FAILED: ... is forbidden: ...` or a webhook denial.

## Checks

1. `helm status <release> -n <ns>` and `helm history <release> -n <ns>` to see the state of each revision.
2. Look at the workloads Helm waited on: `kubectl get pods -n <ns>` and `kubectl get events -n <ns> --sort-by=.lastTimestamp`; follow the matching runbook (image pull, crash loop, readiness, quota).
3. Compare values between revisions: `helm get values <release> --revision <n>`.
4. For `another operation is in progress`, confirm no helm process or CI job is still running for this release.

## Likely causes

- New pods never become Ready within the `--wait` timeout (bad image, crash, failing probe, quota).
- An interrupted helm process (CI job cancelled, laptop closed) left the release `pending-*`.
- Invalid values or a chart change rejected by the API server or an admission policy.

## Fix

- Roll back to the last good revision: `helm rollback <release> <revision> -n <ns> --wait`.
- For a stuck `pending-upgrade`, rolling back to the last `deployed` revision clears the lock in most cases.
- Fix the underlying pod problem, then upgrade again with the corrected values.

## Rollback / escalation

`helm rollback` is the standard first action. Escalate to the chart owner when rollbacks also fail, or before deleting release Secrets.
