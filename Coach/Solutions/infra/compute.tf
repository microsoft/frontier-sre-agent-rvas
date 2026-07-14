resource "azurerm_network_interface" "client" {
  name                = "nic-client"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  tags                = local.demo_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.app_client.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.20.1.10"
  }
}

resource "azurerm_network_interface" "web" {
  count = 2

  name                = "nic-web-${count.index + 1}"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  tags                = local.demo_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.app_web.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.20.2.${10 + count.index}"
  }
}

resource "azurerm_network_interface" "api" {
  name                = "nic-api"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  tags                = local.demo_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.data_api.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.30.1.10"
  }
}

resource "azurerm_network_interface" "db" {
  name                = "nic-db"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  tags                = local.demo_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.data_db.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.30.2.10"
  }
}

resource "azurerm_network_interface" "nva" {
  name                           = "nic-nva"
  location                       = azurerm_resource_group.hub.location
  resource_group_name            = azurerm_resource_group.hub.name
  accelerated_networking_enabled = false
  ip_forwarding_enabled          = true
  tags                           = local.demo_tags

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.hub_nva.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.10.2.10"
  }
}

resource "azurerm_linux_virtual_machine" "client" {
  name                = "vm-client"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  size                = "Standard_B2s_v2"
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.client.id
  ]
  admin_password                  = "Use-A-Strong-Demo-Password-123!"
  disable_password_authentication = false
  custom_data                     = local.demo_client_cloud_init
  tags                            = local.demo_tags

  # Guest patch orchestration is set by the Azure platform after VM creation
  # (patch_mode + patch_assessment_mode = AutomaticByPlatform, bypass = true). Declared
  # here to keep desired state aligned with the live VM and remove the recurring
  # bypass_platform_safety_checks_on_user_schedule_enabled drift.
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  # Ordering guard: cloud-init runs apt-get at first boot and the only internet egress is
  # forced-tunneled through the hub firewall (subnets have default_outbound_access_enabled =
  # false = no implicit outbound). Create the VM only after the full governed-egress path
  # (firewall + allow rules + 0.0.0.0/0 routes + route-table associations + hub/spoke
  # peerings) exists, otherwise cloud-init package installs fail.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.app_default_egress_via_firewall,
    azurerm_route.app_to_data_via_firewall,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.app_client,
    azurerm_subnet_route_table_association.app_web,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_app,
    azurerm_virtual_network_peering.app_to_hub,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_linux_virtual_machine" "web" {
  count = 2

  name                = "vm-web-${count.index + 1}"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  size                = "Standard_B2s_v2"
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.web[count.index].id
  ]
  admin_password                  = "Use-A-Strong-Demo-Password-123!"
  disable_password_authentication = false
  custom_data                     = local.demo_web_cloud_init
  tags                            = local.demo_tags

  # Guest patch orchestration is set by the Azure platform after VM creation
  # (patch_mode + patch_assessment_mode = AutomaticByPlatform, bypass = true). Declared
  # here to keep desired state aligned with the live VM and remove the recurring
  # bypass_platform_safety_checks_on_user_schedule_enabled drift.
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  # Ordering guard: cloud-init runs apt-get at first boot and the only internet egress is
  # forced-tunneled through the hub firewall (subnets have default_outbound_access_enabled =
  # false = no implicit outbound). Create the VM only after the full governed-egress path
  # (firewall + allow rules + 0.0.0.0/0 routes + route-table associations + hub/spoke
  # peerings) exists, otherwise cloud-init package installs fail.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.app_default_egress_via_firewall,
    azurerm_route.app_to_data_via_firewall,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.app_client,
    azurerm_subnet_route_table_association.app_web,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_app,
    azurerm_virtual_network_peering.app_to_hub,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]

  # System-assigned identity required by Azure Monitor Agent (AMA) to authenticate
  # to the data collection rule and Log Analytics for the NGINX-down demo scenario.
  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_linux_virtual_machine" "api" {
  name                = "vm-api"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  size                = "Standard_B2s_v2"
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.api.id
  ]
  admin_password                  = "Use-A-Strong-Demo-Password-123!"
  disable_password_authentication = false
  custom_data                     = local.demo_web_cloud_init
  tags                            = local.demo_tags

  # Guest patch orchestration is set by the Azure platform after VM creation
  # (patch_mode + patch_assessment_mode = AutomaticByPlatform, bypass = true). Declared
  # here to keep desired state aligned with the live VM and remove the recurring
  # bypass_platform_safety_checks_on_user_schedule_enabled drift.
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  # Ordering guard: cloud-init runs apt-get at first boot and the only internet egress is
  # forced-tunneled through the hub firewall (subnets have default_outbound_access_enabled =
  # false = no implicit outbound). Create the VM only after the full governed-egress path
  # (firewall + allow rules + 0.0.0.0/0 routes + route-table associations + hub/spoke
  # peerings) exists, otherwise cloud-init package installs fail.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.app_default_egress_via_firewall,
    azurerm_route.app_to_data_via_firewall,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.app_client,
    azurerm_subnet_route_table_association.app_web,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_app,
    azurerm_virtual_network_peering.app_to_hub,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_linux_virtual_machine" "db" {
  name                = "vm-db"
  location            = azurerm_resource_group.spoke_data.location
  resource_group_name = azurerm_resource_group.spoke_data.name
  size                = "Standard_B2s_v2"
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.db.id
  ]
  admin_password                  = "Use-A-Strong-Demo-Password-123!"
  disable_password_authentication = false
  custom_data                     = local.demo_web_cloud_init
  tags                            = local.demo_tags

  # Guest patch orchestration is set by the Azure platform after VM creation
  # (patch_mode + patch_assessment_mode = AutomaticByPlatform, bypass = true). Declared
  # here to keep desired state aligned with the live VM and remove the recurring
  # bypass_platform_safety_checks_on_user_schedule_enabled drift.
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  # Ordering guard: cloud-init runs apt-get at first boot and the only internet egress is
  # forced-tunneled through the hub firewall (subnets have default_outbound_access_enabled =
  # false = no implicit outbound). Create the VM only after the full governed-egress path
  # (firewall + allow rules + 0.0.0.0/0 routes + route-table associations + hub/spoke
  # peerings) exists, otherwise cloud-init package installs fail.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.app_default_egress_via_firewall,
    azurerm_route.app_to_data_via_firewall,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.app_client,
    azurerm_subnet_route_table_association.app_web,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_app,
    azurerm_virtual_network_peering.app_to_hub,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_linux_virtual_machine" "nva" {
  name                = "vm-nva"
  location            = azurerm_resource_group.hub.location
  resource_group_name = azurerm_resource_group.hub.name
  size                = "Standard_B2s_v2"
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.nva.id
  ]
  admin_password                  = "Use-A-Strong-Demo-Password-123!"
  disable_password_authentication = false
  custom_data                     = local.demo_nva_cloud_init
  tags                            = local.demo_tags

  # Guest patch orchestration is set by the Azure platform after VM creation
  # (patch_mode + patch_assessment_mode = AutomaticByPlatform, bypass = true). Declared
  # here to keep desired state aligned with the live VM and remove the recurring
  # bypass_platform_safety_checks_on_user_schedule_enabled drift.
  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  # Ordering guard: cloud-init runs apt-get at first boot and internet egress in this lab is
  # forced-tunneled through the hub firewall (subnets have default_outbound_access_enabled =
  # false = no implicit outbound). Create the VM only after the full governed-egress path
  # (firewall + allow rules + 0.0.0.0/0 routes + route-table associations + hub/spoke
  # peerings) exists, otherwise cloud-init package installs fail.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.app_default_egress_via_firewall,
    azurerm_route.app_to_data_via_firewall,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.app_client,
    azurerm_subnet_route_table_association.app_web,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_app,
    azurerm_virtual_network_peering.app_to_hub,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}
}

