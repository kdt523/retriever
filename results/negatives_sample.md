# Hard-negative spot check

Mark any negative that actually answers the query.

## 1. [incident_snapshot] node-7b8c9d worker-node-2 Status: MemoryPressure | Event: EvictionThresholdMet attempting to reclaim memory | active_file stats triggering false positive evictions

**Positive** `k8s/concepts/scheduling-eviction/node-pressure-eviction#045`

> Node-pressure Eviction > Known issues > active_file memory is not considered as available memory  On Linux, the kernel tracks the number of bytes of file-backed memory on active least recently used (LRU) list as the `active_file` statistic. The kubelet treats `active_file` memory areas as not reclaimable. For workloads that make intensive use of block-backed local storage, including ephemeral local storage, kernel-level caches of file and block data means that many recently accessed cache pages 

**Negative** `k8s/concepts/storage/persistent-volumes#018`

> Persistent Volumes > Lifecycle of a volume and claim > PersistentVolume deletion protection finalizer  ```shell Name:            pvc-2f0bab97-85a8-4552-8044-eb8be45cf48d Labels:          <none> Annotations:     pv.kubernetes.io/provisioned-by: csi.vsphere.vmware.com Finalizers:      [kubernetes.io/pv-protection external-provisioner.volume.kubernetes.io/finalizer] StorageClass:    fast Status:          Bound Claim:           demo-app/nginx-logs Reclaim Policy:  Delete Access Modes:    RWO VolumeM

- [ ] negative is actually relevant

## 2. [how_to] how do I add mandatory node affinity to a custom scheduler configuration profile

**Positive** `k8s/concepts/scheduling-eviction/assign-pod-node#013`

> Assigning Pods to Nodes > Node affinity > Node affinity per scheduling profile  When configuring multiple scheduling profiles, you can associate a profile with a node affinity, which is useful if a profile only applies to a specific set of nodes. To do so, add an `addedAffinity` to the `args` field of the `NodeAffinity` plugin in the scheduler configuration. For example:  ```yaml apiVersion: kubescheduler.config.k8s.io/v1 kind: KubeSchedulerConfiguration  profiles:   - schedulerName: default-sch

**Negative** `k8s/concepts/storage/persistent-volumes#042`

> Persistent Volumes > Node Affinity  Note: For most volume types, you do not need to set this field. You need to explicitly set this for local volumes.  A PV can specify node affinity to define constraints that limit what nodes this volume can be accessed from. Pods that use a PV will only be scheduled to nodes that are selected by the node affinity. To specify node affinity, set `nodeAffinity` in the `.spec` of a PV. The PersistentVolume API reference has more details on this field.

- [ ] negative is actually relevant

## 3. [symptom] container env var not picking up the value from my configmap key reference

**Positive** `k8s/tasks/configure-pod-container/configure-pod-configmap#032`

> Configure a Pod to Use a ConfigMap > Define container environment variables using ConfigMap data > Define a container environment variable with data from a single ConfigMap  2. Assign the `special.how` value defined in the ConfigMap to the `SPECIAL_LEVEL_KEY`    environment variable in the Pod specification.  ```yaml apiVersion: v1 kind: Pod metadata:   name: dapi-test-pod spec:   containers:     - name: test-container       image: registry.k8s.io/busybox:1.27.2       command: [ "/bin/sh", "-c",

**Negative** `k8s/concepts/configuration/configmap#003`

> ConfigMaps > ConfigMaps and Pods  You can write a Pod `spec` that refers to a ConfigMap and configures the container(s) in that Pod based on the data in the ConfigMap. The Pod and the ConfigMap must be in the same namespace.  Note: The `spec` of a static Pod cannot refer to a ConfigMap or any other API objects.  Here's an example ConfigMap that has some keys with single values, and other keys where the value looks like a fragment of a configuration format.  ```yaml apiVersion: v1 kind: ConfigMap

- [ ] negative is actually relevant

## 4. [symptom] need to check pod events and container logs to find out why the app is failing to start

**Positive** `k8s/concepts/workloads/pods/pod-lifecycle#016`

> Pod Lifecycle > How Pods handle problems with containers  To investigate the root cause of a `CrashLoopBackOff` issue, a user can:  1. **Check logs**: Use `kubectl logs <name-of-pod>` to check the logs of the container.    This is often the most direct way to diagnose the issue causing the crashes. 1. **Inspect events**: Use `kubectl describe pod <name-of-pod>` to see events    for the Pod, which can provide hints about configuration or resource issues. 1. **Review configuration**: Ensure that t

**Negative** `runbook/create-container-config-error#000`

> CreateContainerConfigError (missing ConfigMap or Secret) > Symptoms  This fails before the process starts, so there are no application logs to read.  - `kubectl get pods` shows `STATUS CreateContainerConfigError`, `READY 0/1`, zero restarts. - `kubectl describe pod` shows `Status: Pending`, `State: Waiting`, `Reason: CreateContainerConfigError`. - `Warning Failed` events from the kubelet: `Error: configmap "checkout-config" not found`, or `Error: secret "stripe-api-key" not found`. - Or `Error: 

- [ ] negative is actually relevant

## 5. [how_to] how do I configure minGroupCount for gang scheduling in composite workload groups

**Positive** `k8s/concepts/workloads/workload-api#009`

> Workload API > CompositePodGroupTemplates > Structure and constraints  Each entry represents a template for a `CompositePodGroup` and can contain:  - **Child templates**: Nested `CompositePodGroupTemplates` (for intermediate non-leaf   groups) or `PodGroupTemplates` (for leaf groups containing Pods). - **Scheduling policy**: Specifies how child groups within this composite group are   scheduled:   - `basic`: Child groups are admitted and scheduled independently.   - `gang`: Enforces multi-level 

**Negative** `k8s/concepts/scheduling-eviction/gang-scheduling#008`

> Gang Scheduling > Hierarchical gang scheduling with CompositePodGroups > Placement feasibility  The `GangScheduling` plugin's `PlacementFeasible` method supports evaluation for both `PodGroups` and `CompositePodGroups`. It is invoked by the scheduling cycle before starting child evaluation and after evaluating each child group of a `CompositePodGroup`.  By taking into account the number of child groups that were successfully scheduled and the child groups that were not evaluated in the schedulin

- [ ] negative is actually relevant

## 6. [how_to] what conditions must be met for kubectl to assume in cluster authentication

**Positive** `k8s/reference/kubectl#006`

> Command line tool (kubectl) > In-cluster authentication and namespace overrides  Explicit use of `--namespace <value>` overrides this behavior.  **How kubectl handles ServiceAccount tokens**  If:  * there is Kubernetes service account token file mounted at   `/var/run/secrets/kubernetes.io/serviceaccount/token`, and * the `KUBERNETES_SERVICE_HOST` environment variable is set, and * the `KUBERNETES_SERVICE_PORT` environment variable is set, and * you don't explicitly specify a namespace on the ku

**Negative** `k8s/reference/kubectl/conventions#003`

