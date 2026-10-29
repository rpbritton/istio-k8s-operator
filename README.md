> [!IMPORTANT]
> Moved to https://github.com/canonical/service-mesh/tree/main/charms/istio-k8s.
> This repo is no longer maintained.


# Istio Service Mesh Charmed Operator

[![CharmHub Badge](https://charmhub.io/istio-k8s/badge.svg)](https://charmhub.io/istio-k8s)
[![Release](https://github.com/canonical/istio-k8s-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/istio-k8s-operator/actions/workflows/release.yaml)
[![Discourse Status](https://img.shields.io/discourse/status?server=https%3A%2F%2Fdiscourse.charmhub.io&style=flat&label=CharmHub%20Discourse)](https://discourse.charmhub.io)

## Description

[Istio](https://istio.io) is an open source project that implements a service mesh, allowing for a way to observe and control the traffic flow between applications in Kubernetes.  Istio is a key tool in securing Kubernetess workloads and hardening your environment.

The istio-k8s Charmed Operator deploys and manages the Istio control plane components in a Kubernetes cluster.  The operator is designed to be used in conjunction with the [istio-beacon-k8s](https://github.com/canonical/istio-beacon-k8s-operator) and [istio-ingress-k8s](https://github.com/canonical/istio-ingress-k8s-operator) charms to deploy and configure Istio using Juju.

## Usage

Typically, Istio is deployed to the `istio-system` namespace without any other applications in that namespace.  This is because any Istio Custom Resource deployed to Istio's system namespace are treated as a globally scoped (for example, an `AuthorizationPolicy` deployed in Istio's namespace applies to the entire cluster).  Following these best practices, we can deploy Charmed Istio by:

```bash
juju add-model istio-system
juju deploy istio-k8s --trust
```

This deploys the Istio control plane, which can then be used by anything in the Kubernetes cluster.  To get started from here, see:
* [istio-beacon-k8s](https://github.com/canonical/istio-beacon-k8s-operator) for how to quickly integrate charms to the mesh Istio's Ambient mode
* [istio-ingress-k8s](https://github.com/canonical/istio-ingress-k8s-operator) to create ingresses to the cluster
* for general Istio guidance, see the [Istio docs](https://istio.io/latest/docs/), for example [how to deploy an application to an Istio ambient mesh](https://istio.io/latest/docs/ambient/getting-started/deploy-sample-app/)

### CNI ownership and recovery

Only one independent Istio installation is supported per cluster. The charm claims
`ClusterRoleBinding/istio-cni` atomically before modifying shared resources. Another
installation is blocked with the owner's application instance and namespace, even
when its configuration matches: CNI node-local files and ztunnel are also shared.
The owning charm can reconcile and repair its resources normally.

Remove the previous installation normally whenever possible. A blocked contender
automatically retries when ownership is released. Do not delete the binding while
the previous installation is running or terminating.

If an installation was removed without cleaning up its cluster-scoped resources,
the new charm reports an orphaned binding. After removing the old installation and
its Juju model, inspect the binding and explicitly reclaim it:

```bash
kubectl get clusterrolebinding istio-cni -o yaml
juju run istio/leader reclaim-cni binding-uid=<metadata.uid>
```

Recovery refuses while the previous namespace exists, including when it is empty
or terminating. No pods is not proof of abandonment: a controller can recreate them,
and a new owner claims the binding before creating its pods. Do not recreate the old
installation or namespace during recovery. Unrecognised or unlabelled bindings
require manual investigation rather than automatic adoption.

The action uses the binding's resource version so competing recovery requests cannot
both acquire it. Once acquired, it removes the previous owner's labelled cluster-scoped
control-plane RBAC and webhooks, then reconciles the new installation. CRDs and mesh
custom resources are preserved. Cleanup failures retain the claim and are retried by
subsequent reconciliation. Check Juju status and mesh traffic after recovery; acquiring
ownership alone does not establish workload or endpoint health.

Recovered installations use Istio's host-network mode for the CNI agent, so stale
node-local CNI credentials cannot prevent its replacement from starting and repairing
the node configuration. Normal installations keep their existing networking mode.

Back up mesh configuration before removing an old installation or model: their
normal cleanup can delete CRDs and custom resources. Recovery preserves resources
that still exist; it cannot restore data already removed during teardown.
