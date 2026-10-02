---
title: Init container stuck or failing (Init:0/1, Init:CrashLoopBackOff)
scope: A pod never starts its main containers because an init container is still waiting or keeps failing.
tools: [kubectl get pods, kubectl describe pod, kubectl logs -c <init-container>, kubectl get svc]
cautions:
  - Removing an init container that runs migrations or waits for a dependency can start the app against an unready backend.
related: [dependency-down, crashloop-app-error, volume-mount-failure]
---

Init containers run one at a time and must each exit 0 before the app starts. The status column shows which one is stuck.

## Symptoms

- `kubectl get pods` shows `STATUS Init:0/1` or `Init:1/2` for a long time.
- Or `Init:Error` / `Init:CrashLoopBackOff` with rising restarts and events like `Back-off restarting failed container schema-migrate in pod profiles-6c7d8f9b54-k3m2p_shop(...)`.
- `kubectl describe pod` shows the init container `State: Terminated, Reason: Error, Exit Code: 1` (or `State: Running` while it waits) and the app container `State: Waiting, Reason: PodInitializing`.
- `kubectl logs <pod>` fails with `container "app" in pod "..." is waiting to start: PodInitializing`.
- Init logs repeat `waiting for mysql...` or `nc: bad address 'db'`, or show a migration error.

## Checks

1. See which init container is running or failing: `kubectl describe pod <pod>` under `Init Containers` (state, exit code, restart count).
2. Read its logs: `kubectl logs <pod> -c <init-container-name>`; add `--previous` if it restarted.
3. If it waits for a service, check that service and its endpoints exist: `kubectl get svc,endpointslices -n <ns>`.
4. If it runs migrations, check the database is reachable and the migration did not fail partway.
5. Check that images and volumes used by the init container exist.

## Likely causes

- A wait-for loop waiting on a dependency that is down or misnamed.
- A failing database migration.
- Wrong command or missing tool in the init image (for example `nc` not present).
- Missing ConfigMap or Secret mounted by the init container.

## Fix

- Fix or restore the dependency the init container waits for.
- Fix the migration and redeploy; for a half-applied migration, involve the database owners.
- Correct the init container command or image; roll back if a deploy changed it: `kubectl rollout undo deployment/<name>`.
- Add a timeout to wait loops so failures surface as errors instead of endless waiting.

## Rollback / escalation

Roll back when the init container changed recently. Escalate to the database owners for migration failures; do not edit schema by hand during an incident.
