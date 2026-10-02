---
title: Pod stuck in Terminating
scope: A deleted pod stays in Terminating for a long time because of finalizers, an unreachable node, or a container that ignores SIGTERM.
tools: [kubectl get pod -o yaml, kubectl describe pod, kubectl get node, kubectl delete --grace-period]
cautions:
  - Force deletion (--force --grace-period=0) only removes the API object; the container may still run on an unreachable node.
  - Removing finalizers skips cleanup that a controller was supposed to do.
related: [node-not-ready, volume-mount-failure]
---

Find out what is holding the pod: a finalizer, a dead node, or a slow shutdown.

## Symptoms

- `kubectl get pods` shows `STATUS Terminating` for many minutes, sometimes hours; `kubectl describe pod` shows `Status: Terminating (lasts 12m)` and the pod still has `metadata.deletionTimestamp` set, often with `metadata.finalizers` such as `example.com/backup-hook`.
- New pods of a StatefulSet cannot start because the old pod with the same name still exists.
- A RWO volume stays attached, causing `Multi-Attach error` for the replacement pod.
- Namespace deletion hangs because pods (or other objects) inside it are stuck.

## Checks

1. Check finalizers: `kubectl get pod <pod> -o jsonpath='{.metadata.finalizers}'`.
2. Check the node: `kubectl get pod <pod> -o wide` then `kubectl get node <node>`. If the node is NotReady, the kubelet cannot confirm deletion.
3. Check `terminationGracePeriodSeconds` and whether the app handles SIGTERM; read the logs during shutdown.
4. Check `preStop` hooks that may hang.

## Likely causes

- The node is NotReady or gone, so the kubelet never reports the containers stopped.
- A finalizer whose controller is not running or is failing.
- The app ignores SIGTERM and a long `terminationGracePeriodSeconds` delays the SIGKILL.
- A `preStop` hook that waits on something that never happens.

## Fix

- Node gone: confirm the machine is really down, then `kubectl delete pod <pod> --grace-period=0 --force`.
- Stuck finalizer: fix or restore its controller; as a last resort, `kubectl patch pod <pod> -p '{"metadata":{"finalizers":null}}'`.
- Handle SIGTERM in the app and keep the grace period realistic (30-60 s).
- Fix or time-box `preStop` hooks.

## Rollback / escalation

Escalate before force-deleting StatefulSet pods; two copies of the same database pod can corrupt data. Escalate to the owners of the finalizer's controller when finalizers are involved.
