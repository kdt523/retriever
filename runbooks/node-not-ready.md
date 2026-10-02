---
title: Node NotReady
scope: A node stops reporting healthy status to the control plane; its pods become Unknown or are evicted and rescheduled.
tools: [kubectl get nodes, kubectl describe node, kubectl get pods -o wide, kubectl drain, kubectl cordon]
cautions:
  - Draining a node evicts every pod on it; check PodDisruptionBudgets and single-replica workloads first.
  - Force-deleting pods from an unreachable node can run two copies of a stateful pod.
related: [node-pressure-eviction, pod-stuck-terminating, volume-mount-failure]
---

Find out whether the kubelet is down, the node is under pressure, or the network between node and control plane is broken.

## Symptoms

- `kubectl get nodes` shows `STATUS NotReady` (or `NotReady,SchedulingDisabled`).
- `kubectl describe node` shows every condition (`Ready`, `MemoryPressure`, `DiskPressure`, `PIDPressure`) as `Unknown` with reason `NodeStatusUnknown` and message `Kubelet stopped posting node status.` when the kubelet is gone; `Ready False` when the kubelet runs but reports a problem.
- A `NodeNotReady` event: `Node worker-2 status is now: NodeNotReady`.
- The node gets taints `node.kubernetes.io/unreachable:NoExecute` and `node.kubernetes.io/unreachable:NoSchedule` (or `node.kubernetes.io/not-ready:*`).
- Pods on the node show `Unknown` or `Terminating`; replacements are created elsewhere after about five minutes.
- Kubelet logs may show `PLEG is not healthy` or container runtime errors.

## Checks

1. `kubectl describe node <node>` and read `Conditions` (Ready, MemoryPressure, DiskPressure, PIDPressure) and recent events.
2. List affected pods: `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`.
3. If you can reach the machine: `systemctl status kubelet`, `journalctl -u kubelet --since "15 min ago"`, and the container runtime status (`systemctl status containerd`).
4. Check disk and memory on the host: `df -h`, `free -m`.
5. Check whether several nodes failed at once, which points at the network or control plane rather than one machine.

## Likely causes

- Kubelet or container runtime crashed or hung.
- The node ran out of disk or memory.
- Network partition between node and API server.
- The VM was stopped, rebooted or preempted.

## Fix

- Cordon the node so nothing new lands there: `kubectl cordon <node>`.
- Restart the kubelet or container runtime if they are hung; free disk space if full.
- If the node does not recover, drain it (`kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`) and replace it.
- After repair, `kubectl uncordon <node>`.

## Rollback / escalation

Escalate to the platform or infrastructure team for hardware, VM or network failures. Escalate immediately when more than one node is NotReady.
