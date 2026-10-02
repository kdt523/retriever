---
title: NetworkPolicy blocking pod-to-pod traffic
scope: Connections between pods fail (time out or are refused, depending on the CNI) because a NetworkPolicy, often a default-deny, does not allow the traffic.
tools: [kubectl get networkpolicy, kubectl describe networkpolicy, kubectl get pods --show-labels, kubectl exec]
cautions:
  - Deleting a NetworkPolicy to make traffic flow can expose sensitive services; add a narrow allow rule instead.
  - Policies are additive allow-lists; there is no "deny" rule to remove.
related: [dns-resolution-failure, service-no-endpoints, dependency-down]
---

How blocked traffic looks depends on the network plugin: Calico and Cilium drop packets by default, so calls time out; kube-router (the k3s default) rejects them, so calls are refused immediately.

## Symptoms

- Calls fail with `i/o timeout`, `context deadline exceeded` or `Connection timed out` (dropping CNIs), or with `Connection refused`, for example `URLError(ConnectionRefusedError(111, 'Connection refused'))` (rejecting CNIs such as kube-router on k3s).
- The key difference from a missing-endpoints problem: the target Service does have endpoints (`kubectl get endpointslices` lists the pod IPs) and the target pods are `Running` and Ready.
- Started right after a NetworkPolicy was applied or pod labels changed; `kubectl describe networkpolicy` shows `PodSelector: <none> (Allowing the specific traffic to all pods in this namespace)` and `(Selected pods are isolated for ingress connectivity)` for a default-deny.
- DNS lookups may also fail if egress to kube-dns is blocked.

## Checks

1. List policies in both namespaces: `kubectl get networkpolicy -n <src-ns>` and `-n <dst-ns>`.
2. For each policy selecting the destination pods (`spec.podSelector`), check whether an `ingress` rule allows the source pod's labels, namespace and port.
3. For policies selecting the source pods with `policyTypes: [Egress]`, check egress allows the destination and DNS on port 53.
4. Confirm labels: `kubectl get pods --show-labels` on both sides; namespace selectors use namespace labels such as `kubernetes.io/metadata.name`.
5. Test directly: `kubectl exec <src-pod> -- nc -zv -w 3 <svc> <port>`.

## Likely causes

- A new default-deny policy without matching allow rules.
- Pod labels changed so they no longer match an allow rule.
- Egress policy that forgot DNS.
- A port in the policy that differs from the container port (policies match the pod port, not the Service port).

## Fix

- Add a narrow allow rule for the needed source, destination and port.
- Restore the labels the policy expects, or roll back the deploy that changed them.
- Allow UDP/TCP 53 egress to kube-dns.

## Rollback / escalation

If a policy change caused the outage, revert that policy from source control. Escalate to the security or platform team before loosening policies in shared namespaces.
