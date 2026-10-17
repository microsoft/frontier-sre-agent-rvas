# SignalOps Grubify architecture

## Components

Grubify comprises a React frontend and an ASP.NET API, each in an Azure Container
App. The frontend receives the API URL through its runtime entrypoint. API CORS
must permit the exact HTTPS frontend origin. Images are built from the bundled
sources into Azure Container Registry. Terraform uses an existing registry and
digest-pinned images; Bicep uses the environment's azd-managed registry and
images. A user-assigned identity provides image-pull access.

## Traffic And Telemetry

Read endpoints include `/health`, `/api/fooditems`, and `/api/restaurants`.
`POST /api/cart/{userId}/items` deliberately retains approximately 10 MB per
request. This is an isolated lab fault, not normal application behavior.

The API exports Application Insights telemetry. Container Apps logs and VM
telemetry, when configured, reach the workload Log Analytics workspace.
The deployment context supplies the actual resource names and IDs; do not assume
names or reuse another environment's endpoint.

The full Terraform lab's separate hub-spoke network contains Firewall, Bastion and VM tiers. Parking
Manager includes Lisbon/Berlin Container Apps and Madrid/Paris VM applications.
The Bicep core does not create those VM/network tiers. Grubify uses in-memory
application data; a VM in the full lab is not automatically its downstream dependency.
Use a coach-approved VM-to-VM test path for network missions. Container Apps
workload traffic is not supported by VNet Flow Logs; use app telemetry instead.

## Operational Entry Points

Load the selected deployment with `Get-SignalOpsContext.ps1`. Agent actions and
the Grubify response plan start in approval-gated Review mode. The three local
specialists share an incident context; application-to-network handoff is allowed,
while unrelated cost questions require explicit invocation.
Use Mission 01 for bounded cart injection and recovery, Mission 02 for knowledge
retrieval, and Missions 10–11 for explicitly prepared network evidence.
