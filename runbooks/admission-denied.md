---
title: Request denied by an admission policy or webhook
scope: Creating or updating a resource fails because a ValidatingAdmissionPolicy, an admission webhook (OPA Gatekeeper, Kyverno and similar) or Pod Security admission rejects it.
tools: [kubectl apply --dry-run=server, kubectl get validatingadmissionpolicies, kubectl get validatingwebhookconfigurations, kubectl describe rs, kubectl get events]
cautions:
  - Do not delete or disable a policy or webhook to unblock a deploy; policies encode security and platform rules.
  - A webhook with failurePolicy Fail that is down blocks every matching request in the cluster.
related: [rbac-forbidden, rollout-stuck, resource-quota-exceeded]
---

The rejection message names the policy and its reason. For pods created by controllers, the message appears on the ReplicaSet, Job or StatefulSet instead of in your terminal.

## Symptoms

- `kubectl apply` or `kubectl create` fails with `deployments.apps "fanout-workers" is forbidden: ValidatingAdmissionPolicy 'replica-cap' with binding 'replica-cap' denied request: replica count above 8 is not allowed for batch workloads`.
- Webhooks: `admission webhook "validation.gatekeeper.sh" denied the request: [require-team-label] you must provide labels: {"team"}`, or `Internal error occurred: failed calling webhook "...": ... connect: connection refused` when the webhook service is down.
- Pod Security: `pods "web-..." is forbidden: violates PodSecurity "restricted:latest": allowPrivilegeEscalation != false ...`.
- A Deployment is updated but no new pods appear; the ReplicaSet has `FailedCreate` events with the denial text.

## Checks

1. Reproduce without changing anything: `kubectl apply -f manifest.yaml --dry-run=server` prints the full denial.
2. List policies and bindings: `kubectl get validatingadmissionpolicies,validatingadmissionpolicybindings`, and webhooks: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`.
3. Read the matching policy's rule or CEL expression and the binding's namespace selector.
4. For `failed calling webhook`, check the webhook's Service and pods (`kubectl get pods -n <webhook-namespace>`).
5. For Pod Security, check namespace labels: `kubectl get ns <ns> --show-labels` (`pod-security.kubernetes.io/enforce`).

## Likely causes

- The manifest genuinely violates a rule (replica limit, missing label, privileged container, latest tag).
- A new or tightened policy now rejects manifests that used to pass.
- The webhook backend is down and its failurePolicy is `Fail`.

## Fix

- Change the manifest to satisfy the rule the message names.
- If the policy is wrong, fix it through its owners and source control, then re-apply.
- Restore the webhook's pods when calls fail with connection errors.

## Rollback / escalation

Roll back the policy change if a new policy blocks valid production deploys. Escalate to the policy owners (platform or security); never bypass admission in production.
