---
title: Downstream dependency unavailable (Redis, Postgres, other services)
scope: An application is healthy, but calls to a dependency (cache, database, queue, another service) fail, causing errors or crashes.
tools: [kubectl logs, kubectl get deploy, kubectl get endpointslices, upstream_errors metric, kubectl exec nc]
cautions:
  - Scaling the dependency to more replicas does not fix a single-writer database; check what it supports.
  - Restarting the client app does not help when the dependency is down; it can cause a reconnect storm.
related: [dns-resolution-failure, networkpolicy-blocking-traffic, crashloop-app-error, service-no-endpoints]
---

The error usually names the dependency and the failure type; read it before touching the app.

## Symptoms

- Logs show `redis.exceptions.ConnectionError: Error 111 connecting to redis-demo:6379. Connection refused.`
- Or `psycopg2.OperationalError: could not connect to server: Connection refused`, `FATAL: sorry, too many clients already`, or `FATAL: password authentication failed for user "app"`.
- Or `upstream connect error or disconnect/reset before headers`, `503` from a downstream HTTP service.
- Error rate rises across every service that uses the dependency at the same time.
- The dependency Deployment or StatefulSet shows `0/0` or `0/1` ready.

## Checks

1. Identify the dependency and error type from logs (refused, timeout, auth, too many connections).
2. Check the dependency's workload: `kubectl get deploy,statefulset -n <ns>`; look for zero replicas or crash-looping pods.
3. Check its Service endpoints: `kubectl get endpointslices -l kubernetes.io/service-name=<dep>`.
4. Test connectivity from the client pod: `kubectl exec <pod> -- nc -zv -w 3 <dep-service> <port>`.
5. Check recent changes: was the dependency scaled down, its password rotated, or its storage full?

## Likely causes

- The dependency was scaled to zero or its pod crashed.
- Connection limits exhausted (`max_connections` in Postgres) by a client leak or too many replicas.
- Credentials rotated without updating the client.
- Network policy or DNS change between client and dependency.

## Fix

- Restore the dependency: `kubectl scale deployment/<dep> --replicas=1` if it was scaled to zero, or fix its crash.
- Use connection pooling and cap per-pod pool sizes.
- Update the client secret after a rotation and roll the client.
- Fix network policy or DNS using their runbooks.

## Rollback / escalation

Escalate to the dependency's owners (database team, platform team) as soon as the dependency itself is down. Do not change client apps until the dependency is confirmed healthy.
