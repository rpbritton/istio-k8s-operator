# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from copy import deepcopy

import pytest
from lightkube import ApiError, codecs
from lightkube.resources.core_v1 import ConfigMap
from scenario import Context, State

from src.charm import IstioCoreCharm

MANIFEST = """
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: ztunnel
spec:
  selector:
    matchLabels:
      app: ztunnel
  template:
    metadata:
      labels:
        app: ztunnel
    spec:
      containers:
        - name: istio-proxy
          image: istio-ztunnel
          env:
            - name: CA_ADDRESS
              value: istiod.owner.svc:15012
            - name: CA_ROOT_CA
              value: old-root-path
            - name: XDS_ROOT_CA
              value: old-root-path
        - name: other-container
          image: other
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: istio-cni-node
spec:
  selector:
    matchLabels:
      app: istio-cni-node
  template:
    metadata:
      labels:
        app: istio-cni-node
    spec:
      containers:
        - name: install-cni
          image: istio-install-cni
"""


@pytest.fixture()
def trust_context(mocker):
    client = mocker.patch("src.charm.Client", autospec=True).return_value
    client.get.return_value = ConfigMap(data={"root-cert.pem": "first-root"})
    context = Context(IstioCoreCharm, app_name="istio")
    with context(context.on.update_status(), State()) as manager:
        yield manager.charm, client


def test_changed_root_updates_only_ztunnel_startup_trust(trust_context):
    charm, client = trust_context
    first = codecs.load_all_yaml(MANIFEST)
    original = deepcopy(first)

    charm._configure_ztunnel_trust(first)
    client.get.return_value = ConfigMap(data={"root-cert.pem": "replacement-root"})
    second = codecs.load_all_yaml(MANIFEST)
    charm._configure_ztunnel_trust(second)
    repeated = codecs.load_all_yaml(MANIFEST)
    charm._configure_ztunnel_trust(repeated)

    for resources, root in [(first, "first-root"), (second, "replacement-root")]:
        containers = resources[0].spec.template.spec.containers
        assert [(env.name, env.value) for env in containers[0].env] == [
            ("CA_ADDRESS", "istiod.owner.svc:15012"),
            ("CA_ROOT_CA", root),
            ("XDS_ROOT_CA", root),
        ]
        assert containers[1] == original[0].spec.template.spec.containers[1]
        assert resources[1] == original[1]
    assert first[0].spec.template != second[0].spec.template
    assert second == repeated
    assert client.get.call_count == 3
    client.get.assert_called_with(ConfigMap, "istio-ca-root-cert")


@pytest.mark.parametrize("code", [404, 403, 500])
def test_root_lookup_only_tolerates_initial_missing_configmap(trust_context, code):
    charm, client = trust_context
    error = ApiError(status={"code": code, "reason": "Unavailable", "message": "Unavailable"})
    client.get.side_effect = error
    resources = codecs.load_all_yaml(MANIFEST)
    before = deepcopy(resources)

    if code == 404:
        charm._configure_ztunnel_trust(resources)
    else:
        with pytest.raises(ApiError) as caught:
            charm._configure_ztunnel_trust(resources)
        assert caught.value is error

    assert resources == before


@pytest.mark.parametrize("data", [None, {}, {"root-cert.pem": ""}])
def test_empty_root_is_not_silently_trusted(trust_context, data):
    charm, client = trust_context
    client.get.return_value = ConfigMap(data=data)

    with pytest.raises(ValueError, match="has no root-cert.pem"):
        charm._configure_ztunnel_trust(codecs.load_all_yaml(MANIFEST))


def test_control_plane_reconciliation_includes_observed_root(trust_context, mocker):
    charm, client = trust_context
    mocker.patch.object(charm, "_get_cni_binding", return_value=None)
    ictl = mocker.patch.object(charm, "_get_istioctl").return_value
    ictl.manifest_generate.return_value = MANIFEST
    resource_manager = mocker.patch.object(charm, "_get_resource_manager").return_value

    charm._reconcile_control_plane()

    resources = resource_manager.reconcile.call_args.args[0]
    env = {item.name: item.value for item in resources[0].spec.template.spec.containers[0].env}
    assert env["CA_ROOT_CA"] == env["XDS_ROOT_CA"] == "first-root"
