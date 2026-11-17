"""Permanently SIMULATED architecture/multi-cluster fixture, never runtime data."""

import copy

from support import CLUSTER_ID, REFERENCE, SUBSCRIPTION, api_object, fixture


SECOND_NAME = "aks-client-small"
SECOND_ID = CLUSTER_ID.rsplit("/", 1)[0] + "/" + SECOND_NAME


def configured_engine(engine):
    engine.APPROVED_CLUSTERS[SECOND_NAME] = copy.deepcopy(engine.APPROVED_CLUSTERS["aks-client-lab"])
    return engine


def architecture_fixture(engine):
    raw = fixture(engine)
    config = engine.validate_config("")
    prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-client-nodes/providers/"
    ids = {
        "vnet": prefix + "Microsoft.Network/virtualNetworks/client-vnet",
        "subnet": prefix + "Microsoft.Network/virtualNetworks/client-vnet/subnets/aks",
        "nsg": prefix + "Microsoft.Network/networkSecurityGroups/client-nsg",
        "vmss": prefix + "Microsoft.Compute/virtualMachineScaleSets/client-vmss",
        "pip": prefix + "Microsoft.Network/publicIPAddresses/client-public-ip",
        "elb": prefix + "Microsoft.Network/loadBalancers/client-public-lb",
        "ilb": prefix + "Microsoft.Network/loadBalancers/client-private-lb",
        "disk": prefix + "Microsoft.Compute/disks/client-pv-disk",
        "registry": prefix + "Microsoft.ContainerRegistry/registries/clientregistry",
    }
    assets = []
    def resource(key, kind, properties, **fields):
        source = "arm_resource_" + str(len(assets) + 1)
        item = {"id": ids[key], "name": ids[key].split("/")[-1], "type": kind, "location": "example-region",
                "properties": {"provisioningState": "Succeeded", **properties}, **fields}
        assets.append(engine.normalize_resource(item, source, REFERENCE, config,
                                                {"type": "operator_scoped", "source_id": "configuration"}))
        raw["sources"].append(engine.source_receipt(source, REFERENCE, records=1, resource_id=ids[key]))
    resource("vnet", "Microsoft.Network/virtualNetworks", {"subnets": [{"id": ids["subnet"]}], "addressSpace": {"addressPrefixes": ["10.10.0.0/16"]}})
    resource("subnet", "Microsoft.Network/virtualNetworks/subnets", {"addressPrefix": "10.10.1.0/24", "networkSecurityGroup": {"id": ids["nsg"]}})
    resource("nsg", "Microsoft.Network/networkSecurityGroups", {"securityRules": []})
    backend = ids["elb"] + "/backendAddressPools/nodes"
    resource("vmss", "Microsoft.Compute/virtualMachineScaleSets", {"virtualMachineProfile": {"networkProfile": {
        "networkInterfaceConfigurations": [{"properties": {"networkSecurityGroup": {"id": ids["nsg"]},
            "ipConfigurations": [{"properties": {"subnet": {"id": ids["subnet"]}, "loadBalancerBackendAddressPools": [{"id": backend}]}}]}}]}}},
        sku={"name": "Standard_D4pls_v5", "capacity": 2},
        tags={"aks-managed-poolName": "apps", "aks-managed-cluster-name": "aks-client-lab"})
    resource("pip", "Microsoft.Network/publicIPAddresses", {"ipAddress": "192.0.2.10", "publicIPAllocationMethod": "Static",
                                                            "ipConfiguration": {"id": ids["elb"] + "/frontendIPConfigurations/public"}})
    for key, frontend in (
        ("elb", {"publicIPAddress": {"id": ids["pip"]}}),
        ("ilb", {"privateIPAddress": "10.10.1.10", "subnet": {"id": ids["subnet"]}}),
    ):
        frontend_id = ids[key] + "/frontendIPConfigurations/frontend"
        pool_id = ids[key] + "/backendAddressPools/nodes"
        probe_id = ids[key] + "/probes/http"
        resource(key, "Microsoft.Network/loadBalancers", {
            "frontendIPConfigurations": [{"id": frontend_id, "name": "frontend", "properties": frontend}],
            "backendAddressPools": [{"id": pool_id, "name": "nodes", "properties": {}}],
            "probes": [{"id": probe_id, "name": "http", "properties": {"protocol": "Http", "port": 30080, "requestPath": "/ready"}}],
            "loadBalancingRules": [{"id": ids[key] + "/loadBalancingRules/http", "name": "http", "properties": {
                "frontendIPConfiguration": {"id": frontend_id}, "backendAddressPool": {"id": pool_id}, "probe": {"id": probe_id},
                "protocol": "Tcp", "frontendPort": 80, "backendPort": 30080}}],
        }, sku={"name": "Standard"})
    resource("disk", "Microsoft.Compute/disks", {"diskState": "Attached", "diskSizeGB": 32}, managedBy=ids["vmss"])
    resource("registry", "Microsoft.ContainerRegistry/registries", {"loginServer": "registry.example.invalid", "publicNetworkAccess": "Disabled"})
    principal = "44444444-4444-4444-8444-444444444444"
    raw["cluster"]["identity"]["kubelet_principal_id"] = principal
    source = "arm_registry_roles_1"
    raw["registry_role_assignments"] = [engine.normalize_registry_role({
        "id": ids["registry"] + "/providers/Microsoft.Authorization/roleAssignments/55555555-5555-4555-8555-555555555555",
        "properties": {"scope": ids["registry"], "principalId": principal,
            "roleDefinitionId": "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d",
            "condition": "SIMULATED-condition-text-not-exported"}},
        source, REFERENCE, config, ids["registry"], principal)]
    raw["sources"].append(engine.source_receipt(source, REFERENCE, records=1, resource_id=ids["registry"]))
    raw["inventory"]["related_resources"] = assets
    raw["inventory"]["node_pools"][1]["vnet_subnet_id"] = ids["subnet"]
    raw["inventory"]["nodes"][0]["provider_id"] = "azure://" + ids["vmss"] + "/virtualMachines/0"
    services = []
    for name, internal, address in (("public-frontend", "false", "192.0.2.10"), ("private-frontend", "true", "10.10.1.10")):
        item = api_object("Service", name, "client-apps",
                          spec={"type": "LoadBalancer", "selector": {"app": "frontend"},
                                "ports": [{"name": "http", "port": 80, "targetPort": 8080, "nodePort": 30080, "protocol": "TCP"}]},
                          status={"loadBalancer": {"ingress": [{"ip": address}]}})
        item["metadata"]["annotations"] = {"service.beta.kubernetes.io/azure-load-balancer-internal": internal,
                                           "unrelated-secret": "SIMULATED-EXCLUDED"}
        services.append(engine.normalize_kube(item, "services", "kube_services", REFERENCE, config))
    raw["inventory"]["services"] = services
    pvc_item = api_object("PersistentVolumeClaim", "frontend-data", "client-apps",
                          spec={"volumeName": "frontend-volume", "storageClassName": "managed"},
                          status={"phase": "Bound"})
    pv_item = api_object("PersistentVolume", "frontend-volume", spec={
        "storageClassName": "managed", "csi": {"driver": "disk.csi.azure.com", "volumeHandle": ids["disk"]},
        "claimRef": {"name": "frontend-data", "namespace": "client-apps", "uid": pvc_item["metadata"]["uid"]}},
        status={"phase": "Bound"})
    raw["inventory"]["pvcs"] = [engine.normalize_kube(pvc_item, "pvcs", "kube_pvcs", REFERENCE, config)]
    raw["inventory"]["pvs"] = [engine.normalize_kube(pv_item, "pvs", "kube_pvs", REFERENCE, config)]
    raw["inventory"]["workloads"][0]["pvc_names"] = ["frontend-data"]
    for source in raw["sources"]:
        collection = source["id"].removeprefix("kube_")
        if collection in raw["inventory"]:
            source["records"] = len(raw["inventory"][collection])
    return raw


def second_raw(first):
    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str):
            return value.replace(CLUSTER_ID, SECOND_ID).replace("aks-client-lab", SECOND_NAME)
        return value
    return replace(first)


def document(engine, failed_second=False):
    configured_engine(engine)
    raw = architecture_fixture(engine)
    first = engine.finish_snapshot(raw, REFERENCE, "SIMULATED", "LAB")
    second = engine.finish_snapshot(second_raw(raw), REFERENCE, "SIMULATED", "LAB")
    _, roster = engine.selection_configs("", "aks-client-lab," + SECOND_NAME)
    runs = [{"cluster_id": CLUSTER_ID, "cluster_name": "aks-client-lab", "reference_utc": REFERENCE,
             "status": "partial", "error": None, "snapshot": first},
            {"cluster_id": SECOND_ID, "cluster_name": SECOND_NAME, "reference_utc": REFERENCE,
             "status": "error" if failed_second else "partial",
             "error": {"code": "access_denied", "source": "arm_cluster", "http_status": 403,
                       "message": "SIMULATED primary cluster read denied."} if failed_second else None,
             "snapshot": None if failed_second else second}]
    return engine.multi_snapshot(runs, REFERENCE, roster)