> kubectl Usage Conventions > Best Practices > `kubectl proxy`  Caution: Browsing untrusted pod or service endpoints through `kubectl proxy` is dangerous, as the served content has implicit access to the Kubernetes API using the proxy's credentials. Use caution and avoid accessing untrusted endpoints while using privileged credentials.  To reduce risk:  * Avoid browsing to untrusted pods or services through `kubectl proxy`. * Use `--reject-methods='POST,PUT,PATCH,DELETE'` to restrict the proxy to 

- [ ] negative is actually relevant

## 7. [kubectl_output] Normal SuccessfulCreate 1s job-controller Created pod: indexed-job-ncslj

**Positive** `k8s/tasks/job/indexed-parallel-processing-static#010`

> Indexed Job for Parallel Processing with Static Work Assignment > Running the Job  ```   Normal  SuccessfulCreate  1s    job-controller  Created pod: indexed-job-ncslj ```  In this example, you run the Job with custom values for each index. You can inspect the output of one of the pods:  ```shell kubectl logs indexed-job-fdhq5 # Change this to match the name of a Pod from that Job ```  The output is similar to:  ``` xuq ```

**Negative** `k8s/tasks/job/indexed-parallel-processing-static#000`

> Indexed Job for Parallel Processing with Static Work Assignment  In this example, you will run a Kubernetes Job that uses multiple parallel worker processes. Each worker is a different container running in its own Pod. The Pods have an _index number_ that the control plane sets automatically, which allows each Pod to identify which part of the overall task to work on.  The pod index is available in the annotation `batch.kubernetes.io/job-completion-index` as a string representing its decimal val

- [ ] negative is actually relevant

## 8. [symptom] node authorization mode prevents patching csinode status unless the feature gate is enabled

**Positive** `k8s/concepts/storage/volume-health-monitoring#005`

> Volume Health Monitoring > Health reported on CSINode  Writing to `csinodes/status` is a new capability added by this feature: the Node authorization mode and the NodeRestriction admission plugin only allow a kubelet to patch the `CSINode` object that matches its own node, and only while the `CSIVolumeHealth` feature gate is enabled.

**Negative** `runbook/pending-taints-affinity#004`

> Pods Pending due to taints, node selectors or affinity > Fix  - Wrong selector or affinity from a deploy: `kubectl rollout undo deployment/<name>`. - Missing node labels: relabel the intended nodes, `kubectl label node <node> disktype=ssd`. - Maintenance taints: `kubectl uncordon <node>` when maintenance is done. - Switch hard anti-affinity to `preferredDuringSchedulingIgnoredDuringExecution`, or use topology spread constraints.  Rollback / escalation: Roll back manifest changes first. Escalate 

- [ ] negative is actually relevant

## 9. [error_string] Node name must be a valid DNS subdomain name

**Positive** `k8s/concepts/architecture/nodes#002`

> Nodes > Management  Otherwise, that node is ignored for any cluster activity until it becomes healthy.  Note: Kubernetes keeps the object for the invalid Node and continues checking to see whether it becomes healthy.  You, or a controller, must explicitly delete the Node object to stop that health checking.  The name of a Node object must be a valid DNS subdomain name.

**Negative** `k8s/concepts/services-networking/service#052`

> Service > Discovering services > Environment variables  If you only use DNS to discover the cluster IP for a Service, you don't need to worry about this ordering issue.  Kubernetes also supports and provides variables that are compatible with Docker Engine's "_legacy container links_" feature. You can read `makeLinkVariables` to see how this is implemented in Kubernetes.

- [ ] negative is actually relevant

## 10. [symptom] nodes are failing to pull custom base images from our private harbor registry

**Positive** `k8s/concepts/configuration/secret#038`

> Secrets > Working with Secrets > Container image pull Secrets  If you want to fetch container images from a private repository, you need a way for the kubelet on each node to authenticate to that repository. You can configure _image pull Secrets_ to make this possible. These Secrets are configured at the Pod level.

**Negative** `k8s/concepts/containers/images#018`

> Images > Multi-architecture images with image indexes  As well as providing binary images, a container registry can also serve a container image index. An image index can point to multiple image manifests for architecture-specific versions of a container. The idea is that you can have a name for an image (for example: `pause`, `example/mycontainer`, `kube-apiserver`) and allow different systems to fetch the right binary image for the machine architecture they are using.  The Kubernetes project t

- [ ] negative is actually relevant

## 11. [incident_snapshot] node/ip-10-0-1-50 clock skew detected | ttl-after-finished controller removed batch/v1 Job/analytics-query-9q8w7 prematurely

**Positive** `k8s/concepts/workloads/controllers/ttlafterfinished#004`

> Automatic Cleanup for Finished Jobs > Caveats > Time skew  Because the TTL-after-finished controller uses timestamps stored in the Kubernetes jobs to determine whether the TTL has expired or not, this feature is sensitive to time skew in your cluster, which may cause the control plane to clean up Job objects at the wrong time.  Clocks aren't always correct, but the difference should be very small. Please be aware of this risk when setting a non-zero TTL.

**Negative** `runbook/rollout-stuck#001`

> Deployment rollout stuck (ProgressDeadlineExceeded) > Symptoms  - ReplicaSet events may show `FailedCreate`: `Error creating: pods "etl-7c9b6d8f45-p2xnq" is forbidden: exceeded quota: team-quota, requested: limits.memory=1Gi,requests.memory=512Mi, used: limits.memory=3584Mi,requests.memory=2Gi, limited: limits.memory=4Gi,requests.memory=4Gi`.

- [ ] negative is actually relevant

## 12. [how_to] how do I figure out which burstable pods get evicted first under memory pressure

**Positive** `k8s/concepts/scheduling-eviction/node-pressure-eviction#029`

> Node-pressure Eviction > Node conditions > Pod selection for kubelet eviction  1. `Guaranteed` pods and `Burstable` pods where the usage is less than requests    are evicted last, based on their Priority.  Note: The kubelet does not use the pod's QoS class to determine the eviction order. You can use the QoS class to estimate the most likely pod eviction order when reclaiming resources like memory. QoS classification does not apply to EphemeralStorage requests, so the above scenario will not app

**Negative** `k8s/concepts/scheduling-eviction/node-pressure-eviction#016`

> Node-pressure Eviction > Eviction thresholds > Soft eviction thresholds  You can use the following flags to configure soft eviction thresholds:  - `eviction-soft`: A set of eviction thresholds like `memory.available<1.5Gi`   that can trigger pod eviction if held over the specified grace period. - `eviction-soft-grace-period`: A set of eviction grace periods like `memory.available=1m30s`   that define how long a soft eviction threshold must hold before triggering a Pod eviction. - `eviction-max-p

- [ ] negative is actually relevant

## 13. [symptom] we need to log blocked network security connections in the cluster but network policies lack this feature

**Positive** `k8s/concepts/services-networking/network-policies#032`

> Network Policies > What you can't do with network policies (at least, not yet)  - Forcing internal cluster traffic to go through a common gateway (this might be best served with   a service mesh or other proxy). - Anything TLS related (use a service mesh or ingress controller for this). - Node specific policies (you can use CIDR notation for these, but you cannot target nodes by   their Kubernetes identities specifically). - Targeting of services by name (you can, however, target pods or namespa

