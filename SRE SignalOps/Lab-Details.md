**[Home](./README.md)** — [Start Mission 00 >](./Challenge-00.md)

# Lab Details — Understand Grubify

Read this orientation before Mission 00. It explains what Grubify does, how its components fit together, where operational evidence appears, and what normal should look like.

Architecture describes the intended system. A baseline records what the deployed system proves at a specific time. Learn the architecture now, then return to the baseline checklist after Missions 00–02 and before starting Mission 03.

## Application Overview

Grubify is a small food-ordering application. A customer opens the React website, browses restaurants and food items, and uses the cart. The website calls a separate ASP.NET Core API over HTTPS. The API keeps its sample restaurants, food items, carts, and orders in process memory; this isolated SignalOps core has no external database, queue, cache, or payment service.

```mermaid
flowchart LR
	Customer[Customer browser] -->|HTTPS :443| Frontend[React 18 and nginx<br/>Frontend Container App<br/>target port 80]
	Frontend -->|HTTPS REST to /api/*| API[ASP.NET Core .NET 9<br/>API Container App<br/>target port 8080]
	API --> Memory[(In-memory<br/>restaurants, food items,<br/>carts, and orders)]

	classDef customer fill:#F3F2F1,stroke:#605E5C,color:#201F1E
	classDef app fill:#CFE4FA,stroke:#0078D4,color:#201F1E
	classDef data fill:#DFF6DD,stroke:#107C10,color:#201F1E
	class Customer customer
	class Frontend,API app
	class Memory data
```

The two applications are independently deployed and independently observable. A green frontend root proves that nginx can serve the website; it does not prove that the browser can load restaurant data from the API. Likewise, a healthy API does not prove that the frontend has the correct API URL or CORS origin.

## Important Application URLs

These URLs point to the shared Grubify lab deployment. Mission 00 also writes the environment-specific base addresses to `FRONTEND_URL` and `API_BASE_URL`; use those azd values if you deploy a different environment.

