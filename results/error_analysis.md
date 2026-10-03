# Error analysis: 30 worst test queries (tuned model)

| tag | count |
| --- | --- |
| wrong_label | 2 |
| ambiguous_query | 9 |
| missing_doc | 2 |
| chunk_too_long | 0 |
| model_miss | 17 |

## gen/28d14efdcc9a1dd9 (kubectl_output): ambiguous_query, not in top 100

Query: `NAME TYPE REASON AGE pi-with-timeout Failed DeadlineExceeded 1m`

Relevant: k8s/concepts/workloads/controllers/job#046

Top 3 returned: Resource Management for Pods and Containers > Troubleshooting > My Pods are pending with event message `FailedScheduling`; CronJob > Writing a CronJob spec > Deadline for delayed Job start; CronJob > Writing a CronJob spec > Deadline for delayed Job start

Bare `kubectl get` row with no question or context; several Job/CronJob chunks fit equally.

## so/10884 (stackoverflow): missing_doc, not in top 100

Query: `I am using a Kubernetes Cronjob to run period database restores and post restore scripts which runs against the target environment which include tasks such as working with the database, redis, and file system. The issue I am facing is that I have to re-define all the environment variables I use in m`

Relevant: k8s/tasks/inject-data-application/distribute-credentials-secure#016

Top 3 returned: CronJob > CronJob limitations > Modifying a CronJob; Define Environment Variables for a Container > Define an environment variable for a container; Running Automated Tasks with a CronJob > Deleting a CronJob

No chunk explains sharing env vars between a Deployment and a CronJob; the labeled chunk (envFrom a Secret) is only the nearest thing.

## so/27581 (stackoverflow): model_miss, rank 94

Query: `Hi I have followed this video from starting to end. Using kubectl describe to show the Service that was created yields $ kubectl describe -n ingress-nginx service/ingress-nginx Name: ingress-nginx Namespace: ingress-nginx Labels: <none> Annotations: <none> Selector: app=nginx-ingress Type: LoadBalan`

Relevant: runbook/loadbalancer-pending#000

Top 3 returned: Ingress > Types of Ingress > Ingress backed by a single Service; Ingress > What is Ingress?; Ingress returns 502, 503 or 504 > Checks

Long `kubectl describe` paste hides the question (why no external IP); the LoadBalancer runbook symptoms chunk ranks far down.

## so/11903 (stackoverflow): model_miss, rank 76

Query: `I have a Kafka cluster hosted in GKE. Google updates GKE nodes in weekly basis and whenever this happens Kafka becomes temporarily unavailable and this causes massive error/rebalance to get it backup to healthy state. Currently we rely on K8 retry to eventually succeed once upgrade completes and clu`

Relevant: k8s/concepts/workloads/pods/disruptions#003, k8s/tasks/run-application/configure-pdb#003

Top 3 returned: Disruptions > PodDisruptionBudget example; Kubernetes Self-Healing; Pod Lifecycle > Container restarts > Container restarts and resilience

Needs the inference Kafka upgrades -> voluntary disruption -> PodDisruptionBudget; the model never connects them.

## incident/oom-killed/brief (real_incident_seen): ambiguous_query, rank 49

Query: `inventory-799bw6c8qg-kvbzh 1/1 Running 1 (3s ago) | Warning BackOff Back-off restarting failed container inventory in pod inventory-799bw6c8qg-kvbzh_prod(681d0337-535c-4106-a2ad-eac8c3caf9da)`

Relevant: runbook/oomkilled#000, runbook/oomkilled#001, runbook/oomkilled#002

Top 3 returned: Pod Lifecycle > How Pods handle problems with containers; Jobs > Handling Pod and container failures; Jobs > Handling Pod and container failures > Pod failure policy

The brief snapshot shows only `BackOff`, with no OOMKilled reason, so any crash-loop cause fits.

## gen/bb141ad982ce4819 (how_to): wrong_label, rank 46

Query: `how to verify that deployment pods are up and running with label selectors`

Relevant: k8s/tasks/debug/debug-application/debug-service#003

Top 3 returned: Deployments > Writing a Deployment Spec > Selector; Debug Running Pods > Using `kubectl describe pod` to fetch details about pods; Deployments > Creating a Deployment

The labeled chunk (a Deployment YAML in debug-service) does not explain how to verify pods with label selectors; fix the label.

## so/8622 (stackoverflow): model_miss, rank 46

Query: `We are deploying a spring-boot application using spring-session-hazelcast + hazelcast-kubernetes on an OpenShift/Kubernetes cluster. Due to the nature of our platform, we can only use service-dns configuration. We expose a service on port 5701 for multicasting and set service-dns property to the mul`

Relevant: k8s/concepts/services-networking/service#046

Top 3 returned: Service > Discovering services > DNS; DNS for Services and Pods > Pods > Pod's DNS Policy; DNS for Services and Pods

