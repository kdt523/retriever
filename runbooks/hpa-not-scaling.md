---
title: HorizontalPodAutoscaler not scaling
scope: Load rises but the HPA does not add replicas, because it cannot read metrics, pods lack resource requests, or it is already at maxReplicas.
tools: [kubectl get hpa, kubectl describe hpa, kubectl top pods, kubectl get apiservice, kubectl get deployment -o yaml]
cautions:
  - Raising maxReplicas without checking cluster capacity just creates Pending pods.
  - Manually scaling a deployment that an HPA controls is overwritten at the next HPA sync.
related: [cpu-throttling-latency, pending-insufficient-resources]
---

The HPA's own conditions explain why it is not acting. Start with `kubectl describe hpa`.

## Symptoms

- `kubectl get hpa` shows `TARGETS cpu: <unknown>/70%`, or replicas stuck at the minimum during a load spike.
- `describe hpa` shows condition `ScalingActive False FailedGetResourceMetric` and `Warning FailedGetResourceMetric` events: `failed to get cpu utilization: missing request for cpu in container checkout of Pod checkout-7b8d9c6f54-tx4wz`, plus `FailedComputeMetricsReplicas`: `invalid metrics (1 invalid out of 1), first error is: failed to get cpu resource metric value: ...`.
- Shortly after pods start, `no metrics returned from resource metrics API` or `did not receive metrics for targeted pods (pods might be unready)` is normal; it should clear within a minute or two.
- metrics-server missing: `unable to fetch metrics from resource metrics API: the server could not find the requested resource (get pods.metrics.k8s.io)`.
- Or condition `ScalingLimited True` with reason `TooManyReplicas`: the desired replica count is above `maxReplicas`.
- Latency and CPU throttling rise while replicas stay flat.

## Checks

1. `kubectl describe hpa <name>` and read `Conditions` and events.
2. Check that metrics-server is installed and its APIService is available: `kubectl get apiservice v1beta1.metrics.k8s.io` and `kubectl top pods`.
3. Check every container in the target pods has `resources.requests.cpu` (utilization is computed against requests).
4. Compare current replicas with `maxReplicas`.
5. Check the HPA's `scaleTargetRef` names the right Deployment.

## Likely causes

- metrics-server missing, crashing, or unable to reach kubelets.
- Pods (often a sidecar container) without CPU requests.
- `maxReplicas` reached.
- The HPA targets a Deployment name that changed.

## Fix

- Install or repair metrics-server.
- Add CPU requests to every container in the pod template.
- Raise `maxReplicas` after confirming cluster capacity.
- Correct `scaleTargetRef`.
- As a stopgap, raise `minReplicas` on the HPA rather than scaling the Deployment directly.

## Rollback / escalation

Roll back recent changes to requests or the HPA spec. Escalate to the platform team for metrics-server problems; they affect every autoscaler in the cluster.
