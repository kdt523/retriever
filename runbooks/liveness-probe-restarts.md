---
title: Liveness probe failures restarting containers
scope: The kubelet repeatedly kills and restarts healthy-but-slow containers because their liveness probe fails or times out.
tools: [kubectl describe pod, kubectl get events, kubectl logs --previous, kubectl top pod]
cautions:
  - A too-aggressive liveness probe can turn a short slowdown into a full outage by restarting every replica.
  - Liveness should not depend on downstream services.
related: [readiness-probe-failing, cpu-throttling-latency, crashloop-app-error]
---

The app may be fine; the probe gives up on it too early, and every restart makes the overload worse.

## Symptoms

- Restart counts climb while the logs show no crash or error before each restart.
- A `Warning Unhealthy` event `Liveness probe failed: Get "http://10.244.2.31:9000/healthz": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`, followed by a `Normal Killing` event `Container quote-api failed liveness probe, will be restarted`.
- `Last State: Terminated` with `Exit Code: 137` or `143` and reason `Error`, not OOMKilled.
- Restarts cluster around traffic peaks or long garbage-collection pauses.

## Checks

1. Confirm the restart reason in `kubectl describe pod <pod>`: probe failure events versus OOMKilled.
2. Inspect the probe: `timeoutSeconds`, `periodSeconds`, `failureThreshold`, `initialDelaySeconds`.
3. Check CPU throttling and usage; a container throttled at its CPU limit answers probes slowly.
4. Check whether `/healthz` does heavy work (database queries, calls to other services).
5. Check whether the probe changed in a recent rollout.

## Likely causes

- `timeoutSeconds: 1` on an endpoint that takes longer under load.
- No `startupProbe`, so liveness kills the app during slow startup.
- The health handler shares a thread pool with request handling and blocks under load.
- The liveness endpoint checks a dependency, so a dependency blip restarts every pod.

## Fix

- Loosen the probe: `timeoutSeconds: 3`, `failureThreshold: 3` or more.
- Add a `startupProbe` for slow-starting apps.
- Make `/healthz` cheap and local; move dependency checks to readiness.
- If CPU throttling causes the slowness, raise the CPU limit (see the CPU throttling runbook).
- If a rollout tightened the probe, `kubectl rollout undo deployment/<name>`.

## Rollback / escalation

Roll back probe changes first. Escalate to the app owners if the health endpoint genuinely hangs, which points at a deadlock or exhausted thread pool.
