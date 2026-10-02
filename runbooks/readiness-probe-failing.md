---
title: Readiness probe failing, pods not Ready
scope: Containers run without restarting, but the readiness probe fails, so the pods are removed from Service endpoints and receive no traffic.
tools: [kubectl describe pod, kubectl get endpointslices, kubectl get deployment -o yaml, kubectl port-forward]
cautions:
  - Removing the readiness probe sends traffic to pods that may not be able to serve it.
  - A failing readiness probe never restarts the container; only liveness does.
related: [liveness-probe-restarts, service-no-endpoints, rollout-stuck, dependency-down]
---

Readiness answers "can this pod take traffic right now?" When it fails everywhere, the Service has no endpoints and clients see errors.

## Symptoms

- `kubectl get pods` shows `READY 0/1` with `STATUS Running` and no restarts.
- `Warning Unhealthy` events: `Readiness probe failed: HTTP probe failed with statuscode: 404`, or `Readiness probe failed: Get "http://10.244.3.17:8080/readiness": dial tcp 10.244.3.17:8080: connect: connection refused` (nothing listening on that port yet).
- The app's access log shows the probe requests failing, with user agent `kube-probe/<version>`, for example `"GET /readiness HTTP/1.1" 404 19 "-" "kube-probe/1.35"`.
- The deployment reports `0/3` available replicas; a rollout hangs waiting for new pods to become ready.
- Clients get 503 errors because the Service has no ready endpoints.

## Checks

1. Read the probe failure message in `kubectl describe pod <pod>`; note path, port and status code.
2. Compare the probe definition with what the app serves: `kubectl get deploy <name> -o jsonpath='{.spec.template.spec.containers[0].readinessProbe}'`.
3. Test the endpoint yourself: `kubectl port-forward pod/<pod> 8000:8000` then `curl -i localhost:8000/ready`.
4. Check the endpoints: `kubectl get endpointslices -l kubernetes.io/service-name=<svc>`; ready endpoints should list the pod IPs.
5. Check whether a rollout changed the probe: `kubectl rollout history deployment/<name> --revision=<n>`.

## Likely causes

- The probe path or port is wrong (a typo such as `/readyness`, `/readyz` vs `/ready`, or a renamed endpoint).
- The app listens on a different port than the probe targets.
- The readiness endpoint checks a dependency that is down, so every pod reports unready.
- `initialDelaySeconds` or `timeoutSeconds` too short for a slow-starting app.

## Fix

- Probe changed in a rollout: `kubectl rollout undo deployment/<name>`.
- Correct the path or port in the manifest and roll out.
- For slow starts, add a `startupProbe` rather than a very long initial delay.
- If readiness fails because a dependency is down, fix the dependency (see the dependency runbook).

## Rollback / escalation

Rolling back is safe and quick. Escalate to the app owners when the readiness endpoint itself is failing on a known-good revision.
