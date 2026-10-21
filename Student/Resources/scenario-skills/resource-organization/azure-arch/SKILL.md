---
name: azure-arch
description: |
  Build a first-pass Azure landing-zone architecture and cost estimate from a VM inventory workbook.
  Use this skill when the user wants a draw.io architecture, Azure stencil diagram, landing-zone recommendation,
  migration target design, or rough-order monthly Azure cost estimate for a server estate.
  Outputs typically include a draw.io document, an Excel cost workbook, a CSV summary, and JSON metadata.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: resource-organization
---

# Azure Architecture Skill

Use this skill to convert a VM/server inventory into a reusable Azure landing-zone design package.

## When to use

Use this skill when the user asks for any of the following:
- An Azure architecture diagram from a server or VM list
- A draw.io or diagrams.net document with Azure stencils
- A first-pass landing-zone design for a migration to Azure
- A rough-order monthly Azure cost estimate from an inventory workbook
- A comparison scenario such as Azure Hybrid Benefit on eligible Windows Server VMs

## Inputs expected

This skill works best when you have:
- A spreadsheet or CSV containing server inventory
- Core sizing fields such as server name, role, CPU, RAM, OS, and application/system grouping
- Region target, such as West Europe
- Scope assumptions, such as new subscription, new VNets, single region, or DR exclusion

If some details are missing, infer a practical first-pass design and state the assumptions in the output artifacts.

## Required workflow

1. Read the input inventory file from the thread workspace.
2. Normalize columns and derive workload classes such as web/app/data/SAP/non-prod.
3. Map servers to candidate VM families and retail catalog sizes that meet estimated CPU and RAM. Retail meter presence is not proof of regional or subscription deployability, quota, capacity, certified workload suitability or actual VM capabilities.
   - Validate candidate D and E family capabilities against current official size documentation and approved subscription SKU evidence.
   - If the retail catalog is empty or unavailable, stop sizing and disclose the failure. Do not silently use a static catalog.
   - If no candidate meets the requirements, require manual sizing rather than selecting a smaller fallback.
4. Assign storage profiles for OS and data disks.
   - OS disks use an OS capable disk type, Premium SSD managed disks in this template. Premium SSD v2 cannot be an OS disk.
   - Data disks use Premium SSD managed disks by default. Premium SSD v2 is an explicit data disk only option after region, zone and VM compatibility review.
   - V2 capacity pricing alone does not include additional provisioned IOPS and throughput. Record those requirements and costs before treating the estimate as complete.
5. Build a hub-and-spoke landing-zone design unless the user explicitly requests a different pattern.
6. Ensure the architecture narrative and recommendations align to the Azure Well-Architected Framework, especially security, reliability, operational excellence, performance efficiency, and cost optimization.
7. Create a native `.drawio` XML draft locally, or use an optional operator configured draw.io connector after verifying its actual registered tool names and permissions.
   - The default allowlist does not promise a draw.io MCP connector. Do not invent aliases or assume a connector is installed.
   - If an approved connector exists, discover its actual shape search and render tools at run time. Use returned stencil identifiers only after confirming availability.
   - If a connector or Azure stencil identifiers are unavailable, adapt [the local XML draft](references/landing-zone-draft.drawio) with generic labeled shapes. Do not invent Azure stencil IDs.
   - Reflect only the modeled target Azure resources and assumptions, not anything currently deployed.
   - Show each modeled Azure resource explicitly in the diagram rather than collapsing multiple resources into one consolidated node, summary tile, or pooled block.
   - When the inventory implies repeated resources, enumerate them clearly in the architecture output so the user can see the full modeled footprint.
   - Require an actual import and render validation before claiming a completed diagram. XML parsing or a nonempty file alone is insufficient. If no renderer is available, deliver only an explicitly unvalidated XML draft and state the missing validation.
8. Estimate Azure monthly costs using current Azure Retail Prices API data.
9. Produce both baseline PAYG and Azure Hybrid Benefit scenarios when Windows Server eligibility is relevant.
10. Produce reliability recommendations tailored to the modeled estate.
11. Explicitly remind the user to enable Microsoft Defender for Cloud and subscription-level service alerts for the target subscription.
12. Emit these deliverables:
   - `<prefix>-landing-zone.drawio`, with explicit draft or import and render validation status
   - `<prefix>-cost-estimate.xlsx`
   - `<prefix>-cost-summary.csv`
   - `<prefix>-estimate-metadata.json`
13. Persist the generated files for download before sharing them with the user.

## Default architecture pattern

Unless the user specifies otherwise, use:
- Four subscriptions by environment: prod, dev, test, and acceptance
- Matching environment VNets for prod, dev, test, and acceptance rather than combining all workloads into one network boundary
- A hub-and-spoke layout within each environment, or a shared connectivity hub with clearly separated spokes per environment when the user wants centralized connectivity
- Prod VNets segmented for web/app and data tiers where needed; dev, test, and acceptance VNets can be simpler unless the inventory or compliance requirements justify more tiers
- Shared services such as Log Analytics, Recovery Services Vault, Key Vault, policy/governance, and subscription monitoring
- Hub services such as VPN/ExpressRoute, VPN Gateway, Azure Firewall, Bastion, and Private DNS Resolver
- Zone-aware shared services and failure-domain separation for critical workloads where the region and service support it
- Well-Architected guardrails called out directly in the architecture assumptions and recommendations

## Costing rules

