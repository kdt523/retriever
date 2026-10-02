---
title: Pods not created because a ResourceQuota is exceeded
scope: A controller cannot create pods in a namespace because the namespace's ResourceQuota has no room left for the requested CPU, memory or object count.
tools: [kubectl describe resourcequota, kubectl describe rs, kubectl get events, kubectl get deploy]
cautions:
  - Raising a quota is a capacity decision for the namespace owner or platform team, not an incident shortcut.
  - Lowering requests or limits just to fit the quota can cause OOM kills and throttling later.
related: [rollout-stuck, pending-insufficient-resources]
---

The pods never exist, so there is nothing Pending to describe. The errors live on the ReplicaSet (or Job or StatefulSet) instead.

## Symptoms

- A Deployment stays below its desired replicas, for example `READY 2/3`, while no third pod appears at all.
- `Warning FailedCreate` events on the ReplicaSet from `replicaset-controller`: `Error creating: pods "etl-7c9b6d8f45-p2xnq" is forbidden: exceeded quota: team-quota, requested: limits.memory=1Gi,requests.memory=512Mi, used: limits.memory=3584Mi,requests.memory=2Gi, limited: limits.memory=4Gi,requests.memory=4Gi`.
- Repeats are folded into `(combined from similar events): Error creating: pods ... is forbidden: exceeded quota: ...`.
- Or `failed quota: team-quota: must specify limits.memory for: app` when the quota covers limits and the pod sets none.
- A rollout can stall the same way, because surge pods do not fit.

## Checks

1. Find the failing controller: `kubectl get events -n <ns> --field-selector reason=FailedCreate`.
2. Read the quota usage: `kubectl describe resourcequota -n <ns>`, comparing `Used` with `Hard` for each resource.
3. Compare with what one pod asks for: the `requested:` part of the message, or the pod template's `resources`.
4. Check whether a LimitRange injects default requests or limits (`kubectl describe limitrange -n <ns>`).
5. Check what else consumes the quota: completed Jobs, old ReplicaSets with pods, forgotten test deployments.

## Likely causes

- Scaling up or a new deployment pushes the namespace past its memory or CPU quota.
- A rollout with `maxSurge` needs temporary extra room that the quota does not have.
- Pods without limits in a namespace whose quota requires them.
- Leftover workloads still holding quota.

## Fix

- Free quota: scale down or delete unused workloads in the namespace.
- For rollouts, use `maxSurge: 0` and `maxUnavailable: 1` so updates fit inside the quota.
- Add the missing `resources.limits` to the pod template when the quota requires them.
- Ask the namespace owner to raise the quota if the workload genuinely needs more.

## Rollback / escalation

Roll back a scale-up or deploy that triggered the error. Escalate quota increases to the platform team with the `describe resourcequota` output.
