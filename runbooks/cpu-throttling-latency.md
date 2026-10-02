---
title: High latency from CPU throttling
scope: Requests get slow, with no errors or restarts, because containers hit their CPU limit and the kernel throttles them.
tools: [kubectl top pod, cpu_throttling metric, latency_p99 metric, kubectl get deployment -o yaml, kubectl rollout history]
cautions:
  - Removing CPU limits on a crowded node can starve neighbours; raise them deliberately.
  - Average CPU can look fine while short bursts are throttled; look at the throttled-periods ratio.
related: [liveness-probe-restarts, hpa-not-scaling, bad-release-5xx]
---

CPU limits are enforced in 100 ms periods. A container that bursts above its limit is paused for the rest of the period, which shows up as tail latency.

## Symptoms

- p99 latency rises sharply (for example from 80 ms to 2 s) while error rate and restarts stay flat.
- `container_cpu_cfs_throttled_periods_total / container_cpu_cfs_periods_total` above about 25% for the affected pods.
- `kubectl top pod` shows CPU usage pinned at or near the limit, for example `50m` with a `50m` limit.
- Liveness probes may start timing out, causing restarts.

## Checks

1. Check CPU usage against limits: `kubectl top pod -n <ns>` and `kubectl get deploy <name> -o jsonpath='{..resources}'`.
2. Query the throttling ratio per pod over the last 15 minutes.
3. Check whether a recent rollout lowered `limits.cpu`: `kubectl rollout history deployment/<name> --revision=<n>`.
4. Check whether traffic increased; if yes, compare with HPA status.
5. For multi-threaded runtimes, check thread pool sizes versus the CPU limit.

## Likely causes

- A deploy reduced the CPU limit (for example to `50m`).
- Traffic grew but replicas did not.
- Runtimes that size thread pools from the host's core count instead of the container limit.
- Expensive new code paths in a release.

## Fix

- If a rollout lowered the limit, `kubectl rollout undo deployment/<name>`.
- Raise the limit to cover peak bursts: `kubectl set resources deployment/<name> --limits=cpu=500m --requests=cpu=200m`.
- Scale out, or fix the HPA so it scales on CPU.
- Set runtime thread counts to match the CPU limit.

## Rollback / escalation

Rolling back a limit change is safe. Escalate to the service owner if the latency comes from new code rather than resources. Escalating with no action is acceptable when the cause is unclear.