**Negative** `k8s/concepts/services-networking/network-policies#010`

> Network Policies > The NetworkPolicy resource  (Ingress rules) allows connections to all pods in the `default` namespace with the label    `role=db` on TCP port 6379 from:     * any pod in the `default` namespace with the label `role=frontend`    * any pod in a namespace with the label `project=myproject`    * IP addresses in the ranges `172.17.0.0`–`172.17.0.255` and `172.17.2.0`–`172.17.255.255`      (ie, all of `172.17.0.0/16` except `172.17.1.0/24`)  1. (Egress rules) allows connections from

- [ ] negative is actually relevant

## 14. [how_to] how to troubleshoot distroless container images in production using ephemeral containers

**Positive** `k8s/concepts/workloads/pods/ephemeral-containers#004`

> Ephemeral Containers > Uses for ephemeral containers  Ephemeral containers are useful for interactive troubleshooting when `kubectl exec` is insufficient because a container has crashed or a container image doesn't include debugging utilities.  In particular, distroless images enable you to deploy minimal container images that reduce attack surface and exposure to bugs and vulnerabilities. Since distroless images do not include a shell or any debugging utilities, it's difficult to troubleshoot d

**Negative** `k8s/concepts/containers/images#018`

> Images > Multi-architecture images with image indexes  As well as providing binary images, a container registry can also serve a container image index. An image index can point to multiple image manifests for architecture-specific versions of a container. The idea is that you can have a name for an image (for example: `pause`, `example/mycontainer`, `kube-apiserver`) and allow different systems to fetch the right binary image for the machine architecture they are using.  The Kubernetes project t

- [ ] negative is actually relevant

## 15. [how_to] how do i stop kubectl apply from overwriting manual replica count adjustments on a statefulset

**Positive** `k8s/concepts/workloads/controllers/statefulset#042`