| Experience or check | URL | Why it matters |
|---|---|---|
| Grubify customer experience | [Open the Grubify frontend](https://ca-signalopscor-food-frontend.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/) | Loads the React application and exercises the browser-to-API customer path |
| API health | [Open the health endpoint](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/health) | Confirms that the API process can answer a lightweight request |
| Restaurants | [Open the restaurants endpoint](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/api/restaurants) | Returns the restaurant data shown by the frontend |
| Food items | [Open the food-items endpoint](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/api/fooditems) | Returns the menu catalog used by the browse experience |
| Demo cart | [Open the demo-user cart](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/api/cart/demo-user) | Exercises a user-scoped read without changing data |
| Compatibility check | [Open WeatherForecast](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/WeatherForecast) | Provides a lightweight fallback when an older image does not expose `/health` |
| Negative control | [Open the undefined menu route](https://ca-signalopscor-food-api.proudhill-f504bbcd.swedencentral.azurecontainerapps.io/api/menu) | Expected to return `404`, proving the test can distinguish an undefined route from an outage |

Do not use the API root `/` as a health test; it is not an application route and normally returns `404`. Cart and order write endpoints are intentionally omitted because opening them in a browser does not perform a meaningful customer transaction.

## Azure Resource Architecture

```mermaid
flowchart TB
	subgraph WorkloadRG[Workload resource group: rg-signalopscore-food]
		ACR[Azure Container Registry]
		CAE[Container Apps environment]
		Frontend[Frontend Container App<br/>public ingress, port 80<br/>min 1 / max 3]
		API[API Container App<br/>public ingress, port 8080<br/>min 1 / max 5]
		FrontendIdentity[Frontend managed identity]
		APIIdentity[API managed identity]
		AppInsights[Workspace-based<br/>Application Insights]
		WorkloadLAW[Workload Log Analytics<br/>30-day retention]

		ACR -->|image pull| Frontend
		ACR -->|image pull| API
		FrontendIdentity -->|AcrPull| ACR
		APIIdentity -->|AcrPull| ACR
		Frontend --> CAE
		API --> CAE
		API -. application telemetry .-> AppInsights
		AppInsights --> WorkloadLAW
		CAE -. console and system logs .-> WorkloadLAW
	end

	subgraph AgentRG[Agent resource group: rg-signalopscore-agent]
		Agent[Azure SRE Agent<br/>Autonomous mode<br/>High access configuration]
		AgentIdentity[Agent managed identity]
		AgentInsights[Agent Application Insights]
		AgentLAW[Agent Log Analytics<br/>30-day retention]
		AgentInsights --> AgentLAW
		AgentIdentity --> Agent
	end

	Agent -->|Application Insights connector| AgentInsights
	Agent -->|Log Analytics connector| WorkloadLAW
	AgentIdentity -->|scoped Azure RBAC| WorkloadRG

	classDef app fill:#CFE4FA,stroke:#0078D4,color:#201F1E
	classDef observe fill:#FFF4CE,stroke:#F7630C,color:#201F1E
	classDef identity fill:#F3F2F1,stroke:#605E5C,color:#201F1E
	classDef agent fill:#E8DAEF,stroke:#5C2D91,color:#201F1E
	class ACR,CAE,Frontend,API app
	class AppInsights,WorkloadLAW,AgentInsights,AgentLAW observe
	class FrontendIdentity,APIIdentity,AgentIdentity identity
	class Agent agent
```

## How Many Infrastructure Components Are Deployed?

After Missions 00–02, the lab deploys **14 core Azure resources** across two resource groups. This count includes the services, identities, and agent connectors that participants inspect. It excludes the two resource groups themselves, RBAC role-assignment records, Container App revisions, deployment records, subagent configuration, and the response plan.

| Deployment area | Count | Components | Why they are separate |
|---|---:|---|---|
| Grubify workload | 8 | 2 Container Apps, 1 Container Apps environment, 1 container registry, 2 managed identities, 1 Application Insights component, and 1 Log Analytics workspace | Separates frontend and API releases and scaling, uses credential-free image pulls, and keeps application and platform evidence with the workload |
| SRE Agent | 6 | 1 Azure SRE Agent, 1 managed identity, 1 Application Insights component, 1 Log Analytics workspace, and 2 evidence connectors | Keeps the reasoning and action plane outside the customer path, gives it an auditable identity, records its own telemetry, and connects specific evidence sources |
| **Total** | **14** | **Core resources deployed by the lab** | **Supports an isolated customer path, an independent evidence plane, and bounded agent access** |

The two-resource-group boundary is intentional: `rg-signalopscore-food` owns the customer workload, while `rg-signalopscore-agent` owns the operational agent. This makes ownership, cost, cleanup, access scope, and incident blast radius easier to explain. The resource count may be higher in the Azure portal because Azure also displays revisions, role assignments, deployments, and provider-managed objects.

| Resource or boundary | Normal responsibility |
|---|---|
| Frontend Container App | Serves the React application through nginx and gives the browser the API base URL |
| API Container App | Serves restaurant, food-item, cart, order, weather, and health routes |
| In-memory API state | Holds non-durable demonstration data while the API process is alive; a restart can reset carts and orders |
| Container Apps environment | Runs both application revisions and sends platform logs to the workload workspace |
| Application Insights | Receives API request, dependency, and exception telemetry when the connection string and SDK are active |
| Workload Log Analytics | Stores workspace-based application telemetry and Container Apps platform logs |
| Azure SRE Agent | Investigates evidence and can propose or perform actions allowed by its identity and policies; it remains outside the customer request path |
| Agent managed identity and RBAC | Grants Reader, Monitoring Reader, Log Analytics Reader, and Contributor in the workload resource group, plus subscription Monitoring Contributor |

## Normal Request, Evidence, and Response Flow

```mermaid
sequenceDiagram
	autonumber
	actor Customer
	participant Frontend as Frontend Container App
	participant API as API Container App
	participant AI as Application Insights
	participant LAW as Log Analytics
	participant Monitor as Azure Monitor
	participant SRE as Azure SRE Agent

	Customer->>Frontend: GET / over HTTPS
	Frontend-->>Customer: React application
	Customer->>API: GET /api/restaurants
	API-->>Customer: 200 + restaurant JSON
	API-->>AI: Request duration, result code, exception data
	Frontend-->>LAW: Container console and platform logs
	API-->>LAW: Container console and platform logs
	Monitor-->>SRE: Filtered alert or incident signal
	SRE->>AI: Query application evidence
	SRE->>LAW: Query platform and console evidence
	SRE-->>SRE: Correlate scope, hypotheses, and confidence
	Note over SRE: Any environmental write remains governed<br/>by identity, tool access, policy, and approval
```

The SRE Agent is on the **evidence and control path**, not the **customer request path**. During an incident, first decide whether the frontend, browser-to-API call, API process, deployment revision, or telemetry path is affected. Do not describe “Grubify” as one health state when evidence covers only one component.

## Normal Baseline

Before Mission 00, use this table to understand the expected end state. After Missions 00–02, record a timestamp and the exact subscription, workload resource group, agent resource group, frontend URL, API URL, and active revision names, then evaluate every row.

| Baseline dimension | Normal expectation | Operational meaning |
|---|---|---|
| Azure scope | Intended subscription; `rg-signalopscore-food` and `rg-signalopscore-agent` exist | Evidence and actions are being evaluated in the correct environment |
| Deployment | Both Container Apps are `Running`, each has one ready revision receiving 100% of traffic | The platform has a routable application revision |
| Capacity | Frontend min/max replicas `1/3`; API min/max replicas `1/5` | At least one replica should remain available while scale-out is permitted |
| Frontend | `GET <frontend-url>/` returns HTTP `200` and usable HTML | Static website delivery works |
| API liveness | `GET <api-url>/health` returns HTTP `200`; use `/WeatherForecast` as a compatibility check if the deployed image predates the health route | The API process can answer a lightweight request |
| Domain reads | `GET /api/FoodItems` and `GET /api/Restaurants` return HTTP `200` with JSON | Core browse operations work |
| Cart read | `GET /api/cart/demo-user` returns HTTP `200` with JSON | A user-scoped state path works without changing data |
| Negative control | `GET /api/menu` returns HTTP `404` | The test can distinguish an undefined route from an outage |
| Application telemetry | Recent API requests appear in Application Insights with timestamps, operation names, durations, and result codes | The application evidence path is populated, not merely configured |
| Platform telemetry | Recent frontend and API console/system records appear in the workload workspace | The hosting evidence path is populated |
| Agent evidence access | The SRE Agent can retrieve Grubify request data from the workload workspace and its own telemetry from the agent Application Insights source | Connectors, identity, RBAC, and data availability work together |
| Safety posture | Read-only investigation needs no environmental write; proposed writes show an approval decision before execution | Investigation capability is not mistaken for unrestricted remediation |

Use three labels in the baseline record:

- **PASS** — current evidence matches the normal expectation.
- **FAIL** — current evidence contradicts the normal expectation; stop and treat this as a pre-existing issue.
- **UNKNOWN** — evidence is unavailable, stale, or not yet ingested; state the next check instead of assuming health.

Do not begin Mission 03 until the frontend, API liveness, domain reads, active revisions, and evidence access are either **PASS** or explicitly documented as controlled exercise limitations. Preserve this baseline so later incident results can be compared with the same routes, time window, and resources.

## Lab Sequence

| Stage | Purpose |
|---|---|
| Before Mission 00 | Understand Grubify, its Azure architecture, its evidence paths, and the expected normal state |
| Missions 00–02 | Deploy the workload and agent, then connect their evidence sources |
| Before Mission 03 | Return here and record the observed baseline using PASS, FAIL, or UNKNOWN |
| Missions 03–13 | Investigate operational signals against the preserved baseline |

[Start Mission 00 >](./Challenge-00.md)