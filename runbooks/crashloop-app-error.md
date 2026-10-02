---
title: CrashLoopBackOff from an application error
scope: A container starts, exits with a non-zero code from the application itself, and the kubelet restarts it with growing back-off delays.
tools: [kubectl get pods, kubectl describe pod, kubectl logs --previous, kubectl rollout history]
cautions:
  - Restarting the pod or the deployment does not fix a crash loop; it only resets the back-off timer.
  - Logs from the current attempt are often empty; always read the previous container's logs.
related: [crashloop-missing-config, oomkilled, container-start-error, bad-release-5xx]
---

The container process itself is exiting. Kubernetes is behaving correctly; the bug is in the application, its arguments or its environment.

## Symptoms

- `kubectl get pods` shows `0/1` with a rising `RESTARTS` count. The `STATUS` column alternates between `Error` (just exited) and `CrashLoopBackOff` (waiting out the back-off), for example `billing-7f9c6d5b84-qz2lp 0/1 Error 4 (2m16s ago)`.
- A `Warning BackOff` event: `Back-off restarting failed container billing in pod billing-7f9c6d5b84-qz2lp_shop(f1fda90c-...)`.
- `kubectl describe pod` shows `State: Terminated` or `State: Waiting, Reason: CrashLoopBackOff`, with `Last State: Terminated`, `Reason: Error`, `Exit Code: 1` (or 2, or another small non-zero code).
- The container logs end with the application's own error, for example `ValueError: unsupported tax region 'EU-X' in tax table v7`.

## Checks

1. Read the logs of the crashed attempt: `kubectl logs <pod> -c <container> --previous`. Look at the last 20 lines for a stack trace, `panic:`, `Traceback`, or `Error:`. If that returns `unable to retrieve container logs for containerd://...` after many restarts, run it without `--previous`; while the pod shows `Error`, the current container is the crashed one.
2. Check the exit code in `kubectl describe pod`. Code 1 or 2 means the app exited on purpose; 137 means it was killed (see the OOMKilled runbook); 128 with `StartError` means the process never started.
3. Compare with the previous revision: `kubectl rollout history deployment/<name>` and `kubectl rollout history deployment/<name> --revision=<n>` to see whether the image or command changed recently.
4. Confirm the command and args: `kubectl get deploy <name> -o jsonpath='{.spec.template.spec.containers[0].command}'`.

## Likely causes

- A new image version with a startup bug (unhandled exception, failed migration, wrong flag).
- Wrong `command` or `args` after a manifest change.
- The app cannot reach a dependency at startup and exits instead of retrying.
- File permissions or a read-only filesystem the app tries to write to.

## Fix

- If a recent rollout introduced the crash, roll back: `kubectl rollout undo deployment/<name>`.
- If the logs point at configuration, fix the ConfigMap or env var and roll out again.
- If the app exits when a dependency is down, fix the dependency first; consider making the app retry with backoff instead of exiting.

## Rollback / escalation

Roll back first when a deploy happened in the last hour, then debug the bad version outside production. Escalate to the owning team with the `--previous` log tail, the exit code and the revision diff if the crash is not explained by a recent change.
