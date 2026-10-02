---
title: Service has no endpoints (selector or port mismatch)
scope: Pods are running, but a Service routes traffic nowhere because its selector matches no ready pods or its targetPort does not match the container port.
tools: [kubectl get svc, kubectl get endpointslices, kubectl get pods --show-labels, kubectl describe svc]
cautions:
  - Changing pod labels on a live deployment can orphan its ReplicaSets; change the Service selector instead when possible.
related: [readiness-probe-failing, dns-resolution-failure, ingress-502-503-504]
---

DNS resolves the Service name, but connections fail because there is nothing behind it.

## Symptoms

- Clients calling the Service get `Connection refused` immediately (kube-proxy rejects traffic to a Service with no endpoints), for example `URLError(ConnectionRefusedError(111, 'Connection refused'))` or `dial tcp 10.96.41.7:8000: connect: connection refused`.
- The ingress returns 503 with logs like `Service "shop/inventory" does not have any active Endpoint`.
- `kubectl describe svc inventory` shows `Selector: app=inventory` and an empty `Endpoints:` line; `kubectl get endpointslices -l kubernetes.io/service-name=inventory` lists no addresses.
- The backend pods are `Running` and `1/1 Ready`, but their labels (`kubectl get pods --show-labels`) do not match the selector, for example `app=inventory-v2`.

## Checks

1. Compare the Service selector with pod labels: `kubectl get svc inventory -o jsonpath='{.spec.selector}'` and `kubectl get pods --show-labels -n <ns>`. Every selector key must match exactly.
2. Check endpoints: `kubectl get endpointslices -l kubernetes.io/service-name=<svc> -o wide`.
3. If endpoints exist but connections fail, compare `targetPort` with the port the container actually listens on.
4. Check readiness: unready pods are excluded from endpoints.
5. Test from inside the cluster: `kubectl run tmp --rm -it --image=busybox:1.37 -- wget -qO- http://inventory:8000/healthz`.

## Likely causes

- A deploy changed pod labels (for example `app: inventory-v2`) and the Service still selects `app: inventory`.
- The Service lives in a different namespace than the pods.
- `targetPort` is a named port that the container does not define, or a wrong number.
- All pods are unready, so endpoints are empty.

## Fix

- Make the Service selector match the pod labels, or roll back the deploy that changed them: `kubectl rollout undo deployment/<name>`.
- Fix `targetPort` to the container's real port.
- If pods are unready, follow the readiness probe runbook.

## Rollback / escalation

Selector mistakes are easiest to fix by rolling back the change that introduced them. Escalate if endpoints are populated and correct but traffic still fails; that points at kube-proxy or the CNI.
