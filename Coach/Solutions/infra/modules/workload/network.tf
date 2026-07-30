resource "azurerm_virtual_network" "hub" {
  name                = "vnet-hub"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  address_space       = local.demo_address_spaces.hub
  tags                = local.resource_tags
}

resource "azurerm_virtual_network" "spoke_app" {
  name                = "vnet-app"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  address_space       = local.demo_address_spaces.spoke_app
  tags                = local.resource_tags
}

resource "azurerm_virtual_network" "spoke_data" {
  name                = "vnet-data"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  address_space       = local.demo_address_spaces.spoke_data
  tags                = local.resource_tags
}

resource "azurerm_subnet" "hub_mgmt" {
  name                            = "snet-mgmt"
  resource_group_name             = azurerm_resource_group.hub.name
  virtual_network_name            = azurerm_virtual_network.hub.name
  address_prefixes                = [local.demo_subnets.hub_mgmt]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "hub_nva" {
  name                            = "snet-nva"
  resource_group_name             = azurerm_resource_group.hub.name
  virtual_network_name            = azurerm_virtual_network.hub.name
  address_prefixes                = [local.demo_subnets.hub_nva]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "hub_firewall" {
  name                            = "AzureFirewallSubnet"
  resource_group_name             = azurerm_resource_group.hub.name
  virtual_network_name            = azurerm_virtual_network.hub.name
  address_prefixes                = [local.demo_subnets.hub_firewall]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "hub_firewall_management" {
  name                            = "AzureFirewallManagementSubnet"
  resource_group_name             = azurerm_resource_group.hub.name
  virtual_network_name            = azurerm_virtual_network.hub.name
  address_prefixes                = [local.demo_subnets.hub_firewall_mgmt]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "hub_bastion" {
  name                 = "AzureBastionSubnet"
  resource_group_name  = azurerm_resource_group.hub.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [local.demo_subnets.hub_bastion]
  # Secure-by-default: pin to false to match the live state and prevent Terraform
  # from re-enabling Azure's legacy default outbound access (provider default true).
  # Azure Bastion supplies its own managed outbound, so disabling default egress here
  # is supported and is the running configuration.
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "app_client" {
  name                            = "snet-client"
  resource_group_name             = azurerm_resource_group.spoke_web_api.name
  virtual_network_name            = azurerm_virtual_network.spoke_app.name
  address_prefixes                = [local.demo_subnets.app_client]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "app_web" {
  name                            = "snet-web"
  resource_group_name             = azurerm_resource_group.spoke_web_api.name
  virtual_network_name            = azurerm_virtual_network.spoke_app.name
  address_prefixes                = [local.demo_subnets.app_web]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "data_api" {
  name                            = "snet-api"
  resource_group_name             = azurerm_resource_group.spoke_data.name
  virtual_network_name            = azurerm_virtual_network.spoke_data.name
  address_prefixes                = [local.demo_subnets.data_api]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "data_db" {
  name                            = "snet-db"
  resource_group_name             = azurerm_resource_group.spoke_data.name
  virtual_network_name            = azurerm_virtual_network.spoke_data.name
  address_prefixes                = [local.demo_subnets.data_db]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "data_privatelink" {
  name                              = "snet-privatelink"
  resource_group_name               = azurerm_resource_group.spoke_data.name
  virtual_network_name              = azurerm_virtual_network.spoke_data.name
  address_prefixes                  = [local.demo_subnets.data_privatelink]
  default_outbound_access_enabled   = false
  private_endpoint_network_policies = "Disabled"
}

resource "azurerm_virtual_network_peering" "hub_to_app" {
  name                      = "peer-hub-to-app"
  resource_group_name       = azurerm_resource_group.hub.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.spoke_app.id
  allow_forwarded_traffic   = true
}

resource "azurerm_virtual_network_peering" "app_to_hub" {
  name                      = "peer-app-to-hub"
  resource_group_name       = azurerm_resource_group.spoke_web_api.name
  virtual_network_name      = azurerm_virtual_network.spoke_app.name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
  allow_forwarded_traffic   = true
}

resource "azurerm_virtual_network_peering" "hub_to_data" {
  name                      = "peer-hub-to-data"
  resource_group_name       = azurerm_resource_group.hub.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = azurerm_virtual_network.spoke_data.id
  allow_forwarded_traffic   = true
}

resource "azurerm_virtual_network_peering" "data_to_hub" {
  name                      = "peer-data-to-hub"
  resource_group_name       = azurerm_resource_group.spoke_data.name
  virtual_network_name      = azurerm_virtual_network.spoke_data.name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
  allow_forwarded_traffic   = true
}

resource "azurerm_network_security_group" "app" {
  name                = "nsg-app"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  tags                = local.resource_tags

  security_rule {
    name                       = "AllowVnetInbound"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "AllowHttpFromVnet"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "8080"]
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "data" {
  name                = "nsg-data"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  tags                = local.resource_tags

  security_rule {
    name                       = "AllowAppToDataPorts"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["8080", "5432"]
    source_address_prefixes    = azurerm_virtual_network.spoke_app.address_space
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "hub" {
  name                = "nsg-hub"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  tags                = local.resource_tags

  security_rule {
    name                       = "AllowVnetInbound"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }
}

resource "azurerm_subnet_network_security_group_association" "app_client" {
  subnet_id                 = azurerm_subnet.app_client.id
  network_security_group_id = azurerm_network_security_group.app.id
}

resource "azurerm_subnet_network_security_group_association" "app_web" {
  subnet_id                 = azurerm_subnet.app_web.id
  network_security_group_id = azurerm_network_security_group.app.id
}

resource "azurerm_subnet_network_security_group_association" "data_api" {
  subnet_id                 = azurerm_subnet.data_api.id
  network_security_group_id = azurerm_network_security_group.data.id
}

resource "azurerm_subnet_network_security_group_association" "data_db" {
  subnet_id                 = azurerm_subnet.data_db.id
  network_security_group_id = azurerm_network_security_group.data.id
}

resource "azurerm_subnet_network_security_group_association" "hub_nva" {
  subnet_id                 = azurerm_subnet.hub_nva.id
  network_security_group_id = azurerm_network_security_group.hub.id
}

resource "azurerm_public_ip" "firewall" {
  name                = "pip-firewall"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.resource_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_public_ip" "firewall_management" {
  name                = "pip-firewall-mgmt"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.resource_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_public_ip" "bastion" {
  name                = "pip-bastion"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.resource_tags

  lifecycle {
    ignore_changes = [ip_tags, zones]
  }
}

resource "azurerm_bastion_host" "hub" {
  name                = "bas-hub"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  sku                 = "Basic"
  tags                = local.resource_tags

  ip_configuration {
    name                 = "configuration"
    subnet_id            = azurerm_subnet.hub_bastion.id
    public_ip_address_id = azurerm_public_ip.bastion.id
  }
}

resource "azurerm_firewall_policy" "hub" {
  name                     = "afwp-hub"
  location                 = azurerm_resource_group.hub.location
  resource_group_name      = azurerm_resource_group.hub.name
  sku                      = "Basic"
  threat_intelligence_mode = "Alert"
  tags                     = local.resource_tags
}

resource "azurerm_firewall_policy_rule_collection_group" "hub_demo" {
  name               = "afwrcg-demo"
  firewall_policy_id = azurerm_firewall_policy.hub.id
  priority           = 500

  network_rule_collection {
    name     = "allow-east-west-demo"
    priority = 100
    action   = "Allow"

    rule {
      name                  = "allow-all"
      protocols             = ["Any"]
      source_addresses      = ["*"]
      destination_addresses = ["*"]
      destination_ports     = ["*"]
    }
  }

  application_rule_collection {
    name     = "allow-public-demo-egress"
    priority = 200
    action   = "Allow"

    rule {
      name = "allow-microsoft-https"
      source_addresses = concat(
        local.demo_address_spaces.spoke_app,
        local.demo_address_spaces.spoke_data,
        local.sample_food_address_spaces
      )
      destination_fqdns = [
        "www.microsoft.com",
        "*.microsoft.com"
      ]

      protocols {
        type = "Https"
        port = 443
      }
    }
  }
}

resource "azurerm_firewall" "hub" {
  name                = "afw-hub"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  sku_name            = "AZFW_VNet"
  sku_tier            = "Basic"
  firewall_policy_id  = azurerm_firewall_policy.hub.id
  tags                = local.resource_tags

  ip_configuration {
    name                 = "configuration"
    subnet_id            = azurerm_subnet.hub_firewall.id
    public_ip_address_id = azurerm_public_ip.firewall.id
  }

  management_ip_configuration {
    name                 = "management"
    subnet_id            = azurerm_subnet.hub_firewall_management.id
    public_ip_address_id = azurerm_public_ip.firewall_management.id
  }
}

resource "azurerm_route_table" "app_to_nva" {
  name                = "rt-app-to-nva"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  tags                = local.resource_tags
}

resource "azurerm_route_table" "data_to_nva" {
  name                = "rt-data-to-nva"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  tags                = local.resource_tags
}

resource "azurerm_route" "app_to_data_via_firewall" {
  name                   = "Default-App-To-Data-Via-Firewall"
  resource_group_name    = azurerm_resource_group.spoke_web_api.name
  route_table_name       = azurerm_route_table.app_to_nva.name
  address_prefix         = local.demo_address_spaces.spoke_data[0]
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

resource "azurerm_route" "app_default_egress_via_firewall" {
  name                   = "Default-App-Internet-Via-Firewall"
  resource_group_name    = azurerm_resource_group.spoke_web_api.name
  route_table_name       = azurerm_route_table.app_to_nva.name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

resource "azurerm_route" "data_to_app_via_firewall" {
  name                   = "Default-Data-To-App-Via-Firewall"
  resource_group_name    = azurerm_resource_group.spoke_data.name
  route_table_name       = azurerm_route_table.data_to_nva.name
  address_prefix         = local.demo_address_spaces.spoke_app[0]
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

resource "azurerm_route" "data_default_egress_via_firewall" {
  name                   = "Default-Data-Internet-Via-Firewall"
  resource_group_name    = azurerm_resource_group.spoke_data.name
  route_table_name       = azurerm_route_table.data_to_nva.name
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

resource "azurerm_subnet_route_table_association" "app_client" {
  subnet_id      = azurerm_subnet.app_client.id
  route_table_id = azurerm_route_table.app_to_nva.id
}

resource "azurerm_subnet_route_table_association" "app_web" {
  subnet_id      = azurerm_subnet.app_web.id
  route_table_id = azurerm_route_table.app_to_nva.id
}

resource "azurerm_subnet_route_table_association" "data_api" {
  subnet_id      = azurerm_subnet.data_api.id
  route_table_id = azurerm_route_table.data_to_nva.id
}

resource "azurerm_subnet_route_table_association" "data_db" {
  subnet_id      = azurerm_subnet.data_db.id
  route_table_id = azurerm_route_table.data_to_nva.id
}