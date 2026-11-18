"""Permanently SIMULATED test data; never imported by the SRE tool."""

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "2026-10-10T12:00:00Z"
SUBSCRIPTION = "11111111-1111-4111-8111-111111111111"
CLUSTER_ID = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-client-lab/providers/Microsoft.ContainerService/managedClusters/aks-client-lab"
TEST_TEMPLATE = '<!doctype html><html lang="es"><meta charset="utf-8"><title>SIMULATED CLIENTE</title><script type="application/json" id="report-data">__REPORT_DATA_JSON__</script></html>'


def load_engine(standalone=False):
    path = (ROOT.parent / "manifests" / "tools" / "generate-aks-waf-report.py" if standalone else ROOT / "engine.py")
    spec = importlib.util.spec_from_file_location("aks_engine_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not standalone:
        build_spec = importlib.util.spec_from_file_location("aks_builder_under_test", ROOT / "build_tool.py")
        builder = importlib.util.module_from_spec(build_spec)
        build_spec.loader.exec_module(builder)
        module.CATALOG = builder.load_catalog()
        module.HTML_TEMPLATE = (ROOT / "report_template.html").read_text(encoding="utf-8") if (ROOT / "report_template.html").exists() else TEST_TEMPLATE
    module.SUBSCRIPTION_ID = SUBSCRIPTION
    module.TENANT_ID = "22222222-2222-4222-8222-222222222222"
    module.MANAGED_IDENTITY_CLIENT_ID = "33333333-3333-4333-8333-333333333333"
    module.AUTO_DISCOVERY = False  # legacy fixed-allowlist fixtures; discovery is covered by test_fleet.py
    module.APPROVED_CLUSTERS = {"aks-client-lab": {"resource_group": "rg-client-lab", "environment": "LAB",
                                                "kubernetes_enabled": True, "include_node_resource_group": True, "advisor_enabled": True,
                                                "approved_related_resource_ids": [], "approved_cost_resource_ids": [],
                                                "cost_scope": "disabled", "cost_timeframe": "last_30_days", "requirements": {}}}
    return module


def api_object(kind, name, namespace=None, **fields):
    metadata = {"uid": "simulated-uid-" + kind + "-" + str(namespace or "") + "-" + name, "name": name, "resourceVersion": "10"}
    if namespace:
        metadata["namespace"] = namespace
    return {"kind": kind, "apiVersion": "v1", "metadata": metadata, **fields}


def container(name="app", **overrides):
    return {"name": name, "image": "registry.example.invalid/client/app:v1", "resources": {
        "requests": {"cpu": "250m", "memory": "256Mi"}, "limits": {"memory": "512Mi"}},
        "readinessProbe": {"httpGet": {"path": "/ready", "port": 8080}},
        "livenessProbe": {"httpGet": {"path": "/live", "port": 8080}},
        "ports": [{"containerPort": 8080}], "securityContext": {
            "privileged": False, "allowPrivilegeEscalation": False, "runAsNonRoot": True}, **overrides}


def fixture(engine):
    config = engine.validate_config("")
    raw_cluster = {"id": CLUSTER_ID, "name": "aks-client-lab", "type": "Microsoft.ContainerService/managedClusters",
                   "location": "example-region", "sku": {"name": "Base", "tier": "Standard"},
                   "identity": {"type": "UserAssigned"}, "properties": {
        "currentKubernetesVersion": "1.35.7", "powerState": {"code": "Running"}, "provisioningState": "Succeeded",
        "nodeResourceGroup": "rg-client-nodes", "enableRBAC": True, "disableLocalAccounts": True,
        "aadProfile": {"managed": True, "enableAzureRBAC": True}, "fqdn": "aks-client.example.azmk8s.io",
        "apiServerAccessProfile": {"enablePrivateCluster": False, "authorizedIPRanges": ["192.0.2.0/24"]},
        "securityProfile": {"workloadIdentity": {"enabled": True}, "defender": {"securityMonitoring": {"enabled": True}}},
        "oidcIssuerProfile": {"enabled": True}, "networkProfile": {"networkPlugin": "azure", "networkPluginMode": "overlay",
            "networkDataplane": "cilium", "networkPolicy": "cilium", "loadBalancerSku": "standard"},
        "autoUpgradeProfile": {"upgradeChannel": "stable", "nodeOSUpgradeChannel": "NodeImage"},
        "addonProfiles": {"azurepolicy": {"enabled": True}},
    }}
    cluster = engine.normalize_cluster(raw_cluster, "arm_cluster", REFERENCE, config)
    pools = []
    for name, mode in (("system", "System"), ("apps", "User")):
        pools.append(engine.normalize_pool({"id": CLUSTER_ID + "/agentPools/" + name, "name": name,
            "type": "Microsoft.ContainerService/managedClusters/agentPools", "properties": {
                "mode": mode, "vmSize": "Standard_D4s_v5", "count": 3, "enableAutoScaling": mode == "User",
                "minCount": 2, "maxCount": 6, "availabilityZones": ["1", "2", "3"], "provisioningState": "Succeeded",
                "nodeTaints": ["CriticalAddonsOnly=true:NoSchedule"] if mode == "System" else [],
                "maxPods": 250, "osType": "Linux", "osDiskType": "Ephemeral", "currentOrchestratorVersion": "1.35.7"}},
            "arm_node_pools", REFERENCE, config))
    inventory = {key: [] for key in engine.KUBE_PATHS}
    inventory.update(node_pools=pools, workloads=[], related_resources=[], related_resource_index=[])
    namespace = api_object("Namespace", "client-apps")
    namespace["metadata"]["labels"] = {"pod-security.kubernetes.io/enforce": "restricted"}
    inventory["namespaces"] = [engine.normalize_kube(namespace, "namespaces", "kube_namespaces", REFERENCE, config)]
    deployment = api_object("Deployment", "frontend", "client-apps", spec={
        "replicas": 2, "template": {"metadata": {"labels": {"app": "frontend", "release": "v1"}},
                                  "spec": {"containers": [container()]}}}, status={"readyReplicas": 2})
    inventory["deployments"] = [engine.normalize_kube(deployment, "deployments", "kube_deployments", REFERENCE, config)]
    inventory["workloads"] = list(inventory["deployments"])
    service = api_object("Service", "frontend", "client-apps", spec={"type": "ClusterIP", "selector": {"app": "frontend"}, "ports": [{"port": 80, "protocol": "TCP"}]})
    inventory["services"] = [engine.normalize_kube(service, "services", "kube_services", REFERENCE, config)]
    pdb = api_object("PodDisruptionBudget", "frontend", "client-apps", spec={"selector": {"matchLabels": {"app": "frontend"}}, "minAvailable": 1})
    inventory["pdbs"] = [engine.normalize_kube(pdb, "pdbs", "kube_pdbs", REFERENCE, config)]
    policy = api_object("NetworkPolicy", "frontend", "client-apps", spec={"podSelector": {"matchLabels": {"app": "frontend"}},
                                                                       "policyTypes": ["Ingress"], "ingress": []})
    inventory["network_policies"] = [engine.normalize_kube(policy, "network_policies", "kube_network_policies", REFERENCE, config)]
    node = api_object("Node", "client-node-1", status={"capacity": {"cpu": "4", "memory": "16Gi"}, "allocatable": {"cpu": "3800m", "memory": "15Gi"}})
    node["metadata"]["labels"] = {"kubernetes.azure.com/agentpool": "apps"}
    inventory["nodes"] = [engine.normalize_kube(node, "nodes", "kube_nodes", REFERENCE, config)]
    rs = api_object("ReplicaSet", "frontend-revision", "client-apps")
    rs["metadata"]["ownerReferences"] = [{"kind": "Deployment", "name": "frontend", "uid": deployment["metadata"]["uid"], "controller": True}]
    inventory["replicasets"] = [engine.normalize_kube(rs, "replicasets", "kube_replicasets", REFERENCE, config)]
    pod = api_object("Pod", "frontend-instance", "client-apps", spec={"nodeName": "client-node-1", "containers": [container()]}, status={"phase": "Running"})
    pod["metadata"]["ownerReferences"] = [{"kind": "ReplicaSet", "name": "frontend-revision", "uid": rs["metadata"]["uid"], "controller": True}]
    inventory["pods"] = [engine.normalize_kube(pod, "pods", "kube_pods", REFERENCE, config)]
    nm = api_object("NodeMetrics", "client-node-1", timestamp=REFERENCE, window="30s", usage={"cpu": "100000000n", "memory": "256Mi"})
    pm = api_object("PodMetrics", "frontend-instance", "client-apps", timestamp=REFERENCE, window="30s",
                    containers=[{"name": "app", "usage": {"cpu": "10000000n", "memory": "64Mi"}}])
    inventory["node_metrics"] = [engine.normalize_kube(nm, "node_metrics", "kube_node_metrics", REFERENCE, config)]
    inventory["pod_metrics"] = [engine.normalize_kube(pm, "pod_metrics", "kube_pod_metrics", REFERENCE, config)]
    sources = [engine.source_receipt("arm_cluster", REFERENCE, records=1), engine.source_receipt("arm_node_pools", REFERENCE, records=2),
               engine.source_receipt("arm_related_inventory", REFERENCE),
               engine.source_receipt("arm_regional_versions", REFERENCE, records=1),
               engine.source_receipt("arm_upgrade_profile", REFERENCE, records=1),
               engine.source_receipt("arm_maintenance", REFERENCE), engine.source_receipt("arm_diagnostics", REFERENCE),
               engine.source_receipt("arm_advisor", REFERENCE),
               engine.source_receipt("azure_cost", REFERENCE, "not_configured")]
    sources.extend(engine.source_receipt("kube_" + key, REFERENCE, records=len(inventory[key])) for key in engine.KUBE_PATHS)
    return {"cluster": cluster, "inventory": inventory, "sources": sources, "requirements": {},
            "regional_versions": [{"id": "1.35", "version": "1.35", "patch_versions": {"1.35.7": {"upgrades": []}}}],
            "upgrade_profile": {"version": "1.35.7", "upgrades": []}, "arm_maintenance": [], "arm_diagnostics": [], "advisor": [], "cost_rows": []}


class ScriptedReader:
    def __init__(self, responses):
        self.responses, self.calls, self.allowed = list(responses), [], []

    def allow(self, url, method="GET"):
        self.allowed.append((method, url))
        return url

    def request(self, method, url, source, **kwargs):
        self.calls.append((method, url, source, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected network read in offline test.")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return json.loads(json.dumps(value))
