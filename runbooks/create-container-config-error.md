---
title: CreateContainerConfigError (missing ConfigMap or Secret)
scope: The kubelet cannot build the container's configuration because a referenced ConfigMap, Secret or key does not exist, so the container is never created.
tools: [kubectl describe pod, kubectl get configmap, kubectl get secret, kubectl get deployment -o yaml]
cautions:
  - Do not create placeholder Secrets with dummy values just to get pods running.
  - Do not print Secret data; check that keys exist with `kubectl describe secret`, which shows sizes only.
related: [crashloop-missing-config, volume-mount-failure]
---

This fails before the process starts, so there are no application logs to read.

## Symptoms

- `kubectl get pods` shows `STATUS CreateContainerConfigError`, `READY 0/1`, zero restarts.
- `kubectl describe pod` shows `Status: Pending`, `State: Waiting`, `Reason: CreateContainerConfigError`.
- `Warning Failed` events from the kubelet: `Error: configmap "checkout-config" not found`, or `Error: secret "stripe-api-key" not found`.
- Or `Error: couldn't find key CACHE_TTL in ConfigMap shop/cart-config` (namespace/name of the ConfigMap).
- `kubectl logs` returns `container "app" in pod "..." is waiting to start: CreateContainerConfigError`.

## Checks

1. Read the exact message: `kubectl describe pod <pod>` under `State: Waiting` and `Events`.
2. Check the object exists in the same namespace: `kubectl get configmap <name> -n <ns>` or `kubectl get secret <name> -n <ns>`.
3. Check the key exists: `kubectl describe configmap <name>` or `kubectl describe secret <name>` (lists keys without values).
4. Find every reference in the pod spec: `envFrom`, `env[].valueFrom.configMapKeyRef`, `env[].valueFrom.secretKeyRef`.
5. Check whether a deploy added the reference, or someone deleted or renamed the object.

## Likely causes

- A manifest references a ConfigMap or Secret that was never applied to this namespace.
- The object was created in a different namespace.
- A key was renamed in the ConfigMap but not in the deployment.
- A Secret managed by an external operator failed to sync.

## Fix

- Apply the missing ConfigMap or Secret from source control, in the right namespace.
- Fix the key name in the deployment, or mark optional references with `optional: true` when the value really is optional.
- If a rollout introduced the bad reference, `kubectl rollout undo deployment/<name>`.

## Rollback / escalation

Roll back when the reference is new. Escalate to whoever owns the secret source (vault or external-secrets operator) when a managed Secret is missing.
