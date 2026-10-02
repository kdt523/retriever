---
title: RBAC Forbidden errors from a ServiceAccount or user
scope: A workload, CI job or user gets HTTP 403 Forbidden from the Kubernetes API because no Role or ClusterRole binding grants the verb on the resource.
tools: [kubectl auth can-i, kubectl get rolebindings, kubectl describe role, kubectl get serviceaccount]
cautions:
  - Never fix a Forbidden error by binding cluster-admin to an application ServiceAccount.
  - Grant the narrowest verb, resource and namespace that the workload needs.
related: [admission-denied, crashloop-app-error]
---

The error message names the exact identity, verb, resource, API group and namespace. Everything needed for the fix is in that one line.

## Symptoms

- `Error from server (Forbidden): pods is forbidden: User "system:serviceaccount:staging:ci-runner" cannot list resource "pods" in API group "" in the namespace "staging"`.
- For other resources the group appears: `deployments.apps "checkout" is forbidden: User "system:serviceaccount:staging:ci-runner" cannot get resource "deployments" in API group "apps" in the namespace "staging"`.
- In-cluster clients log the same text with HTTP status 403, for example a controller crash-looping on `Forbidden` during startup, or a CI pipeline failing at `kubectl rollout restart`.
- `kubectl auth can-i list pods -n staging --as=system:serviceaccount:staging:ci-runner` prints `no`.

## Checks

1. Read the identity, verb, resource, group and namespace from the error message.
2. Confirm with `kubectl auth can-i <verb> <resource> -n <ns> --as=<identity>`.
3. List bindings for the identity: `kubectl get rolebindings,clusterrolebindings -A -o wide | grep <serviceaccount>`.
4. Inspect the bound role's rules: `kubectl describe role <name> -n <ns>` or `kubectl describe clusterrole <name>`.
5. Check the pod really runs as the expected account: `kubectl get pod <pod> -o jsonpath='{.spec.serviceAccountName}'`.

## Likely causes

- A new feature calls an API the ServiceAccount was never granted.
- The RoleBinding exists in a different namespace than the workload.
- The pod uses the `default` ServiceAccount because `serviceAccountName` is missing.
- A role was tightened or a binding deleted during a cleanup.

## Fix

- Create or extend a namespaced Role with only the needed verbs, then bind it: `kubectl create role pod-reader --verb=get,list,watch --resource=pods -n staging` and `kubectl create rolebinding ci-runner-pod-reader --role=pod-reader --serviceaccount=staging:ci-runner -n staging`.
- Set `serviceAccountName` on the pod template when the wrong account is used.
- Re-test with `kubectl auth can-i` before restarting the workload.

## Rollback / escalation

Restore a deleted binding from source control if it disappeared during a change. Escalate to the platform or security team for any ClusterRole change.