The answer is the headless Service chunk; the query talks about service-dns and multicast, so the model returns generic DNS pages.

## gen/289a87657a28a681 (how_to): wrong_label, rank 17

Query: `how to increase memory limit for a container after oomkill`

Relevant: k8s/concepts/configuration/manage-resources-containers#047

Top 3 returned: Assign Memory Resources to Containers and Pods > If you do not specify a memory limit; Assign Memory Resources to Containers and Pods > Exceed a Container's memory limit; Assign Memory Resources to Containers and Pods > Exceed a Container's memory limit

The labeled chunk is a describe output of an OOM kill and never says how to raise the limit; the returned chunks come closer.

## so/7449 (stackoverflow): ambiguous_query, rank 17

Query: `We have a deployment with a large replicas number ( > 1 ) that we must deploy in the same zone. We stumbled upon this documentation section: https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#an-example-of-a-pod-that-uses-pod-affinity which explains how to schedule pods in zone`

Relevant: k8s/concepts/scheduling-eviction/assign-pod-node#018, k8s/concepts/scheduling-eviction/assign-pod-node#035

Top 3 returned: Assigning Pods to Nodes > Inter-pod affinity and anti-affinity > Pod Affinity Example; Assigning Pods to Nodes > Inter-pod affinity and anti-affinity > Pod Affinity Example; Pod Topology Spread Constraints > Topology spread constraint examples > Example: topology spread constraints with node affinity

Rank 1 (pod affinity example with zones) answers the question as well as the labeled chunks; qrels list only two chunks.

## gen/211aac2d5b740506 (how_to): model_miss, rank 16

Query: `what are the available action values for pod failure policy rules in kubernetes`

Relevant: k8s/concepts/workloads/controllers/job#038

Top 3 returned: Jobs > Handling Pod and container failures > Pod failure policy; Jobs > Handling Pod and container failures > Pod failure policy; Jobs > Handling Pod and container failures > Pod failure policy

Right page, neighbouring chunk: the three top results are adjacent Job chunks about pod failure policy.

## gen/1ca216c14cd3e8c4 (how_to): model_miss, rank 15

Query: `how to request a custom resource in a pod spec limits`

Relevant: k8s/concepts/configuration/manage-resources-containers#035

Top 3 returned: Resource Management for Pods and Containers > Pod-level resource specification; Resource Management for Pods and Containers > Resource requests and limits of Pod and container; Assign Pod-level CPU and memory resources > Create a pod with resource requests and limits at both pod-level and container-level

Right page again; the extended-resources chunk loses to two neighbouring chunks of manage-resources-containers.

## so/1264 (stackoverflow): missing_doc, rank 15

Query: `I have setup a Postgres pod on my Kubernetes cluster, and I am trying to troubleshoot it a bit. I would like to use the official Postgres image and deploy it to my Kubernetes cluster using kubectl. Given that my Postgres server connection details are: host: mypostgres port: 5432 username: postgres p`

Relevant: k8s/tasks/debug/debug-application/debug-service#001, k8s/tasks/run-application/run-replicated-stateful-application#023

Top 3 returned: Downstream dependency unavailable (Redis, Postgres, other services) > Likely causes; Run a Single-Instance Stateful Application > Accessing the MySQL instance; Downstream dependency unavailable (Redis, Postgres, other services) > Symptoms

Corpus has a mysql client pod example but nothing for psql; the labeled chunks are the closest analogues.

## incident/pod-stuck-finalizer/full (real_incident_seen): ambiguous_query, rank 14

Query: `ledger-0 1/1 Terminating 0 | Status: Terminating (lasts 0s) | event: Normal Killing Stopping container ledger`

Relevant: runbook/pod-stuck-terminating#000, runbook/pod-stuck-terminating#001, runbook/pod-stuck-terminating#002

Top 3 returned: Determine the Reason for Pod Failure > Writing and reading a termination message; Determine the Reason for Pod Failure; kubectl for Docker Users > docker stop and docker rm

`Terminating (lasts 0s)` is a normal termination, with no sign of a stuck finalizer.

## so/24911 (stackoverflow): model_miss, rank 14

Query: `I have two clusters NAME LOCATION MASTER_VERSION MASTER_IP MACHINE_TYPE NODE_VERSION NUM_NODES STATUS cassandra-cluster europe-west4-a 1.14.10-gke.36 xx.90.xx.31 n1-standard-1 1.14.10-gke.36 3 RUNNING codingjediweb-cluster europe-west4-a 1.14.10-gke.36 uu.90.uu.182 n1-standard-1 1.14.10-gke.36 2 RUN`

Relevant: k8s/concepts/configuration/organize-cluster-access-kubeconfig#003, k8s/tasks/debug/debug-cluster/troubleshoot-kubectl#007

