---
title: Container fails to start (StartError, exec format error, permission denied)
scope: The container runtime cannot start the container's process at all, because the entrypoint is missing, not executable, or built for the wrong CPU architecture.
tools: [kubectl describe pod, kubectl get deployment -o yaml, docker manifest inspect, kubectl get nodes -L kubernetes.io/arch]
cautions:
  - Running the container as root to get past a permission error widens the attack surface; fix file permissions in the image instead.
related: [crashloop-app-error, image-pull-backoff]
---

The image pulled fine, but the process never ran. These errors come from the runtime, not the application.

## Symptoms

- `kubectl get pods` shows `STATUS RunContainerError` (or `CrashLoopBackOff`) with restarts; `kubectl describe pod` shows `State: Waiting, Reason: RunContainerError` and `Last State: Terminated, Reason: StartError, Exit Code: 128`.
- `Warning Failed` events: `Error: failed to create containerd task: failed to create shim task: OCI runtime create failed: runc create failed: unable to start container process: error during container init: exec: "/opt/service/entrypoint.sh": stat /opt/service/entrypoint.sh: no such file or directory`.
- Or the same with `exec: "/opt/service/entrypoint.sh": permission denied` (file not executable), or `exec: "server": executable file not found in $PATH`.
- Or the container log shows `exec /usr/local/bin/app: exec format error` (wrong CPU architecture) and exits with code 1 or 255.

## Checks

1. Read the full runtime error in `kubectl describe pod <pod>` under `Last State` and `Events`.
2. Check the entrypoint: `kubectl get deploy <name> -o jsonpath='{.spec.template.spec.containers[0].command} {.spec.template.spec.containers[0].args}'` versus the image's `ENTRYPOINT`/`CMD`.
3. For `exec format error`, compare architectures: `kubectl get nodes -L kubernetes.io/arch` and `docker manifest inspect <image>` (look for `amd64` versus `arm64`).
4. For `permission denied`, check the file mode in the image and whether the pod runs as a non-root user (`securityContext.runAsUser`).
5. Check whether a rollout changed the image or command.

## Likely causes

- An image built on an ARM laptop (arm64) deployed to amd64 nodes, without a multi-arch manifest.
- A shell script without the executable bit, or with Windows CRLF line endings in its shebang.
- A `command` override pointing at a path that does not exist in the image.
- A distroless image with a shell-form command (`sh -c ...`) but no shell.

## Fix

- Rebuild multi-arch images: `docker buildx build --platform linux/amd64,linux/arm64`.
- `chmod +x` scripts in the Dockerfile and convert line endings to LF.
- Fix or remove the `command` override.
- Roll back to the last working image: `kubectl rollout undo deployment/<name>`.

## Rollback / escalation

Roll back immediately; this failure is always caused by the image or the manifest. Escalate to the team owning the build pipeline for architecture problems.
