# Sample Food Ordering App Architecture

The Sample Food Ordering App lab is an optional application workload integrated into the existing Azure VNet Flow Logs and Traffic Analytics Terraform project.

## Components

| Component | Azure service | Terraform output/source |
| --- | --- | --- |
| Frontend | Azure Container Apps | `sample_food_frontend_container_app_name`, `sample_food_frontend_url` |
| API | Azure Container Apps | `sample_food_api_container_app_name`, `sample_food_api_url` |
| Container registry | Azure Container Registry | `sample_food_container_registry_name` |
| Runtime environment | Azure Container Apps Environment | `sample_food_resource_names.container_apps_environment` |
| App telemetry | Application Insights | `sample_food_application_insights_resource_id` |
| Log store | Log Analytics workspace | `log_analytics_workspace_customer_id` |
| Network boundary | Dedicated VNet | `sample_food_network.vnet_id`, default `10.40.0.0/16` |

## Traffic And Telemetry

- Browser users call the frontend Container App over HTTPS.
- The frontend calls the API base URL configured by `REACT_APP_API_BASE_URL`.
- The API (ASP.NET Core, container target port `8080`) exposes these routes: `GET /WeatherForecast`, `GET /api/FoodItems`, `GET /api/Restaurants`, and `GET`/`POST /api/cart/{user}/items` (e.g. `/api/cart/demo-user/items`, body `{"foodItemId":1,"quantity":1}`). There is **no `/health` and no `/api/menu`** route, and no HTTP health probe (only a platform TCP probe on port 8080); use `GET /WeatherForecast` (expect 200) as the liveness check and `GET /api/FoodItems` (expect 200) as the domain-health check.
- Azure Container Apps emits platform, console, and HTTP logs to Log Analytics when diagnostic settings are enabled.
- Application Insights is available for application telemetry when the app emits it.

## Important Boundary

Azure Container Apps workload traffic is not supported by Azure Virtual Network Flow Logs. Use Container Apps logs and Application Insights for application incident analysis. Use `NTANetAnalytics` for the existing VM/network lab and any explicitly deployed supported probe workload.

Official source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services

## Operational Entry Points

- Deploy images: `scripts/deploy-sample-food-images.sh`.
- Validate runtime: `scripts/validate-sample-food-app.sh`.
- Generate app traffic: `scripts/generate-sample-food-app-traffic.sh`.
- Trigger controlled cart load: `scripts/break-sample-food-app.sh`.