> StatefulSets > PersistentVolumeClaim retention > Replicas  `.spec.replicas` is an optional field that specifies the number of desired Pods. It defaults to 1.  Should you manually scale a StatefulSet, via `kubectl scale statefulset statefulset --replicas=X`, and then you update that StatefulSet based on a manifest (for example: by running `kubectl apply -f statefulset.yaml`), then applying that manifest overwrites the manual scaling that you previously did.  If a HorizontalPodAutoscaler (or any s

**Negative** `k8s/tasks/run-application/scale-deployment#003`

> Horizontal Manual Scaling for a Deployment > Scaling down a Deployment  To reduce the number of Pods, set `--replicas` to a lower value:  ```shell kubectl scale deployment/nginx-deployment --replicas=2 ```  Kubernetes gracefully terminates the excess Pods, respecting each Pod's `terminationGracePeriodSeconds` setting.  Verify that the Deployment has two Pods:  ```shell kubectl get pods -l app=nginx ```  The output is similar to:  ``` NAME                                READY   STATUS    RESTARTS

- [ ] negative is actually relevant

## 16. [kubectl_output] namespace/cpu-example created

**Positive** `k8s/tasks/configure-pod-container/assign-cpu-resource#001`

> Assign CPU Resources to Containers and Pods > Specify a CPU request and a CPU limit  Create a namespace: Create a so that the resources you create in this exercise are isolated from the rest of your cluster.  ```shell kubectl create namespace cpu-example ```  To specify a CPU request for a container, include the `resources.requests.cpu` field in the container’s resource manifest. To specify a CPU limit, include `resources.limits.cpu`.  In this exercise, you create a Pod that has one container. T

**Negative** `k8s/tasks/configure-pod-container/assign-cpu-resource#005`

> Assign CPU Resources to Containers and Pods > CPU units  The CPU resource is measured in *CPU* units. One CPU, in Kubernetes, is equivalent to:  * 1 AWS vCPU * 1 GCP Core * 1 Azure vCore * 1 Hyperthread on a bare-metal Intel processor with Hyperthreading  Fractional values are allowed. A Container that requests 0.5 CPU is guaranteed half as much CPU as a Container that requests 1 CPU. You can use the suffix m to mean milli. For example 100m CPU, 100 milliCPU, and 0.1 CPU are all the same. Precis

- [ ] negative is actually relevant

## 17. [symptom] icmp ping packets are still getting through even though we have a deny all network policy applied

**Positive** `k8s/concepts/services-networking/network-policies#020`

> Network Policies > Network traffic filtering  NetworkPolicy is defined for layer 4 connections (TCP, UDP, and optionally SCTP). For all the other protocols, the behaviour may vary across network plugins.  Note: You must be using a CNI plugin that supports SCTP protocol NetworkPolicies.  When a `deny all` network policy is defined, it is only guaranteed to deny TCP, UDP and SCTP connections. For other protocols, such as ARP or ICMP, the behaviour is undefined. The same applies to allow rules: whe

**Negative** `k8s/concepts/services-networking/service-traffic-policy#000`

> Service Internal Traffic Policy  _Service Internal Traffic Policy_ enables internal traffic restrictions to only route internal traffic to endpoints within the node the traffic originated from. The "internal" traffic here refers to traffic originated from Pods in the current cluster. This can help to reduce costs and improve performance.

- [ ] negative is actually relevant

## 18. [how_to] what header fields are required in the yaml to make a gmsacredentialspec custom resource

**Positive** `k8s/tasks/configure-pod-container/configure-gmsa#003`

> Configure GMSA for Windows Pods and containers > Create GMSA credential spec resources  1. Use `Get-CredentialSpec` to show the path of the JSON file.  1. Convert the credspec file from JSON to YAML format and apply the necessary    header fields `apiVersion`, `kind`, `metadata` and `credspec` to make it a    GMSACredentialSpec custom resource that can be configured in Kubernetes.  The following YAML configuration describes a GMSA credential spec named `gmsa-WebApp1`:

**Negative** `k8s/reference/kubectl/quick-reference#011`

> kubectl Quick Reference > short alias to set/show context/namespace (only works for bash and bash-compatible shells, current context to be set before using kn to set namespace)  Kubernetes manifests can be defined in YAML or JSON. The file extension `.yaml`, `.yml`, and `.json` can be used.  ```bash kubectl apply -f ./my-manifest.yaml # create resource(s) kubectl apply -f ./my1.yaml -f ./my2.yaml # create from multiple files kubectl apply -f ./dir # create resource(s) in all manifest files in di

- [ ] negative is actually relevant

## 19. [symptom] pods and services not getting ipv6 addresses even though dual stack should be on

**Positive** `k8s/concepts/services-networking/dual-stack#000`

> IPv4/IPv6 dual-stack  IPv4/IPv6 dual-stack networking enables the allocation of both IPv4 and IPv6 addresses to Pods and Services.  IPv4/IPv6 dual-stack networking is enabled by default for your Kubernetes cluster starting in 1.21, allowing the simultaneous assignment of both IPv4 and IPv6 addresses.

**Negative** `runbook/networkpolicy-blocking-traffic#001`

> NetworkPolicy blocking pod-to-pod traffic > Symptoms  - Calls fail with `i/o timeout`, `context deadline exceeded` or `Connection timed out` (dropping CNIs), or with `Connection refused`, for example `URLError(ConnectionRefusedError(111, 'Connection refused'))` (rejecting CNIs such as kube-router on k3s). - The key difference from a missing-endpoints problem: the target Service does have endpoints (`kubectl get endpointslices` lists the pod IPs) and the target pods are `Running` and Ready. - Sta

- [ ] negative is actually relevant

## 20. [how_to] how do I completely remove the default accept header from startup probe requests

**Positive** `k8s/concepts/workloads/pods/probes#021`

> Liveness, Readiness, and Startup Probes > Probe mechanism details > HTTP probes  You can also remove these two headers by defining them with an empty value.  ```yaml livenessProbe:   httpGet:     httpHeaders:       - name: Accept         value: ""  startupProbe:   httpGet:     httpHeaders:       - name: User-Agent         value: "" ```  You can configure an HTTP probe to use HTTP/2 cleartext (h2c) by setting the `protocol` field to `HTTP2`. When `protocol` is set to `HTTP2`, the kubelet uses h2c

**Negative** `k8s/concepts/workloads/pods/probes#015`

> Liveness, Readiness, and Startup Probes > Configuration fields  `terminationGracePeriodSeconds` : configure a grace period for the kubelet to wait between triggering a shut down of the failed container, and then forcing the container runtime to stop that container. The default is to inherit the Pod-level value for `terminationGracePeriodSeconds` (30 seconds if not specified), and the minimum value is 1. See probe-level `terminationGracePeriodSeconds` for more detail.  Caution: Incorrect implemen

- [ ] negative is actually relevant

## 21. [symptom] any user who can patch a namespace is able to weaken the pod security admission labels and bypass restrictions

**Positive** `k8s/tasks/configure-pod-container/migrate-from-psp#005`

> Migrate from PodSecurityPolicy to the Built-In PodSecurity Admission Controller > 1. Review namespace permissions  Pod Security Admission is controlled by labels on namespaces. This means that anyone who can update (or patch or create) a namespace can also modify the Pod Security level for that namespace, which could be used to bypass a more restrictive policy. Before proceeding, ensure that only trusted, privileged users have these namespace permissions. It is not recommended to grant these pow

**Negative** `k8s/tasks/configure-pod-container/migrate-from-psp#020`

> Migrate from PodSecurityPolicy to the Built-In PodSecurity Admission Controller > 3. Update Namespaces > 3.b. Verify the Pod Security level  Once you have selected a Pod Security level for the namespace (or if you're trying several), it's a good idea to test it out first (you can skip this step if using the Privileged level). Pod Security includes several tools to help test and safely roll out profiles.  First, you can dry-run the policy, which will evaluate pods currently running in the namespa

- [ ] negative is actually relevant

## 22. [how_to] how do I share dynamic resource allocation claims across pods in a group

**Positive** `k8s/concepts/workloads/workload-api/workloadbuilder#006`

> Scheduling Building Block APIs and the workloadbuilder Library > Reusable building blocks > Resource claims  The resource claims block expresses which dynamic resource allocation claims are shared by every Pod in the group rather than allocated per Pod. Each entry names the claim within the group and points at either an existing ResourceClaim or a ResourceClaimTemplate from which one is generated. A group may declare at most four claims.  Pods consume the devices allocated to the group by declar

**Negative** `k8s/concepts/workloads/workload-api/topology-aware-scheduling#005`

> Topology-Aware Workload Scheduling > Multi-level topology-aware scheduling  Complex workloads might require co-location of their Pods at different levels of the cluster infrastructure. For example, an entire workload may need to run within a single availability zone, while different parts of that workload may require strict co-location within specific server racks.  Such multi-level co-location requirements can be expressed using the `CompositePodGroup` API and by specifying topology constraints

- [ ] negative is actually relevant

## 23. [how_to] how to change pod management policy back to default ordered ready in statefulset yaml

**Positive** `k8s/concepts/workloads/controllers/statefulset#020`

> StatefulSets > Pod Management Policies > OrderedReady Pod Management  Pod Management Policies: StatefulSet allows you to relax its ordering guarantees while preserving its uniqueness and identity guarantees via its `.spec.podManagementPolicy` field.  `OrderedReady` pod management is the default for StatefulSets. It implements the behavior described in Deployment and Scaling Guarantees.

**Negative** `k8s/tasks/run-application/configure-pdb#008`

> Specifying a Disruption Budget for your Application > Specifying a PodDisruptionBudget  For policy/v1beta1 an empty selector matches zero pods, while for policy/v1 an empty selector matches every pod in the namespace.  You can specify only one of `maxUnavailable` and `minAvailable` in a single `PodDisruptionBudget`. `maxUnavailable` can only be used to control the eviction of pods that all have the same associated controller managing them. In the examples below, "desired replicas" is the `scale`

- [ ] negative is actually relevant

## 24. [error_string] apiVersion: audit.k8s.io/v1

**Positive** `k8s/tasks/debug/debug-cluster/audit#006`

> Auditing > Audit policy  ```yaml   # Log all other resources in core and extensions at the Request level.   - level: Request     resources:     - group: "" # core API group     - group: "extensions" # Version of group should NOT be included.    # A catch-all rule to log all other requests at the Metadata level.   - level: Metadata     # Long-running requests like watches that fall under this rule will not     # generate an audit event in RequestReceived.     omitStages:       - "RequestReceived"

**Negative** `k8s/tasks/debug/debug-cluster/resource-usage-monitoring#002`

> Tools for Monitoring Resources > Resource metrics pipeline  These metrics are collected by the lightweight, short-term, in-memory metrics-server and  are exposed via the `metrics.k8s.io` API.  metrics-server discovers all nodes on the cluster and queries each node's kubelet for CPU and memory usage. The kubelet acts as a bridge between the Kubernetes master and the nodes, managing the pods and containers running on a machine. The kubelet translates each pod into its constituent containers and fe

- [ ] negative is actually relevant

## 25. [how_to] where are the lease objects stored that correspond to node heartbeats

**Positive** `k8s/concepts/architecture/leases#001`

> Leases > Node heartbeats  Kubernetes uses the Lease API to communicate kubelet node heartbeats to the Kubernetes API server. For every `Node` , there is a `Lease` object with a matching name in the `kube-node-lease` namespace. Under the hood, every kubelet heartbeat is an **update** request to this `Lease` object, updating the `spec.renewTime` field for the Lease. The Kubernetes control plane uses the time stamp of this field to determine the availability of this `Node`.  See Node Lease objects 

**Negative** `k8s/concepts/storage/storage-classes#006`

> Storage Classes > Provisioner  Each StorageClass has a provisioner that determines what volume plugin is used for provisioning PVs. This field must be specified.  | Volume Plugin | Internal Provisioner | Config Example | | :------------------- | :------------------: | :-----------------------------------: | | AzureFile | ✓ | Azure File | | CephFS | - | - | | FC | - | - | | FlexVolume | - | - | | iSCSI | - | - | | Local | - | Local | | NFS | - | NFS | | PortworxVolume | ✓ | Portworx Volume | | RB

- [ ] negative is actually relevant

## 26. [symptom] generic ephemeral volumes need snapshotting and resizing capabilities like normal volumes

**Positive** `k8s/concepts/storage/ephemeral-volumes#006`

> Ephemeral Volumes > Generic ephemeral volumes  Generic ephemeral volumes are similar to `emptyDir` volumes in the sense that they provide a per-pod directory for scratch data that is usually empty after provisioning. But they may also have additional features:  - Storage can be local or network-attached. - Volumes can have a fixed size that Pods are not able to exceed. - Volumes may have some initial data, depending on the driver and   parameters. - Typical operations on volumes are supported as

**Negative** `k8s/concepts/storage/ephemeral-storage#001`

> Local ephemeral storage  * An admin sets the resource quota for ephemeral-storage in a namespace. * A user needs to specify limits for the ephemeral-storage resource in the Pod spec.  If the user doesn't specify the ephemeral-storage resource limit in the Pod spec, the resource quota is not enforced on ephemeral-storage.  Kubernetes lets you track, reserve and limit the amount of ephemeral local storage a Pod can consume.

- [ ] negative is actually relevant

## 27. [kubectl_output] behavior: scaleDown: selectPolicy: Disabled

**Positive** `k8s/concepts/workloads/autoscaling/horizontal-pod-autoscale#037`

> Horizontal Pod Autoscaling > Configurable scaling behavior > Example: disable scale down  The `selectPolicy` value of `Disabled` turns off scaling the given direction. So to prevent downscaling the following policy would be used:  ```yaml behavior:   scaleDown:     selectPolicy: Disabled ```

**Negative** `k8s/tasks/run-application/horizontal-pod-autoscale-walkthrough#023`

> HorizontalPodAutoscaler Walkthrough > Appendix: Horizontal Pod Autoscaler Status Conditions  For this HorizontalPodAutoscaler, you can see several conditions in a healthy state. The first, `AbleToScale`, indicates whether or not the HPA is able to fetch and update scales, as well as whether or not any backoff-related conditions would prevent scaling. The second, `ScalingActive`, indicates whether or not the HPA is enabled (i.e. the replica count of the target is not zero) and is able to calculat

- [ ] negative is actually relevant

## 28. [how_to] how do i set up a pod disruption budget to limit concurrent evictions on my app

**Positive** `k8s/tasks/run-application/configure-pdb#000`

> Specifying a Disruption Budget for your Application > Protecting an Application with a PodDisruptionBudget  This page shows how to limit the number of concurrent disruptions that your application experiences, allowing for higher availability while permitting the cluster administrator to manage the clusters nodes.  1. Identify what application you want to protect with a PodDisruptionBudget (PDB). 1. Think about how your application reacts to disruptions. 1. Create a PDB definition as a YAML file.

**Negative** `k8s/tasks/run-application/configure-pdb#006`

> Specifying a Disruption Budget for your Application > Think about how your application reacts to disruptions > Rounding logic when specifying percentages  For instance, if   you set `minAvailable` to `"50%"`, then at least 50% of the Pods remain available   during a disruption.  When you specify the value as a percentage, it may not map to an exact number of Pods. For example, if you have 7 Pods and you set `minAvailable` to `"50%"`, it's not immediately obvious whether that means 3 Pods or 4 Po

- [ ] negative is actually relevant

## 29. [how_to] how do I use telepresence to develop services locally that need to access secrets in a remote cluster

**Positive** `k8s/tasks/debug/debug-cluster/local-debugging#000`

> Developing and debugging services locally using telepresence  Kubernetes applications usually consist of multiple, separate services, each running in its own container. Developing and debugging these services on a remote Kubernetes cluster can be cumbersome, requiring you to get a shell on a running container in order to run debugging tools.  `telepresence` is a tool to ease the process of developing and debugging services locally while proxying the service to a remote Kubernetes cluster. Using 

**Negative** `k8s/concepts/configuration/secret#037`

> Secrets > Working with Secrets > Using Secrets as environment variables  To use a Secret in an environment variable in a Pod:  1. For each container in your Pod specification, add an environment variable    for each Secret key that you want to use to the    `env[].valueFrom.secretKeyRef` field. 1. Modify your image and/or command line so that the program looks for values    in the specified environment variables.  For instructions, refer to Define container environment variables using Secret dat

- [ ] negative is actually relevant

## 30. [how_to] how to perform a safe pod deletion without setting grace period to zero

**Positive** `k8s/tasks/run-application/force-delete-stateful-set-pod#002`

> Force Delete StatefulSet Pods > Delete Pods  You can perform a graceful pod deletion with the following command:  ```shell kubectl delete pods <pod> ```  For the above to lead to graceful termination, the Pod **must not** specify a `pod.Spec.TerminationGracePeriodSeconds` of 0. The practice of setting a `pod.Spec.TerminationGracePeriodSeconds` of 0 seconds is unsafe and strongly discouraged for StatefulSet Pods. Graceful deletion is safe and will ensure that the Pod shuts down gracefully before 

**Negative** `k8s/tasks/job/pod-failure-policy#012`

> Handling retriable and non-retriable pod failures with Pod failure policy > Usage scenarios > Using Pod Failure Policy to avoid unnecessary Pod retries per index  To avoid unnecessary Pod restarts per index, you can use the _Pod failure policy_ and _backoff limit per index_ features. This section of the page shows how to use these features together.  1. Examine the following manifest:  1. Apply the manifest:     ```sh    kubectl create -f https://k8s.io/examples/controllers/job-backoff-limit-per

- [ ] negative is actually relevant

## 31. [symptom] daemonset template spec missing apiVersion validation error during apply

**Positive** `k8s/concepts/workloads/controllers/daemonset#005`

> DaemonSet > Writing a DaemonSet Spec > Pod Template  The `.spec.template` is one of the required fields in `.spec`.  The `.spec.template` is a pod template. It has exactly the same schema as a Pod, except it is nested and does not have an `apiVersion` or `kind`.  In addition to required fields for a Pod, a Pod template in a DaemonSet has to specify appropriate labels (see pod selector).  A Pod Template in a DaemonSet must have a `RestartPolicy`  equal to `Always`, or be unspecified, which defaul

**Negative** `k8s/concepts/containers/images#024`

> Images > Using a private registry > Interpretation of config.json  The amount of matched subdomains has to be equal to the amount of glob patterns (`*.`), for example:  - `*.kubernetes.io` will *not* match `kubernetes.io`, but will match     `abc.kubernetes.io`. - `*.*.kubernetes.io` will *not* match `abc.kubernetes.io`, but will match     `abc.def.kubernetes.io`. - `prefix.*.io` will match `prefix.kubernetes.io`. - `*-good.kubernetes.io` will match `prefix-good.kubernetes.io`.  This means that 

- [ ] negative is actually relevant

## 32. [how_to] how do I create a volume attributes class object with immutable parameters

**Positive** `k8s/concepts/storage/volume-attributes-classes#001`

> Volume Attributes Classes > The VolumeAttributesClass API  Each VolumeAttributesClass contains the `driverName` and `parameters`, which are used when a PersistentVolume (PV) belonging to the class needs to be dynamically provisioned or modified.  The name of a VolumeAttributesClass object is significant and is how users can request a particular class. Administrators set the name and other parameters of a class when first creating VolumeAttributesClass objects. While the name of a VolumeAttribute

**Negative** `k8s/tasks/inject-data-application/distribute-credentials-secure#009`

> Distribute Credentials Securely Using Secrets > Create a Pod that has access to the secret data through a Volume > Set POSIX permissions for Secret keys  The Secret is mounted on `/etc/foo`; all the files created by the secret volume mount have permission `0400`.  Note: If you're defining a Pod or a Pod template using JSON, beware that the JSON specification doesn't support octal literals for numbers because JSON considers `0400` to be the _decimal_ value `400`. In JSON, use decimal values for t

- [ ] negative is actually relevant

## 33. [symptom] vpa tries to resize containers without restarting them but falls back to eviction if it fails

**Positive** `k8s/concepts/workloads/autoscaling/vertical-pod-autoscale#011`

> Vertical Pod Autoscaling > Update modes > InPlaceOrRecreate  In `InPlaceOrRecreate` mode, VPA attempts to update Pod resource requests and limits without restarting the Pod when possible. However, if in-place updates cannot be performed for a particular resource change, VPA falls back to evicting the Pod (similar to `Recreate` mode) and allowing the workload controller to create a replacement Pod with updated resources.  In this mode, the updater applies recommendations in-place using the Resize

**Negative** `k8s/concepts/workloads/pods/disruptions#007`

> Disruptions > Pod disruption budgets  Instead, the handling of failures during application updates is configured in the spec for the specific workload resource.  It is recommended to set `AlwaysAllow` Unhealthy Pod Eviction Policy to your PodDisruptionBudgets to support eviction of misbehaving applications during a node drain. The default behavior is to wait for the application pods to become healthy before the drain can proceed.  When a pod is evicted using the eviction API, it is gracefully te

- [ ] negative is actually relevant

## 34. [how_to] how should I reference storage classes in portable pvc templates so they use the cluster default

**Positive** `k8s/concepts/storage/persistent-volumes#071`

> Persistent Volumes > Writing Portable Configuration  - Include PersistentVolumeClaim objects in your bundle of config (alongside   Deployments, ConfigMaps, etc). - Do not include PersistentVolume objects in the config, since the user instantiating   the config may not have permission to create PersistentVolumes. - Give the user the option of providing a storage class name when instantiating   the template.   - If the user provides a storage class name, put that value into the     `persistentVolu

**Negative** `k8s/concepts/storage/persistent-volumes#004`

> Persistent Volumes > Provisioning > Dynamic  When none of the static PVs the administrator created match a user's PersistentVolumeClaim, the cluster may try to dynamically provision a volume specially for the PVC. This provisioning is based on StorageClasses: the PVC must request a storage class and the administrator must have created and configured that class for dynamic provisioning to occur. Claims that request the class `""` effectively disable dynamic provisioning for themselves.  To enable

- [ ] negative is actually relevant

## 35. [how_to] how to correctly configure the spec selector for a statefulset template

**Positive** `k8s/concepts/workloads/controllers/statefulset#005`

> StatefulSets > Components > Pod Selector  You must set the `.spec.selector` field of a StatefulSet to match the labels of its `.spec.template.metadata.labels`. Failing to specify a matching Pod Selector will result in a validation error during StatefulSet creation.

**Negative** `k8s/concepts/workloads/controllers/statefulset#020`

> StatefulSets > Pod Management Policies > OrderedReady Pod Management  Pod Management Policies: StatefulSet allows you to relax its ordering guarantees while preserving its uniqueness and identity guarantees via its `.spec.podManagementPolicy` field.  `OrderedReady` pod management is the default for StatefulSets. It implements the behavior described in Deployment and Scaling Guarantees.

- [ ] negative is actually relevant

## 36. [kubectl_output] Events: Type Reason Age From Message Warning Unhealthy 2m (x3 over 4m) kubelet Liveness probe failed: HTTP status code 500

**Positive** `k8s/tasks/configure-pod-container/configure-liveness-readiness-startup-probes#011`

> Configure Liveness, Readiness and Startup Probes > Define a liveness HTTP request  To try the HTTP liveness check, create a Pod:  ```shell kubectl apply -f https://k8s.io/examples/pods/probe/http-liveness.yaml ```  After 10 seconds, view Pod events to verify that liveness probes have failed and the container has been restarted:  ```shell kubectl describe pod liveness-http ```  In releases after v1.13, local HTTP proxy environment variable settings do not affect the HTTP liveness probe.

**Negative** `k8s/tasks/configure-pod-container/configure-liveness-readiness-startup-probes#022`

> Configure Liveness, Readiness and Startup Probes > Define a gRPC liveness probe > Use TLS with gRPC probes  By default the `kubelet` connects to gRPC health endpoints over plaintext. If your application serves gRPC only over TLS, you can add the `mode` field to the `grpc` field in the probe specification and specify a value of `TLS`. This requires the `GRPCContainerProbeTLS` feature gate to be enabled on both the `kube-apiserver` and the `kubelet`.  ```yaml apiVersion: v1 kind: Pod metadata:   n

- [ ] negative is actually relevant

## 37. [symptom] kill hup 1 command is signaling the pause container instead of my application process

**Positive** `k8s/tasks/configure-pod-container/share-process-namespace#004`

> Share Process Namespace between Containers in a Pod > Understanding process namespace sharing  Pods share many resources so it makes sense they would also share a process namespace. Some containers may expect to be isolated from others, though, so it's important to understand the differences:  1. **The container process no longer has PID 1.** Some containers refuse    to start without PID 1 (for example, containers using `systemd`) or run    commands like `kill -HUP 1` to signal the container pr

**Negative** `runbook/job-backoff-limit#002`

> Job failed (BackoffLimitExceeded) or CronJob not running > Likely causes  - Application error in the job (bad input, unreachable dependency, wrong credentials). - Job pods OOMKilled or Pending. - `activeDeadlineSeconds` shorter than the real run time. - CronJob suspended, a long-running previous Job with `Forbid`, or the controller missed too many schedules.

- [ ] negative is actually relevant

## 38. [error_string] Multi-Category Security (MCS)

**Positive** `k8s/tasks/configure-pod-container/security-context#045`

> Configure a Security Context for a Pod or Container > Discussion  The security context for a Pod applies to the Pod's Containers and also to the Pod's Volumes when applicable. Specifically `fsGroup` and `seLinuxOptions` are applied to Volumes as follows:  * `fsGroup`: Volumes that support ownership management are modified to be owned   and writable by the GID specified in `fsGroup`. See the   Ownership Management design document   for more details.  * `seLinuxOptions`: Volumes that support SELin

**Negative** `k8s/tasks/configure-pod-container/security-context#010`

> Configure a Security Context for a Pod or Container > Configure fine-grained SupplementalGroups control for a Pod  This feature can be enabled by setting the `SupplementalGroupsPolicy` feature gate for kubelet and kube-apiserver, and setting the `.spec.securityContext.supplementalGroupsPolicy` field for a pod.  The `supplementalGroupsPolicy` field defines the policy for calculating the supplementary groups for the container processes in a pod. There are two valid values for this field:  * `Merge

- [ ] negative is actually relevant

## 39. [how_to] how to pass secret keys as environment variables to containers

**Positive** `k8s/concepts/configuration/secret#037`

> Secrets > Working with Secrets > Using Secrets as environment variables  To use a Secret in an environment variable in a Pod:  1. For each container in your Pod specification, add an environment variable    for each Secret key that you want to use to the    `env[].valueFrom.secretKeyRef` field. 1. Modify your image and/or command line so that the program looks for values    in the specified environment variables.  For instructions, refer to Define container environment variables using Secret dat

**Negative** `k8s/tasks/inject-data-application/define-environment-variable-container#001`

> Define Environment Variables for a Container > Define an environment variable for a container  You can read more about ConfigMap and Secret.  This page explains how to use `env`.  In this exercise, you create a Pod that runs one container. The configuration file for the Pod defines an environment variable with name `DEMO_GREETING` and value `"Hello from the environment"`. Here is the configuration manifest for the Pod:  ```yaml apiVersion: v1 kind: Pod metadata:   name: envar-demo   labels:     

- [ ] negative is actually relevant

## 40. [incident_snapshot] cart-service-xgwghb6l-zh2bz 1/1 Running 0 (4h ago) | cni plugin dropped packet from payments-worker to cart-service due to networkpolicy

**Positive** `runbook/networkpolicy-blocking-traffic#000`

> NetworkPolicy blocking pod-to-pod traffic  How blocked traffic looks depends on the network plugin: Calico and Cilium drop packets by default, so calls time out; kube-router (the k3s default) rejects them, so calls are refused immediately.

**Negative** `runbook/loadbalancer-pending#003`

> LoadBalancer Service stuck with EXTERNAL-IP pending > Fix  - Install or configure a load balancer implementation (MetalLB with an address pool, or the cloud controller manager). - Add the required subnet tags or IAM permissions; raise the quota. - Expose the app through an existing Ingress controller instead of a new LoadBalancer per Service.  Rollback / escalation: Revert recent Service annotation changes. Escalate to the platform or cloud team for controller, IAM, subnet and quota problems.

- [ ] negative is actually relevant

## 41. [how_to] how do I write a ResourceClaimTemplate yaml requesting 64Gi memory device class

**Positive** `k8s/tasks/configure-pod-container/assign-resources/allocate-devices-dra#004`

> Allocate Devices to Workloads with DRA > Claim resources  To create a workload that claims resources, select one of the following options:  Review the following example manifest:  ```yaml apiVersion: resource.k8s.io/v1 kind: ResourceClaimTemplate metadata:   name: example-resource-claim-template spec:   spec:     devices:       requests:       - name: gpu-claim         exactly:           deviceClassName: example-device-class           selectors:             - cel:                 expression: |- 

**Negative** `k8s/tasks/run-application/run-single-instance-stateful-application#002`

> Run a Single-Instance Stateful Application > Deploy MySQL  ```yaml apiVersion: v1 kind: PersistentVolume metadata:   name: mysql-pv-volume   labels:     type: local spec:   storageClassName: manual   capacity:     storage: 20Gi   accessModes:     - ReadWriteOnce   hostPath:     path: "/mnt/data" --- apiVersion: v1 kind: PersistentVolumeClaim metadata:   name: mysql-pv-claim spec:   storageClassName: manual   accessModes:     - ReadWriteOnce   resources:     requests:       storage: 20Gi ```  1. 

- [ ] negative is actually relevant

## 42. [symptom] windows containerized csi node plugins are failing to mount file systems because privileged disk operations are not working

**Positive** `k8s/concepts/storage/volumes#058`

> Volumes > csi > Windows CSI proxy  CSI node plugins need to perform various privileged operations like scanning of disk devices and mounting of file systems. These operations differ for each host operating system. For Linux worker nodes, containerized CSI node plugins are typically deployed as privileged containers. For Windows worker nodes, privileged operations for containerized CSI node plugins are supported using csi-proxy, a community-managed, stand-alone binary that needs to be pre-install

**Negative** `k8s/concepts/storage/persistent-volumes#066`

> Persistent Volumes > Volume Snapshot and Restore Volume from Snapshot Support  Volume snapshots only support the out-of-tree CSI volume plugins. For details, see Volume Snapshots. In-tree volume plugins are deprecated. You can read about the deprecated volume plugins in the Volume Plugin FAQ.

- [ ] negative is actually relevant

## 43. [how_to] what resource limits and requests are needed for guaranteed qos class

**Positive** `k8s/concepts/workloads/pods/pod-qos#003`

> Pod Quality of Service Classes > Guaranteed > Criteria  For a Pod to be given a QoS class of `Guaranteed`:  * Every Container in the Pod must have a memory limit and a memory request, both greater than zero. * For every Container in the Pod, the memory limit must equal the memory request. * Every Container in the Pod must have a CPU limit and a CPU request, both greater than zero. * For every Container in the Pod, the CPU limit must equal the CPU request.  If instead the Pod uses Pod-level resou

**Negative** `k8s/concepts/workloads/pods/pod-qos#011`

> Pod Quality of Service Classes > Memory QoS with cgroup v2 > Configuring memory reservation  Memory reservation is controlled via the kubelet configuration field `memoryReservationPolicy`:  - `None` (default): the kubelet does not set `memory.min` or `memory.low` for   containers and pods. No memory is hard-locked by the kernel. - `TieredReservation`: the kubelet sets tiered memory protection based on the   Pod's QoS class:   - **Guaranteed** pods: `memory.min` is set to memory requests. The ker

- [ ] negative is actually relevant

## 44. [symptom] endpointslice controller is allocating wrong proportions because control plane nodes are ignored

**Positive** `k8s/concepts/services-networking/topology-aware-routing#010`

> Topology Aware Routing > Constraints  * Topology Aware Hints are not used when `internalTrafficPolicy` is set to `Local`   on a Service. It is possible to use both features in the same cluster on different   Services, just not on the same Service.  * This approach will not work well for Services that have a large proportion of   traffic originating from a subset of zones. Instead this assumes that incoming   traffic will be roughly proportional to the capacity of the Nodes in each   zone.  * The

**Negative** `k8s/concepts/workloads/workload-api/workloadbuilder#010`

> Scheduling Building Block APIs and the workloadbuilder Library > The workloadbuilder library > How a controller uses it  A controller describes its workload as a tree of `WorkloadItem` nodes, one per logical component. A node with no children becomes a single `PodGroupTemplate`, while a node with children becomes a `CompositePodGroupTemplate` over them, which is how a multi-level controller represents a group of groups. Each node carries:  * a *default config*, the controller's own defaults for 

- [ ] negative is actually relevant

## 45. [symptom] need to quickly edit a pod definition image version in place without editing full yaml manually

**Positive** `k8s/reference/kubectl/quick-reference#032`

> kubectl Quick Reference > Update a single-container pod's image version (tag) to v4  kubectl get pod mypod -o yaml | sed 's/\(image: myimage\):.*$/\1:v4/' | kubectl replace -f -  kubectl label pods my-pod new-label=awesome # Add a Label kubectl label pods my-pod new-label- # Remove a label kubectl label pods my-pod new-label=new-value --overwrite # Overwrite an existing value kubectl annotate pods my-pod icon-url=http://goo.gl/XXBTWq # Add an annotation kubectl annotate pods my-pod icon-url- # R

**Negative** `k8s/concepts/workloads/pods#003`

> Pods > Using Pods  The following is an example of a Pod which consists of a container running the image `nginx:1.14.2`.  ```yaml apiVersion: v1 kind: Pod metadata:   name: nginx spec:   containers:   - name: nginx     image: nginx:1.14.2     ports:     - containerPort: 80 ```  To create the Pod shown above, run the following command: ```shell kubectl apply -f https://k8s.io/examples/pods/simple-pod.yaml ```  Pods are generally not created directly and are created using workload resources. See Wo

- [ ] negative is actually relevant

## 46. [how_to] how do I configure imagefs available threshold for minimum eviction reclaim

**Positive** `k8s/concepts/scheduling-eviction/node-pressure-eviction#037`

> Node-pressure Eviction > Node conditions > Minimum eviction reclaim  Similarly, the kubelet tries to reclaim the `imagefs` resource until the `imagefs.available` value reaches `102Gi`, representing 102 GiB of available container image storage. If the amount of storage that the kubelet could reclaim is less than 2GiB, the kubelet doesn't reclaim anything.  The default `eviction-minimum-reclaim` is `0` for all resources.

**Negative** `k8s/tasks/run-application/configure-pdb#010`

> Specifying a Disruption Budget for your Application > Specifying a PodDisruptionBudget  In typical usage, a single budget would be used for a collection of pods managed by a controller—for example, the pods in a single ReplicaSet or StatefulSet.  Note: A disruption budget does not truly guarantee that the specified number/percentage of pods will always be up. For example, a node that hosts a pod from the collection may fail when the collection is at the minimum size specified in the budget, thus

- [ ] negative is actually relevant

## 47. [incident_snapshot] batch-processor-w9v92jctm-zqnbd 0/1 Completed 0 (5m ago) | job workers spinning up to consume queue messages in parallel

**Positive** `k8s/tasks/job/coarse-parallel-processing-work-queue#000`

> Coarse Parallel Processing Using a Work Queue  In this example, you will run a Kubernetes Job with multiple parallel worker processes.  In this example, as each pod is created, it picks up one unit of work from a task queue, completes it, deletes it from the queue, and exits.  Here is an overview of the steps in this example:  1. **Start a message queue service.** In this example, you use RabbitMQ, but you could use another    one. In practice you would set up a message queue service once and re

**Negative** `k8s/tasks/job/coarse-parallel-processing-work-queue#004`

> Coarse Parallel Processing Using a Work Queue > Testing the message queue service  ``` RABBITMQ_SERVICE_SERVICE_HOST=10.0.147.152 ``` (the IP address will vary)  Next you will verify that you can create a queue, and publish and consume messages.  ```shell # Run these commands inside the Pod # In the next line, rabbitmq-service is the hostname where the rabbitmq-service # can be reached.  5672 is the standard port for rabbitmq. export BROKER_URL=amqp://guest:guest@rabbitmq-service:5672 # If you c

- [ ] negative is actually relevant

## 48. [symptom] kubelet logs are filling up with warnings about deprecated container garbage collection flags

**Positive** `k8s/concepts/scheduling-eviction/node-pressure-eviction#013`

> Node-pressure Eviction > Eviction signals and thresholds > Deprecated kubelet garbage collection features  Some kubelet garbage collection features are deprecated in favor of eviction:  | Existing Flag | Rationale | | ------------- | --------- | | `--maximum-dead-containers` | deprecated once old logs are stored outside of container's context | | `--maximum-dead-containers-per-container` | deprecated once old logs are stored outside of container's context | | `--minimum-container-ttl-duration` |

**Negative** `k8s/tasks/debug/debug-cluster/crictl#014`

> Debugging Kubernetes nodes with crictl > Example crictl commands > Get a container's logs  Get all container logs:  ```shell crictl logs 87d3992f84f74 ```  The output is similar to this:  ``` 10.240.0.96 - - [06/Jun/2018:02:45:49 +0000] "GET / HTTP/1.1" 200 612 "-" "curl/7.47.0" "-" 10.240.0.96 - - [06/Jun/2018:02:45:50 +0000] "GET / HTTP/1.1" 200 612 "-" "curl/7.47.0" "-" 10.240.0.96 - - [06/Jun/2018:02:45:51 +0000] "GET / HTTP/1.1" 200 612 "-" "curl/7.47.0" "-" ```  Get only the latest `N` lin

- [ ] negative is actually relevant

## 49. [how_to] how to write a network policy that allows traffic from a specific namespace or a specific pod label

**Positive** `k8s/concepts/services-networking/network-policies#012`

> Network Policies > Behavior of `to` and `from` selectors  This policy contains a single `from` element allowing connections from Pods with the label `role=client` in namespaces with the label `user=alice`. But the following policy is different:  ```yaml   ...   ingress:   - from:     - namespaceSelector:         matchLabels:           user: alice     - podSelector:         matchLabels:           role: client   ... ```  It contains two elements in the `from` array, and allows connections from Pod

**Negative** `k8s/concepts/scheduling-eviction/assign-pod-node#026`

> Assigning Pods to Nodes > Inter-pod affinity and anti-affinity > Pod Affinity Example  You can modify or disable the   admission controller if you want to allow custom topologies.  In addition to `labelSelector` and `topologyKey`, you can optionally specify a list of namespaces which the `labelSelector` should match against using the `namespaces` field at the same level as `labelSelector` and `topologyKey`. If omitted or empty, `namespaces` defaults to the namespace of the Pod where the affinity

- [ ] negative is actually relevant

## 50. [how_to] how do I configure an emptydir volume to use ram instead of node disk

**Positive** `k8s/concepts/storage/volumes#009`

> Volumes > Types of volumes > emptyDir  The `emptyDir.medium` field controls where `emptyDir` volumes are stored. By default `emptyDir` volumes are stored on whatever medium that backs the node such as disk, SSD, or network storage, depending on your environment. If you set the `emptyDir.medium` field to `"Memory"`, Kubernetes mounts a tmpfs (RAM-backed filesystem) for you instead. While tmpfs is very fast, be aware that, unlike disks, files you write count against the memory limit of the contain

**Negative** `k8s/concepts/storage/windows-storage#000`

> Windows Storage > Persistent storage  This page provides an storage overview specific to the Windows operating system.  Windows has a layered filesystem driver to mount container layers and create a copy filesystem based on NTFS. All file paths in the container are resolved only within the context of that container.  * With Docker, volume mounts can only target a directory in the container, and not   an individual file. This limitation does not apply to containerd. * Volume mounts cannot project

- [ ] negative is actually relevant
