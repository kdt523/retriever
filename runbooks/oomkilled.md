---
title: Container OOMKilled (exit code 137)
scope: A container is killed by the kernel out-of-memory killer because it exceeded its memory limit, or because the node ran out of memory.
tools: [kubectl describe pod, kubectl top pod, kubectl get pod -o yaml, memory_vs_limit metric]
cautions:
  - Raising the memory limit hides a leak; check the memory trend before and after.
  - Removing limits entirely lets one pod starve the whole node.
related: [node-pressure-eviction, crashloop-app-error, bad-release-5xx]
---

Exit code 137 means the process received SIGKILL. With reason OOMKilled the kernel killed it for using too much memory.

## Symptoms

- `kubectl describe pod` shows `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`.
- `kubectl get pods` shows `STATUS OOMKilled` right after the kill (for example `reporting-6d4f9c7b58-x8k2m 0/1 OOMKilled 1 (4s ago)`), then `CrashLoopBackOff` as restarts pile up, with `Back-off restarting failed container reporting in pod ...` events.
- Java apps may log `java.lang.OutOfMemoryError: Java heap space` just before; Python and Node often log nothing.
- Memory usage graphs climb to the limit line and drop to zero at each restart.

## Checks

1. Confirm the reason: `kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'`.
2. Compare usage to the limit: `kubectl top pod <pod> --containers` and the container's `resources.limits.memory`.
3. Check whether the limit changed recently with `kubectl rollout history deployment/<name> --revision=<n>`.
4. Check whether the whole node was under memory pressure: `kubectl describe node <node>` and look for `MemoryPressure True` or `System OOM encountered` events.
5. For JVM apps, check that `-Xmx` (or `MaxRAMPercentage`) is below the container limit, leaving room for non-heap memory.

## Likely causes

- A deploy lowered the memory limit below the app's normal working set.
- A memory leak or an unbounded cache in a new version.
- A traffic spike or large request payloads.
- JVM heap configured larger than the container limit.

## Fix

- If a recent rollout lowered the limit or introduced the leak, `kubectl rollout undo deployment/<name>`.
- Otherwise raise the limit to the observed peak plus about 25% headroom: `kubectl set resources deployment/<name> --limits=memory=512Mi --requests=memory=384Mi`.
- Cap runtimes to the container: set JVM `-XX:MaxRAMPercentage=75`, or bound caches in the app.

## Rollback / escalation

Roll back when the OOM started with a new revision. If memory grows steadily on the old revision too, escalate to the service owners as a probable leak, with the memory graph and the limit history attached.