resource "azurerm_lb" "internal_web" {
  name                = "lb-internal-web"
  location            = azurerm_resource_group.spoke_web_api.location
  resource_group_name = azurerm_resource_group.spoke_web_api.name
  sku                 = "Standard"
  tags                = local.demo_tags

  frontend_ip_configuration {
    name                          = "web-ilb"
    subnet_id                     = azurerm_subnet.app_web.id
    private_ip_address_allocation = "Static"
    private_ip_address            = "10.20.2.100"
  }
}

resource "azurerm_lb_backend_address_pool" "web" {
  loadbalancer_id = azurerm_lb.internal_web.id
  name            = "web-backend"
}

resource "azurerm_network_interface_backend_address_pool_association" "web" {
  count = 2

  network_interface_id    = azurerm_network_interface.web[count.index].id
  ip_configuration_name   = "ipconfig1"
  backend_address_pool_id = azurerm_lb_backend_address_pool.web.id
}

resource "azurerm_lb_probe" "web_http" {
  loadbalancer_id = azurerm_lb.internal_web.id
  name            = "http-probe"
  protocol        = "Http"
  request_path    = "/"
  port            = 80
}

resource "azurerm_lb_rule" "web_http" {
  loadbalancer_id                = azurerm_lb.internal_web.id
  name                           = "http"
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "web-ilb"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.web.id]
  probe_id                       = azurerm_lb_probe.web_http.id
}