Top 3 returned: StatefulSets > Pod Identity > Stable Network ID; kubectl Quick Reference > Create a secret with several keys; Developing and debugging services locally using telepresence > Connecting your local machine to a remote Kubernetes cluster

Pasted GKE cluster table dominates the query; the kubeconfig contexts chunks are not retrieved.

## gen/8983c06ed00dbd64 (symptom): model_miss, rank 11

Query: `why is my kubectl command hitting the wrong cluster`

Relevant: k8s/tasks/debug/debug-cluster/troubleshoot-kubectl#007

Top 3 returned: Command line tool (kubectl) > In-cluster authentication and namespace overrides; Troubleshooting Clusters; Troubleshooting kubectl

Query wording is general; the model returns kubectl overview pages instead of the contexts section.

## incident/pod-stuck-finalizer/brief (real_incident_seen): ambiguous_query, rank 11

Query: `ledger-0 1/1 Terminating 0 | Normal Killing Stopping container ledger`

Relevant: runbook/pod-stuck-terminating#000, runbook/pod-stuck-terminating#001, runbook/pod-stuck-terminating#002

Top 3 returned: Pod Lifecycle > Termination of Pods > Stop Signals; Container Lifecycle Hooks > Container hooks > Hook handler execution; Pod Lifecycle > Termination of Pods

Same snapshot as the full form with less context: a normal `Killing` event.

## gen/a7a26fc1e6ab9bce (error_string): model_miss, rank 10

Query: `kubectl.config.k8s.io/v1beta1`

Relevant: k8s/reference/kubectl/kuberc#000

Top 3 returned: Troubleshooting kubectl > Check kubeconfig; Set Up DRA in a Cluster > Optional: enable additional DRA API groups; Organizing Cluster Access Using kubeconfig Files

Query is only an apiVersion identifier; a dense model has little signal (BM25 helps here).

## gen/406362474f40f4c7 (symptom): model_miss, rank 9

Query: `pods get evicted right away when a taint is added instead of waiting the hour we configured`

Relevant: k8s/concepts/scheduling-eviction/taint-and-toleration#007, k8s/concepts/scheduling-eviction/taint-and-toleration#008

Top 3 returned: Taints and Tolerations > Taint based Evictions; Taints and Tolerations > Taint based Evictions; Nodes > Node controller > Rate limits on eviction

Right page (taint and toleration), wrong chunk: the tolerationSeconds example ranks 9th.

## gen/db74cabd76e38a0b (how_to): ambiguous_query, rank 9

Query: `how to add imagePullSecrets to the auth-api deployment`

Relevant: runbook/image-pull-backoff#005

Top 3 returned: Secrets > Using imagePullSecrets > Arranging for imagePullSecrets to be automatically attached; Images > Creating a Secret with a Docker config > Referring to `imagePullSecrets` on a Pod; Images > Creating a Secret with a Docker config > Referring to `imagePullSecrets` on a Pod

Rank 1 (Secrets: manually specifying an imagePullSecret) also answers the how-to; the runbook chunk is one of several.

## incident/ephemeral-storage-eviction/brief (real_incident_heldout): ambiguous_query, rank 9

Query: `thumbnailer-8fdrp6gkmp-b27qm 0/1 ContainerCreating 0 | Warning Evicted Pod ephemeral local storage usage exceeds the total limit of containers 20Mi.`

Relevant: runbook/node-pressure-eviction#000, runbook/node-pressure-eviction#001, runbook/node-pressure-eviction#002

Top 3 returned: Local ephemeral storage > Ephemeral storage consumption management; Local ephemeral storage > Setting requests and limits for local ephemeral storage; Local ephemeral storage > Ephemeral storage consumption management

Rank 1-3 are the Kubernetes ephemeral-storage docs, which explain this event; qrels count only the runbook.

## gen/5afce9928773e17d (symptom): model_miss, rank 8

Query: `pods requesting hardware accelerators are stuck in pending because tolerations are missing`

Relevant: k8s/concepts/scheduling-eviction/taint-and-toleration#016

Top 3 returned: Pods Pending due to insufficient CPU or memory > Symptoms; Taints and Tolerations > Example Use Cases; Taints and Tolerations > Device taints and tolerations

Neighbouring chunk of the right page ranks 2nd; the accelerator-toleration chunk is 8th.

## so/23788 (stackoverflow): model_miss, rank 8

Query: `I am trying to test inter-pod communication without expose as service. I have read that a pod does have FQDN in kubedns. kubernetes doc Its default should be (A Record) metadata_name.namespace.svc.cluster.local or hostname.subdomain.namespace.svc.cluster.local But I tried both with curl and nslookup`

Relevant: k8s/concepts/services-networking/dns-pod-service#009, k8s/concepts/services-networking/dns-pod-service#012

