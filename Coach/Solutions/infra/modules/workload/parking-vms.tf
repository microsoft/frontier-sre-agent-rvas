# ─── Madrid — Windows Server 2022 ─────────────────────────────────────────────

resource "azurerm_public_ip" "madrid" {
  count = var.create_parking_public_ips && var.deploy_madrid_vm ? 1 : 0

  name                = "pip-parking-madrid"
  location            = azurerm_resource_group.parking_madrid.location
  resource_group_name = azurerm_resource_group.parking_madrid.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.resource_tags

}

resource "azurerm_network_interface" "madrid" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                = "nic-parking-madrid"
  location            = azurerm_resource_group.parking_madrid.location
  resource_group_name = azurerm_resource_group.parking_madrid.name
  tags                = local.resource_tags


  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.data_api.id
    private_ip_address_allocation = "Dynamic"

    public_ip_address_id = var.create_parking_public_ips ? azurerm_public_ip.madrid[0].id : null
  }
}

resource "azurerm_windows_virtual_machine" "madrid" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                = "vm-parking-madrid"
  location            = azurerm_resource_group.parking_madrid.location
  resource_group_name = azurerm_resource_group.parking_madrid.name
  size                = "Standard_B2s"
  computer_name       = "madrid-api"
  admin_username      = var.vm_admin_username
  admin_password      = var.vm_admin_password
  network_interface_ids = [
    azurerm_network_interface.madrid[0].id
  ]
  tags = local.resource_tags


  patch_mode = "AutomaticByOS"

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    name                 = "osdisk-parking-madrid"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-azure-edition-smalldisk"
    version   = "latest"
  }

  boot_diagnostics {}

  # Ordering guard: egress through the hub firewall must be established before
  # provisioning so that the Azure Monitor Windows Agent can reach Azure Monitor.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]
}

resource "azurerm_virtual_machine_extension" "madrid_ama" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                       = "AzureMonitorWindowsAgent"
  virtual_machine_id         = azurerm_windows_virtual_machine.madrid[0].id
  publisher                  = "Microsoft.Azure.Monitor"
  type                       = "AzureMonitorWindowsAgent"
  type_handler_version       = "1.0"
  auto_upgrade_minor_version = true
  automatic_upgrade_enabled  = true
  tags                       = local.resource_tags

}

# ─── Paris — Ubuntu Server 22.04 LTS ──────────────────────────────────────────

resource "azurerm_public_ip" "paris" {
  count = var.create_parking_public_ips && var.deploy_paris_vm ? 1 : 0

  name                = "pip-parking-paris"
  location            = azurerm_resource_group.parking_paris.location
  resource_group_name = azurerm_resource_group.parking_paris.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.resource_tags

}

resource "azurerm_network_interface" "paris" {
  count = var.deploy_paris_vm ? 1 : 0

  name                = "nic-parking-paris"
  location            = azurerm_resource_group.parking_paris.location
  resource_group_name = azurerm_resource_group.parking_paris.name
  tags                = local.resource_tags


  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.data_api.id
    private_ip_address_allocation = "Dynamic"

    public_ip_address_id = var.create_parking_public_ips ? azurerm_public_ip.paris[0].id : null
  }
}

resource "azurerm_linux_virtual_machine" "paris" {
  count = var.deploy_paris_vm ? 1 : 0

  name                = "vm-parking-paris"
  location            = azurerm_resource_group.parking_paris.location
  resource_group_name = azurerm_resource_group.parking_paris.name
  size                = "Standard_B2s"
  admin_username      = var.vm_admin_username
  network_interface_ids = [
    azurerm_network_interface.paris[0].id
  ]
  admin_password                  = var.vm_admin_password
  disable_password_authentication = false
  tags                            = local.resource_tags


  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    name                 = "osdisk-parking-paris"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}

  # Ordering guard: internet egress through the hub firewall must be established
  # before provisioning so that the CustomScript extension can run apt-get.
  depends_on = [
    azurerm_firewall.hub,
    azurerm_firewall_policy_rule_collection_group.hub_demo,
    azurerm_route.data_default_egress_via_firewall,
    azurerm_route.data_to_app_via_firewall,
    azurerm_subnet_route_table_association.data_api,
    azurerm_subnet_route_table_association.data_db,
    azurerm_virtual_network_peering.hub_to_data,
    azurerm_virtual_network_peering.data_to_hub,
  ]
}

resource "azurerm_virtual_machine_extension" "paris_ama" {
  count = var.deploy_paris_vm ? 1 : 0

  name                       = "AzureMonitorLinuxAgent"
  virtual_machine_id         = azurerm_linux_virtual_machine.paris[0].id
  publisher                  = "Microsoft.Azure.Monitor"
  type                       = "AzureMonitorLinuxAgent"
  type_handler_version       = "1.0"
  auto_upgrade_minor_version = true
  automatic_upgrade_enabled  = true
  tags                       = local.resource_tags

}

resource "azurerm_virtual_machine_extension" "paris_node_setup" {
  count = var.deploy_paris_vm ? 1 : 0

  name                       = "CustomScript"
  virtual_machine_id         = azurerm_linux_virtual_machine.paris[0].id
  publisher                  = "Microsoft.Azure.Extensions"
  type                       = "CustomScript"
  type_handler_version       = "2.1"
  auto_upgrade_minor_version = true
  tags                       = local.resource_tags


  settings = jsonencode({
    script = base64encode(<<-SCRIPT
      #!/bin/bash
      set -e

      apt-get update
      apt-get install -y ca-certificates curl gnupg rsyslog

      mkdir -p /etc/apt/keyrings
      curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor --batch --yes -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null || true
      echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" \
        | tee /etc/apt/sources.list.d/nodesource.list

      apt-get update
      apt-get install -y nodejs

      node --version
      npm --version
    SCRIPT
    )
  })

  depends_on = [azurerm_virtual_machine_extension.paris_ama]
}
