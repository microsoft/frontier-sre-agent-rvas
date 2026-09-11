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

  name                = "nic-parking-madrid-vnet"
  location            = azurerm_resource_group.parking_madrid.location
  resource_group_name = azurerm_resource_group.parking_madrid.name
  tags                = local.resource_tags

  lifecycle {
    create_before_destroy = true
  }

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.parking_vms.id
    private_ip_address_allocation = "Dynamic"

    public_ip_address_id = var.create_parking_public_ips ? azurerm_public_ip.madrid[0].id : null
  }
}

resource "azurerm_windows_virtual_machine" "madrid" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                = "vm-parking-madrid"
  location            = azurerm_resource_group.parking_madrid.location
  resource_group_name = azurerm_resource_group.parking_madrid.name
  size                = "Standard_B2s_v2"
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
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-azure-edition-smalldisk"
    version   = "latest"
  }

  boot_diagnostics {}

  # Ensure independent Parking VNet egress is ready before the VM agent starts.
  depends_on = [
    azurerm_nat_gateway_public_ip_association.parking,
    azurerm_subnet_nat_gateway_association.parking_vms,
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

resource "azurerm_virtual_machine_extension" "madrid_api_setup" {
  count = var.deploy_madrid_vm ? 1 : 0

  name                       = "MadridParkingApiSetup"
  virtual_machine_id         = azurerm_windows_virtual_machine.madrid[0].id
  publisher                  = "Microsoft.Compute"
  type                       = "CustomScriptExtension"
  type_handler_version       = "1.10"
  auto_upgrade_minor_version = true
  tags                       = local.resource_tags

  settings = jsonencode({
    commandToExecute = "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand ${textencodebase64(templatefile("${path.module}/templates/windows-gzip-bootstrap.ps1.tftpl", {
      script_base64gzip = base64gzip(templatefile("${path.module}/templates/madrid-parking-api-setup.ps1.tftpl", {
        source_base_url   = "https://raw.githubusercontent.com/microsoft/frontier-sre-agent-rvas/main/Student/Resources/parking-manager/backend"
        chaos_control_url = "https://${azurerm_container_app.chaos_control.ingress[0].fqdn}"
      }))
    }), "UTF-16LE")}"
  })

  depends_on = [azurerm_virtual_machine_extension.madrid_ama]
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

  name                = "nic-parking-paris-vnet"
  location            = azurerm_resource_group.parking_paris.location
  resource_group_name = azurerm_resource_group.parking_paris.name
  tags                = local.resource_tags

  lifecycle {
    create_before_destroy = true
  }

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = azurerm_subnet.parking_vms.id
    private_ip_address_allocation = "Dynamic"

    public_ip_address_id = var.create_parking_public_ips ? azurerm_public_ip.paris[0].id : null
  }
}

resource "azurerm_linux_virtual_machine" "paris" {
  count = var.deploy_paris_vm ? 1 : 0

  name                = "vm-parking-paris"
  location            = azurerm_resource_group.parking_paris.location
  resource_group_name = azurerm_resource_group.parking_paris.name
  size                = "Standard_B2s_v2"
  admin_username      = var.vm_admin_username
  network_interface_ids = [
    azurerm_network_interface.paris[0].id
  ]
  admin_password                  = var.vm_admin_password
  disable_password_authentication = false
  encryption_at_host_enabled      = false
  secure_boot_enabled             = false
  vtpm_enabled                    = false
  tags                            = local.resource_tags


  patch_mode                                             = "AutomaticByPlatform"
  patch_assessment_mode                                  = "AutomaticByPlatform"
  bypass_platform_safety_checks_on_user_schedule_enabled = true

  identity {
    identity_ids = []
    type         = "SystemAssigned"
  }

  os_disk {
    name                 = "osdisk-parking-paris"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  boot_diagnostics {}

  # Ensure independent Parking VNet egress is ready before CustomScript runs apt-get.
  depends_on = [
    azurerm_nat_gateway_public_ip_association.parking,
    azurerm_subnet_nat_gateway_association.parking_vms,
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
  provision_after_extensions = []
  tags                       = local.resource_tags

}

resource "azurerm_virtual_machine_extension" "paris_node_setup" {
  count = var.deploy_paris_vm ? 1 : 0

  name                       = "ParisParkingApiSetup"
  virtual_machine_id         = azurerm_linux_virtual_machine.paris[0].id
  publisher                  = "Microsoft.Azure.Extensions"
  type                       = "CustomScript"
  type_handler_version       = "2.1"
  auto_upgrade_minor_version = true
  automatic_upgrade_enabled  = false
  provision_after_extensions = []
  tags                       = local.resource_tags


  settings = jsonencode({
    script = base64encode(templatefile("${path.module}/templates/paris-parking-api-setup.sh.tftpl", {
      server_js_base64        = filebase64("${path.module}/../../../../../Student/Resources/parking-manager/backend/paris-parking-api/server.js")
      logger_js_base64        = filebase64("${path.module}/../../../../../Student/Resources/parking-manager/backend/paris-parking-api/syslogLogger.js")
      package_json_base64     = filebase64("${path.module}/../../../../../Student/Resources/parking-manager/backend/paris-parking-api/package.json")
      chaos_middleware_base64 = filebase64("${path.module}/../../../../../Student/Resources/parking-manager/backend/shared/chaosMiddleware.js")
      chaos_control_url       = "https://${azurerm_container_app.chaos_control.ingress[0].fqdn}"
    }))
  })

  depends_on = [azurerm_virtual_machine_extension.paris_ama]
}
