# Prompts — SRE use-case builder (case 00)

Open a new chat in the SRE Agent portal, type `/agent`, pick **sre-usecase-builder** and paste one of these prompts.
One or two sentences are enough: say **what** you want to know, **how often**, and **why**. Mention where the data lives
if you know it. If you don't, the builder discovers it or leaves a placeholder for you to fill.

Prompts marked ✅ were run live on a lab agent; each one produced all 4 Builder blocks with no questions. Three of them were run
in Spanish and are shown here in English: the builder answers in the language you write in.

## 1. Verified prompts

| ✅ | Prompt | Result |
|---|---|---|
| ✅ | I need a weekly report of orphaned managed disks (not attached to any VM) across my subscriptions, with size and SKU, so we can clean up waste. | `READY_LIVE_VERIFIED` (Resource Graph) |
| ✅ | Every Monday, warn me about the Entra ID app secrets that have already expired or expire in the next 30 days, so that no integration goes down. | `READY_LIVE_VERIFIED` (Microsoft Graph) |
| ✅ | Every morning at 7, I want to know which virtual machines are stopped but not deallocated (they still bill compute) across all my subscriptions, so the team can deallocate them. | `READY_LIVE_VERIFIED` (Resource Graph) |
| ✅ | We keep an Excel file in SharePoint where the systems team tracks the certificate inventory with expiry dates. I want a weekly report that reads the latest Excel file, flags the certificates that expire in less than 30 days, compares it with the previous week and publishes the report in SharePoint. | `READY_WITH_INPUTS` (site and folder to fill) |

## 2. More ideas by source type

### Log Analytics (KQL)

- Every morning, list the VMs and Arc servers that stopped sending heartbeat in the last 24 hours, grouped by resource group, using workspace `<workspace name>`.
- Weekly report of servers with average CPU above 85% or free disk below 10% over the last 7 days.
- Daily report of the 5xx errors of my Application Gateways in the last 24 hours, with the most affected URLs.

### Azure Resource Graph / ARM

- Monthly list of high-impact Azure Advisor recommendations per subscription, with what changed since last month.
- Weekly report of public IPs not associated with any resource, and network interfaces not attached to any VM.
- Monthly report of the machines without backup configured in Recovery Services, per subscription.
- Every Monday, list the resources deleted in the last 7 days from the Activity Log, with who deleted them.

### Cost Management

- Weekly cost by resource group for the last 7 days, highlighting the 10 biggest increases versus the previous week.
- Monthly report of cost by service and by `CostCenter` tag, flagging what has no tag.

### Microsoft Graph

- Every Monday, list guest users who have not signed in for 90 days.
- Weekly report of app registrations without an owner, and of service principals with certificates expiring in 60 days.

### Files in SharePoint or Blob

- Read the latest server inventory CSV in storage account `<account>`, container `inventory`, and flag servers past end of support or without an owner.
- Every week, read the latest Excel file in the `Reports/Security` folder of the site `https://contoso.sharepoint.com/sites/infra`, compare it with the previous week and publish the report in the same folder.

### Combine sources in one report

- Weekly operations summary: VMs without heartbeat (Log Analytics) plus high-impact Advisor recommendations plus cost by resource group, in one report.

### Report in a customer's look

Name the company or its website and the builder reads the logo, colours and font from the public site:

- Weekly report of VMs and Arc servers without heartbeat for Contoso (https://www.contoso.com), with its logo and colours.
- Weekly report of the Entra ID secrets that expire in 30 days for Contoso (https://www.contoso.com), with its logo and colours, and charts per application.

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
