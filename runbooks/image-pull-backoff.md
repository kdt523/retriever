---
title: ImagePullBackOff and ErrImagePull
scope: The kubelet cannot pull the container image, so the container never starts.
tools: [kubectl describe pod, kubectl get events, kubectl get deployment -o yaml, kubectl rollout history]
cautions:
  - Do not paste registry passwords into commands that end up in shell history; create pull secrets from files.
  - Do not switch to a `latest` tag as a quick fix; it makes rollbacks unpredictable.
related: [bad-release-5xx, rollout-stuck]
---

The pod is scheduled, but the image pull fails. Kubernetes retries with back-off, which shows as ImagePullBackOff.

## Symptoms

- `kubectl get pods` shows `ErrImagePull`, then `ImagePullBackOff`; `READY 0/1`, zero restarts.
- Missing tag: `Failed to pull image "nginx:1.27.99": rpc error: code = NotFound desc = failed to pull and unpack image "docker.io/library/nginx:1.27.99": failed to resolve reference "docker.io/library/nginx:1.27.99": docker.io/library/nginx:1.27.99: not found`.
- Private image without credentials: `failed to resolve reference "ghcr.io/acme/payments:2.4.1": failed to authorize: failed to fetch anonymous token: unexpected status from GET request to https://ghcr.io/token?...: 403 Forbidden` (other registries say `401 Unauthorized` or `pull access denied, repository does not exist or may require authorization`).
- Rate limits: `429 Too Many Requests` / `toomanyrequests: You have reached your pull rate limit`.
- Then `Warning Failed ... Error: ErrImagePull`, `Warning Failed ... Error: ImagePullBackOff` and a `Normal BackOff` event `Back-off pulling image "..."`.

## Checks

1. Read the exact pull error: `kubectl describe pod <pod>` under `Events`.
2. Check the image reference for typos in the registry, repository or tag: `kubectl get deploy <name> -o jsonpath='{..image}'`.
3. Verify the tag exists in the registry (registry UI or `docker manifest inspect <image>` from a machine with access).
4. For private registries, check the pod has `imagePullSecrets` and that the secret exists in the same namespace: `kubectl get secret <name> -n <ns>`.
5. Check whether a rollout just changed the image: `kubectl rollout history deployment/<name>`.

## Likely causes

- A deploy referenced a tag that was never pushed, or has a typo.
- The image is private and the namespace lacks a valid pull secret, or the token expired.
- Registry rate limiting (common with anonymous Docker Hub pulls).
- The node cannot reach the registry (DNS, proxy, firewall).

## Fix

- Bad tag from a deploy: `kubectl rollout undo deployment/<name>`, then publish the correct image and redeploy.
- Missing credentials: create the secret from a Docker config file, `kubectl create secret generic regcred --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson=$HOME/.docker/config.json`, and add it under `imagePullSecrets`.
- Rate limits: authenticate pulls or mirror the image to your own registry.

## Rollback / escalation

Old pods keep serving during a failed rollout, so roll back calmly. Escalate to the platform team if pulls fail for every image on a node, which points at node networking or registry outages.
