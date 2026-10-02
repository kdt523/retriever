---
title: CrashLoopBackOff from missing configuration
scope: The pod is created and the container starts, but the application exits at startup because a required environment variable, config file or secret value is missing or wrong.
tools: [kubectl logs --previous, kubectl describe deployment, kubectl get configmap, kubectl rollout history]
cautions:
  - Never print secret values into logs, tickets or chat; compare variable names only.
  - Editing a ConfigMap does not restart pods that read it as env vars; a rollout is needed.
related: [crashloop-app-error, create-container-config-error, bad-release-5xx]
---

Unlike CreateContainerConfigError, the container does start here; the application notices the missing setting and exits.

## Symptoms

- `STATUS CrashLoopBackOff` (or `Error` between restarts), rising restarts, `Last State: Terminated, Reason: Error, Exit Code: 1` within a second or two of start, and `Back-off restarting failed container ledger-api in pod ...` events.
- Previous logs end with a configuration error, for example `KeyError: 'POSTGRES_DSN'`, `panic: required env var REDIS_URL is not set`, `ValueError: invalid literal for int() with base 10: ''`, or `FileNotFoundError: /etc/app/config.yaml`.
- The problem started right after a deploy or a ConfigMap/Secret change.

## Checks

1. `kubectl logs <pod> --previous | tail -30` and find the variable or file the app complains about.
2. List the env var names the container gets: `kubectl describe deployment <name>` (look under `Environment:` and `Environment Variables from:`).
3. Diff env var names between revisions: `kubectl rollout history deployment/<name> --revision=<n>` for the current and previous revisions.
4. If the value comes from a ConfigMap, confirm the key exists: `kubectl get configmap <cm> -o jsonpath='{.data}'` and check the key name for typos.
5. If it is a mounted file, check the volume's `items` and `mountPath` match the path in the error.

## Likely causes

- A deploy removed or renamed an environment variable.
- A ConfigMap key was renamed while the deployment still references the old key.
- An empty value passed validation in Kubernetes but not in the app.
- A config file mounted at a different path than the app expects.

## Fix

- Restore the missing variable: `kubectl set env deployment/<name> POSTGRES_DSN=...` (prefer sourcing secrets with `valueFrom.secretKeyRef`).
- If the change came with a rollout, `kubectl rollout undo deployment/<name>` is the fastest safe fix.
- After fixing a ConfigMap used as env vars, run `kubectl rollout restart deployment/<name>` so pods pick it up.

## Rollback / escalation

Prefer rollback to the last revision that started cleanly. Escalate to the service owner if the required setting is undocumented or the correct value is unknown; do not guess production credentials.
