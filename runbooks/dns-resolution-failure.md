---
title: DNS resolution failures inside the cluster
scope: Pods cannot resolve Service names or external hosts, because of a wrong hostname, a CoreDNS problem, or DNS traffic being blocked.
tools: [kubectl exec nslookup, kubectl logs -n kube-system -l k8s-app=kube-dns, kubectl get svc -A, kubectl get networkpolicy]
cautions:
  - Restarting CoreDNS affects every workload in the cluster; check its logs first.
  - Hardcoding pod IPs to work around DNS breaks on the next restart.
related: [service-no-endpoints, networkpolicy-blocking-traffic, dependency-down]
---

First decide whether one name fails (usually a typo or wrong namespace) or every name fails (usually CoreDNS or a network policy).

## Symptoms

- App logs show a lookup failure whose wording depends on the runtime: Go `dial tcp: lookup payment on 10.96.0.10:53: no such host`; Node `getaddrinfo ENOTFOUND payment`; Python on glibc `[Errno -2] Name or service not known` or `[Errno -3] Temporary failure in name resolution`; Python on Alpine/musl `gaierror(-3, 'Try again')` even for a name that does not exist.
- Or timeouts when DNS itself is unreachable: `lookup payments.demo.svc.cluster.local: i/o timeout`, `server misbehaving`.
- `nslookup payment` from a debug pod prints `** server can't find payment.shop.svc.cluster.local: NXDOMAIN` for each search domain.
- Error rates jump right after a config change that set a new service URL, for example `PAYMENTS_URL=http://payment:8080`.

## Checks

1. Test from a pod in the same namespace: `kubectl run dnsutils --rm -it --image=registry.k8s.io/e2e-test-images/agnhost:2.39 -- nslookup orders`.
2. Check the name is right: `kubectl get svc -A | grep <name>`. Across namespaces use `<svc>.<namespace>.svc.cluster.local` or `<svc>.<namespace>`.
3. Check that CoreDNS pods are running and read their logs: `kubectl get pods -n kube-system -l k8s-app=kube-dns` and `kubectl logs -n kube-system -l k8s-app=kube-dns`.
4. Check `/etc/resolv.conf` in the failing pod: `kubectl exec <pod> -- cat /etc/resolv.conf`.
5. Check NetworkPolicies with egress rules; they must allow UDP and TCP 53 to kube-dns.

## Likely causes

- A typo in a service name or URL env var (for example `payment` instead of `payments`).
- Calling a Service in another namespace by its short name.
- CoreDNS crash-looping, overloaded, or misconfigured.
- An egress NetworkPolicy that blocks port 53.

## Fix

- Wrong name from a config change: fix the env var or `kubectl rollout undo deployment/<name>`.
- Use fully qualified names across namespaces.
- CoreDNS unhealthy: fix its config or resources, then restart it.
- Add an egress rule allowing DNS to the kube-dns pods.

## Rollback / escalation

Roll back app-side config changes immediately. Escalate to the platform team when CoreDNS itself is failing; it is cluster-wide.
