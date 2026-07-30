# Sample Food Ordering App Lab

The Sample Food Ordering App extends the VNet Flow Logs demo with an application incident surface on Azure Container Apps.

## Resources

Terraform creates these resources in the Sample Food resource group:

- Azure Container Registry.
- User-assigned managed identity for image pulls.
- `AcrPull` role assignment.
- VNet and delegated Container Apps infrastructure subnet.
- Container Apps Environment integrated with the VNet.
- API Container App on port `8080`.
- Frontend Container App on port `80`.
- Application Insights linked to the demo Log Analytics workspace.
- Diagnostic settings for Container Apps logs and metrics.

The apps start with Microsoft placeholder images. Use `deploy-sample-food-images.sh` to build and deploy real Grubify API/frontend images into the lab ACR.

## Demo Flow

1. Deploy Terraform.
2. Check placeholder app status:

   ```bash
   Student/Resources/scenarios/scripts/deploy-sample-food-images.sh --status
   ```

3. Build and deploy Grubify images:

   ```bash
   Student/Resources/scenarios/scripts/deploy-sample-food-images.sh
   ```

4. Validate API/frontend and recent logs:

   ```bash
   Student/Resources/scenarios/scripts/validate-sample-food-app.sh
   ```

5. Generate user-like traffic:

   ```bash
   Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh
   ```

6. Generate controlled cart load:

   ```bash
   Student/Resources/scenarios/scripts/break-sample-food-app.sh
   ```

7. Investigate with KQL and the `sample-food-container-app-incident-analysis` Azure SRE Agent skill.

## Observability Notes

Azure Container Apps workload traffic is not represented as VNet Flow Logs. Use these sources instead:

- `ContainerAppHTTPLogs` for HTTP status, path, latency, revision and request IDs.
- `ContainerAppConsoleLogs_CL` for application stdout/stderr.
- `ContainerAppSystemLogs_CL` for revision provisioning, image pulls and platform events.
- Application Insights for application telemetry when emitted by the app.

Use `NTANetAnalytics` for the base VM/network lab and for explicitly documented probe traffic, not for Container Apps workload flows.