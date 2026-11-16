# Prompts — SRE use-case builder (case 00)

Open a new chat in the SRE Agent portal, type `/agent`, pick **sre-usecase-builder** and paste one of these prompts.
One or two sentences are enough: say **what** you want to know, **how often**, and **why**. Mention where the data lives
if you know it. If you don't, the builder discovers it or leaves a placeholder for you to fill.

Prompts marked ✅ were run live on a lab agent; each one produced all 4 Builder blocks with no questions.

## 1. Verified prompts

| ✅ | Prompt | Result |
|---|---|---|
| ✅ | I need a weekly report of orphaned managed disks (not attached to any VM) across my subscriptions, with size and SKU, so we can clean up waste. | `READY_LIVE_VERIFIED` (Resource Graph) |
| ✅ | Quiero que cada lunes me avise de los secretos de las aplicaciones de Entra ID que ya han caducado o caducan en los próximos 30 días, para que no se nos caiga ninguna integración. | `READY_LIVE_VERIFIED` (Microsoft Graph) |
| ✅ | Cada mañana a las 7 quiero saber qué máquinas virtuales están paradas pero no desasignadas (siguen facturando cómputo), en todas mis suscripciones, para que el equipo las desasigne. | `READY_LIVE_VERIFIED` (Resource Graph) |
| ✅ | Tenemos un Excel en SharePoint donde el equipo de sistemas mantiene el inventario de certificados con su fecha de caducidad. Quiero un informe semanal que lea el último Excel, marque los que caducan en menos de 30 días, lo compare con la semana anterior y deje el informe publicado en SharePoint. | `READY_WITH_INPUTS` (site and folder to fill) |

## 2. More ideas by source type

### Log Analytics (KQL)

- Every morning, list the VMs and Arc servers that stopped sending heartbeat in the last 24 hours, grouped by resource group, using workspace `<workspace name>`.
- Weekly report of servers with average CPU above 85% or free disk below 10% over the last 7 days.
- Quiero un informe diario de los errores 5xx de mis Application Gateway en las últimas 24 horas, con las URLs más afectadas.

### Azure Resource Graph / ARM

- Monthly list of high-impact Azure Advisor recommendations per subscription, with what changed since last month.
- Weekly report of public IPs not associated with any resource, and network interfaces not attached to any VM.
- Informe mensual de las máquinas sin backup configurado en Recovery Services, por suscripción.
- Every Monday, list the resources deleted in the last 7 days from the Activity Log, with who deleted them.

### Cost Management

- Weekly cost by resource group for the last 7 days, highlighting the 10 biggest increases versus the previous week.
- Informe mensual del coste por servicio y por etiqueta `CostCenter`, marcando lo que no tenga etiqueta.

### Microsoft Graph

- Every Monday, list guest users who have not signed in for 90 days.
- Weekly report of app registrations without an owner, and of service principals with certificates expiring in 60 days.

### Files in SharePoint or Blob

- Read the latest server inventory CSV in storage account `<account>`, container `inventory`, and flag servers past end of support or without an owner.
- Lee cada semana el último Excel de la carpeta `Informes/Seguridad` del sitio `https://contoso.sharepoint.com/sites/infra`, compáralo con la semana anterior y publica el informe en la misma carpeta.

### Combine sources in one report

- Weekly operations summary: VMs without heartbeat (Log Analytics) plus high-impact Advisor recommendations plus cost by resource group, in one report.

### Report in a customer's look

Name the company or its website and the builder reads the logo, colours and font from the public site:

- Weekly report of VMs and Arc servers without heartbeat for Contoso (https://www.contoso.com), with its logo and colours.
- Quiero un informe semanal de los secretos de Entra ID que caducan en 30 días para Contoso (https://www.contoso.com), con su logo y sus colores, y gráficos por aplicación.

## 3. Follow-up prompts in the same thread

The builder regenerates and re-tests after each change.

| You want to | Say |
|---|---|
| Change a threshold | Change the threshold to 60 days and mark Premium disks as high severity. |
| Change the schedule | Run it every day at 06:30 UTC instead of weekly. |
| Keep history and compare | Publish the report to my SharePoint site `<site URL>` folder `Reports/Disks` so each run compares with the previous one. |
| Publish to Blob | Publish the report to storage account `<account>`, container `sre-reports`. |
| Add a column or KPI | Add the disk tier as a column and a KPI with the total GB of Premium disks. |
| Add a chart | Add a chart of orphaned capacity (GB) by resource group. |
| Use a customer's look | Use the logo and colours of https://www.contoso.com. |
| Fix the brand | Use primary #0E5A5A, accent #FF7A59 and the logo at `<https URL of the logo>`. |
| Rename columns | Call the columns "Disk", "Size (GB)" and "Days unattached". |
| Understand permissions | Explain the permissions the agent needs for this and give me the exact commands. |
| Check real columns first | Probe the source and show me the real columns before generating. |
| Get one block again | Give me block 1 again (the Python tool) complete. |
| Skip questions | Use defaults and placeholders, don't ask me anything. |

## 4. Prompts for the generated subagent

After you create the generated tool, skill and subagent (for example `orphaned-managed-disks`), open a new chat, type `/agent`,
pick the subagent (the chip **Agent: orphaned-managed-disks** appears) and send one of these prompts:

- `run the self test of the tool and tell me if it works`
- `check the live data sources and show me the columns you see`
- `give me the report for the last 7 days`
- `what changed since the previous report and what should I fix first?`
