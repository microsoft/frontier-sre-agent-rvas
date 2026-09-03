resource "azurerm_resource_group" "sample_food" {
  name     = local.sample_food_names.resource_group
  location = local.sample_food_location
  tags     = local.sample_food_tags
}

resource "azurerm_virtual_network" "sample_food" {
  name                = local.sample_food_names.vnet
  location            = azurerm_resource_group.sample_food.location
  resource_group_name = azurerm_resource_group.sample_food.name
  address_space       = local.sample_food_address_spaces
  tags                = local.sample_food_tags
}

resource "azurerm_subnet" "sample_food_container_apps" {
  name                 = local.sample_food_names.container_apps_subnet
  resource_group_name  = azurerm_resource_group.sample_food.name
  virtual_network_name = azurerm_virtual_network.sample_food.name
  address_prefixes     = ["10.40.0.0/21"]
  # Secure-by-default: pin to false to match the live state and prevent Terraform
  # from re-enabling Azure's legacy default outbound access (provider default true).
  # The Container Apps environment provides its own outbound path, so disabling
  # default egress on this delegated subnet is supported and is the running config.
  default_outbound_access_enabled = false

  delegation {
    name = "container-apps-environment"

    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "sample_food_probe" {
  name                            = local.sample_food_names.probe_subnet
  resource_group_name             = azurerm_resource_group.sample_food.name
  virtual_network_name            = azurerm_virtual_network.sample_food.name
  address_prefixes                = ["10.40.8.0/24"]
  default_outbound_access_enabled = false
}

resource "azurerm_virtual_network_peering" "hub_to_sample_food" {
  name                      = "peer-hub-to-food"
  resource_group_name       = azurerm_resource_group.hub.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.sample_food.id
  allow_forwarded_traffic   = true

  depends_on = [
    azurerm_subnet.sample_food_container_apps,
    azurerm_subnet.sample_food_probe,
  ]
}

resource "azurerm_virtual_network_peering" "sample_food_to_hub" {
  name                      = "peer-food-to-hub"
  resource_group_name       = azurerm_resource_group.sample_food.name
  virtual_network_name      = azurerm_virtual_network.sample_food.name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
  allow_forwarded_traffic   = true

  depends_on = [
    azurerm_subnet.hub_mgmt,
    azurerm_subnet.hub_nva,
    azurerm_subnet.hub_firewall,
    azurerm_subnet.hub_firewall_management,
    azurerm_subnet.hub_bastion,
  ]
}

resource "azurerm_route_table" "sample_food_probe_to_firewall" {
  name                = local.sample_food_names.route_table
  location            = azurerm_resource_group.sample_food.location
  resource_group_name = azurerm_resource_group.sample_food.name
  tags                = local.sample_food_tags
}

resource "azurerm_route" "sample_food_probe_default_egress_via_firewall" {
  name                   = "Default-Food-Probe-Internet-Via-Firewall"
  resource_group_name    = azurerm_resource_group.sample_food.name
  route_table_name       = azurerm_route_table.sample_food_probe_to_firewall.name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

resource "azurerm_subnet_route_table_association" "sample_food_probe" {
  subnet_id      = azurerm_subnet.sample_food_probe.id
  route_table_id = azurerm_route_table.sample_food_probe_to_firewall.id
}