- Use Azure Retail Prices API list/consumption pricing.
- Restrict VM price selection to true `Consumption` rows.
- Exclude Spot and Low Priority rows.
- Prefer a current candidate satisfying sizing requirements, but verify resource SKU support independently from retail pricing.
- Model Windows baseline using Windows-inclusive pricing.
- Model Azure Hybrid Benefit by using the base compute rate for eligible Windows Server VMs.
- Separate OS and data disk models. Never use Premium SSD v2 for OS disks. A missing price is a disclosed failure, not a deployability assertion.
- Exclude items unless the user explicitly asks for them:
  - Data egress
  - Public IP charges
  - DNS query charges
  - DDoS Protection
  - Backup vault storage
  - Paired-region DR
  - SQL Server or third-party licensing not embedded in the selected SKU

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Output expectations

The Excel workbook should contain, at minimum:
- `Summary`
- `SharedServices`
- `VMEstimate`
- `Assumptions`
- `PriceTrace`
- `Recommendations`

The `Summary` sheet should include:
- Baseline monthly total
- Monthly total with Azure Hybrid Benefit
- AHB savings

Subscription readiness reminders should be captured in `Assumptions`, `Recommendations`, and the metadata JSON rather than as a zero-cost summary line.

The metadata JSON should include:
- generation timestamp
- input workbook path
- server count
- baseline monthly total
- monthly total with AHB
- AHB savings
- assumption notes
- reliability recommendations
- subscription reminders
- Well-Architected alignment notes

## Implementation template

Use the included Python template as the starting point for cost-model implementation:
- [generator-template.py](generator-template.py)

Copy it into the current thread workspace, then adapt:
- thread paths
- source workbook path
- region
- environment-specific subscription names and VNet CIDRs for prod, dev, test, and acceptance
- shared service assumptions
- workload grouping rules for sizing and costing only
- any user-requested architecture variants that affect pricing or recommendations

The Python template remains responsible for workbook, CSV and metadata generation only. Create the diagram separately, using local XML or an approved optional connector. Do not use workbook grouping rules to consolidate distinct modeled Azure resources in the architecture view. The generator's `diagramGeneration` metadata is a planning request, not proof that a connector exists or that a diagram was created, imported or rendered.

### Local diagram fallback and validation

1. Copy [references/landing-zone-draft.drawio](references/landing-zone-draft.drawio) into the approved workspace output path as `<prefix>-landing-zone.drawio`.
2. Replace placeholders with the approved proposed topology, region, subscriptions, resource groups and individual resources. The bundled file is a generic planning example, not a deployed inventory or validated architecture.
3. Preserve the `mxfile` wrapper, root cells `0` and `1`, unique IDs, valid parent and edge references and `mxGeometry` children. Escape label text as XML.
4. Parse the XML and check references locally. This verifies structure only; keep the unvalidated draft label.
5. Import the saved file into an approved draw.io editor, or use an operator configured connector with verified actual tool names to import and render the same saved XML. Confirm labels, resource counts, containers, routes and missing stencil placeholders visually. Record editor or tool, version when available, file path, date and observed result.
6. Only after successful import and render validation remove the unvalidated draft label and describe it as a diagram output. If validation cannot run, disclose that limitation and keep the draft label. Do not claim validation from file existence or XML parsing, and do not send customer topology to an external connector without approval.

### Template configuration and validation

| Environment variable | Meaning | Default |
| --- | --- | --- |
| `SRE_ARCH_INVENTORY` | Approved input workbook path | `inventory.xlsx` |
| `SRE_ARCH_OUTPUT` | Workspace output directory | `azure-landing-zone` |
| `SRE_ARCH_REGION` | Retail region filter | `westeurope` |
| `SRE_ARCH_HOURS` | Compute hours per month | `730` |
| `SRE_ARCH_ENVIRONMENTS` | Proposed environment names, comma separated | `prod,dev,test,acceptance` |
| `SRE_ARCH_PREMIUM_V2_DATA` | Explicit data disk v2 costing option | `false` |

Environment names describe a proposed topology; they do not multiply the input inventory or shared services in the estimate. Disk capacity and count are RAM and role based planning heuristics, not measured storage requirements. Validate them against actual workload capacity, IOPS, throughput, latency and growth before approval. AHB is an eligibility assumption, not a licensing verification.

Metadata always reports `assessment_status=Partial` and source links because SKU allocation, quota, performance, licensing and full cost coverage are not validated. Explicit exclusions include logs, backups, egress, transactions, variable gateway capacity, taxes and support. The generator does not deploy resources or query subscription capacity. Scope and file approvals remain playbook gates, not host enforcement.

## Execution guidance

- Keep the script in the thread workspace, not in the attached repo.
- Validate workbook and CSV files exist and are nonempty. For `.drawio`, also require actual import and render validation before claiming a completed diagram; otherwise deliver an unvalidated draft.
- Retail and management collectors use the shared `azure_http` policy adapter for approved HTTPS hosts, disabled redirects, explicit timeouts and bounded transient retries. Do not add a second retry loop or retry authorization failures.
- When the user asks for Hybrid Benefit, present both baseline and AHB values so the savings are explicit.
- Include a recommendation section that highlights reliability improvements such as zone redundancy, backup validation, restore testing, and alert/action-group readiness.
- Always call out that Microsoft Defender for Cloud onboarding and subscription-level Service Health or Activity Log alerting still need to be enabled as part of landing-zone readiness.

## Example user asks

- "Here is my VM list. Give me an Azure architecture diagram."
- "Produce the draw.io version with Azure stencils."
- "Do a cost estimation in West Europe."
- "Show me the Hybrid Benefit included costs as well."

## Sources

- [Managed disk types and Premium SSD v2 limits](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-types), OS restriction checked 2026-10-21.
- [Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
- [Local XML draft](references/landing-zone-draft.drawio), generic shapes without external stencil dependencies. Structural regression tests do not establish editor import or rendering success.

Offline regression tests validate OS versus data disk selection, unavailable catalogs and insufficient sizing. No live retail price, resource SKU, Azure resource or deployment was queried during these tests.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.
