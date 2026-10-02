---
title: LoadBalancer Service stuck with EXTERNAL-IP pending
scope: A Service of type LoadBalancer never gets an external address because no load balancer controller handles it, or the cloud provider fails to create one.
tools: [kubectl get svc, kubectl describe svc, kubectl get events, kubectl logs cloud-controller-manager]
cautions:
  - Every cloud load balancer costs money; check before creating more of them to work around the problem.
  - Switching to NodePort exposes ports on every node; review firewall rules first.
related: [service-no-endpoints, ingress-502-503-504]
---

Kubernetes does not create load balancers itself. A cloud controller manager or a bare-metal implementation (MetalLB, k3s ServiceLB) must act on the Service.

## Symptoms

- `kubectl get svc` shows `TYPE LoadBalancer` with `EXTERNAL-IP <pending>` for many minutes, for example `public-api LoadBalancer 10.96.120.33 <pending> 443:31544/TCP`. The NodePort (`31544`) is allocated and works; only the external address is missing.
- `kubectl describe svc` shows `Normal EnsuringLoadBalancer` events repeating, then `Warning SyncLoadBalancerFailed Error syncing load balancer: failed to ensure load balancer: ...`.
- On AWS a common message is `could not find any suitable subnets for creating the ELB`.
- On bare-metal clusters, or when `spec.loadBalancerClass` names a class no controller implements, `kubectl describe svc` shows `Events: <none>`: nothing is acting on the Service.

## Checks

1. `kubectl describe svc <name>` and read the events.
2. Find the controller: cloud controller manager pods in `kube-system`, or MetalLB / ServiceLB pods; read their logs.
3. On cloud, check provider prerequisites: subnet tags (AWS `kubernetes.io/role/elb`), quotas on load balancers and public IPs, IAM permissions of the controller.
4. For MetalLB, check that an `IPAddressPool` exists and has free addresses.
5. Check `spec.loadBalancerClass` and Service annotations for typos (internal vs external load balancer); a class nobody implements is silently ignored.

## Likely causes

- Bare-metal or local cluster without MetalLB or another load balancer implementation.
- Missing subnet tags or IAM permissions for the cloud controller.
- Load balancer or public IP quota exhausted.
- MetalLB address pool empty or misconfigured.

## Fix

- Install or configure a load balancer implementation (MetalLB with an address pool, or the cloud controller manager).
- Add the required subnet tags or IAM permissions; raise the quota.
- Expose the app through an existing Ingress controller instead of a new LoadBalancer per Service.

## Rollback / escalation

Revert recent Service annotation changes. Escalate to the platform or cloud team for controller, IAM, subnet and quota problems.