Top 3 returned: Debug Services > Does the Service work by DNS name?; Debug Services > Does the Service work by DNS name?; Debug Services > Does the Service work by DNS name?

Query asks for pod FQDNs; the model returns the Service DNS debugging steps instead of the pod hostname/subdomain section.

## gen/1c50dae0941e087e (symptom): model_miss, rank 7

Query: `dns resolution fails for ledger-worker service when called across namespaces`

Relevant: runbook/dns-resolution-failure#004, runbook/dns-resolution-failure#005

Top 3 returned: DNS for Services and Pods > DNS resolution on Windows nodes; Service > Discovering services > DNS; DNS for Services and Pods > Namespaces of Services

Cross-namespace DNS fix chunks of the runbook lose to generic Kubernetes DNS pages.

## gen/372b2a842f08aa49 (symptom): model_miss, rank 7

Query: `how do I tell from describe output how long our batch job has been on hold`

Relevant: k8s/concepts/workloads/controllers/job#062

Top 3 returned: Running Automated Tasks with a CronJob > Creating a CronJob; Parallel Processing using Expansions > Create Jobs based on a template > Create Jobs from the manifests; Running Automated Tasks with a CronJob > Creating a CronJob

`on hold` means suspended; the model matches CronJob status output instead of the suspend section.

## gen/9ebd7a15068a47c7 (error_string): model_miss, rank 7

Query: `0/42 nodes available: insufficient cpu`

Relevant: k8s/concepts/configuration/manage-resources-containers#037, k8s/concepts/configuration/manage-resources-containers#038, runbook/pending-insufficient-resources#002

Top 3 returned: Assign CPU Resources to Containers and Pods > Specify a CPU request and a CPU limit; Assign CPU Resources to Containers and Pods > Specify a CPU request that is too big for your Nodes; Assign CPU Resources to Containers and Pods > Specify a CPU request that is too big for your Nodes

Exact scheduler message; the model returns CPU assignment pages while the FailedScheduling chunks rank 7th.

## so/24551 (stackoverflow): model_miss, rank 7

Query: `I am trying to change priority of an existing Kubernetes Pod using 'patch' command, but it returns error saying that this is not one of the fields that can be modified. I can patch the priority in the Deployment spec, but it would cause the Pod to be recreated (following the defined update strategy)`

Relevant: k8s/concepts/workloads/pods#012

Top 3 returned: Pod Priority and Preemption > PriorityClass > Notes about PodPriority and existing clusters; Pod Priority and Preemption > Pod priority > Effect of Pod priority on scheduling order; Advanced Pod Configuration > PriorityClasses

The answer is Pod immutability; the query's wording about priority pulls in the priority/preemption pages.

## gen/03bd4ffdc52643e8 (symptom): ambiguous_query, rank 6

Query: `need to run node local daemon pods automatically on every newly added cluster node`

Relevant: k8s/concepts/workloads#001, k8s/concepts/workloads/controllers/daemonset#008

Top 3 returned: Workload Management; DaemonSet; DaemonSet > Alternatives to DaemonSet > Deployments

Rank 1 (workload overview describing DaemonSets) answers it about as well as the labeled chunks.

## gen/a2b91b1e1bbd83b3 (symptom): model_miss, rank 6

Query: `pods are being immediately terminated when a node gets tainted with noExecute`

Relevant: k8s/concepts/scheduling-eviction/taint-and-toleration#004

Top 3 returned: Taints and Tolerations > Taint based Evictions; Nodes > Node controller > Rate limits on eviction; Disruptions > Pod disruption conditions

Right topic; the NoExecute definition chunk ranks 6th behind other taint chunks.

## so/17625 (stackoverflow): ambiguous_query, rank 6

Query: `I am getting an error message after running some kubectl commands (GCP command line - gcloud). I have a K8S cluster created in GKE. Example: kubectl describe node gke_k8s_cluster_name Error from server (Forbidden): leases.coordination.k8s.io "gke_k8s_cluster_name" is forbidden: User "MY_SERVICE_ACCO`

Relevant: runbook/rbac-forbidden#001, runbook/rbac-forbidden#003

Top 3 returned: Leases; RBAC Forbidden errors from a ServiceAccount or user > Symptoms; Leases > API server identity

Rank 2 is the RBAC Forbidden symptoms chunk of the right runbook, which qrels leave out (only 2 of its chunks are listed).

## gen/0e18c4647285bab6 (how_to): model_miss, rank 5

Query: `how to verify that new pods automatically inherit image pull secrets from the service account`

Relevant: k8s/tasks/configure-pod-container/configure-service-account#017

Top 3 returned: Volumes > The mount into the container is read-only. > image; Images > Using a private registry > Ensure image pull credential verification; Images > Using a private registry > Ensure image pull credential verification

The service-account imagePullSecrets verification chunk ranks 5th behind general image pages.
