---
title: Job failed (BackoffLimitExceeded) or CronJob not running
scope: A batch Job keeps failing until it hits its backoffLimit or activeDeadlineSeconds, or a CronJob stops creating Jobs on schedule.
tools: [kubectl get jobs, kubectl describe job, kubectl logs job/<name>, kubectl get cronjob, kubectl describe cronjob]
cautions:
  - Re-running a non-idempotent job (payments, emails, migrations) can repeat side effects.
  - Deleting a Job deletes its pods and their logs; save the logs first.
related: [crashloop-app-error, oomkilled, pending-insufficient-resources]
---

A Job retries failed pods with exponential back-off until it gives up. Its conditions say whether it ran out of retries or time.

## Symptoms

- `kubectl get jobs` shows `STATUS Failed` and `COMPLETIONS 0/1`; the Job has a `Warning BackoffLimitExceeded` event from `job-controller`: `Job has reached the specified backoff limit`.
- Or reason `DeadlineExceeded`: `Job was active longer than specified deadline`.
- With `restartPolicy: Never`, one pod per attempt (backoffLimit + 1 pods) in `Error` state, each with a non-zero exit code and the failure in its logs, for example `ERROR: upload to s3://reports-bucket/... failed: 403 AccessDenied`.
- CronJob events show `Cannot determine if job needs to be started: too many missed start times` or no new Jobs for hours.

## Checks

1. `kubectl describe job <name>` for conditions and pod failure events.
2. Read the logs of the failed pods: `kubectl logs job/<name>` or `kubectl logs <pod>` for each `Error` pod.
3. Check exit codes and reasons (137 with OOMKilled, 1 for application errors).
4. For CronJobs: `kubectl describe cronjob <name>`; check `suspend`, `schedule`, `concurrencyPolicy`, `startingDeadlineSeconds` and `lastScheduleTime`.
5. Check whether a previous Job is still running and `concurrencyPolicy: Forbid` blocks new ones.

## Likely causes

- Application error in the job (bad input, unreachable dependency, wrong credentials).
- Job pods OOMKilled or Pending.
- `activeDeadlineSeconds` shorter than the real run time.
- CronJob suspended, a long-running previous Job with `Forbid`, or the controller missed too many schedules.

## Fix

- Fix the cause from the pod logs, then create a fresh run: `kubectl create job --from=cronjob/<name> <name>-manual-1`.
- Raise memory limits or `activeDeadlineSeconds` if the job legitimately needs more.
- Unsuspend: `kubectl patch cronjob <name> -p '{"spec":{"suspend":false}}'`.
- Set `startingDeadlineSeconds` so missed schedules do not pile up.

## Rollback / escalation

Roll back the job's image if a new version started failing. Escalate to the data or service owner before re-running jobs with side effects.
