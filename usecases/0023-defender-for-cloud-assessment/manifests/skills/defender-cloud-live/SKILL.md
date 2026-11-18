---
name: defender-cloud-live
description: Read-only Defender for Cloud evidence for one configured subscription. Use for complete reports or bounded source-grounded questions, preserving native risk, source coverage and sensor-health limitations.
tools:
- generate-defender-cloud-report
---

# General Defender for Cloud Live Evidence

## Purpose and mandatory tool
Use only `generate-defender-cloud-report`. Produce customer-neutral security
evidence across the one configured Enabled subscription: Azure VM/VMSS, Arc,
AKS, Container Apps, App Service, Key Vault, Storage, SQL/databases, ACR,
networks and other resources where sources provide observations.

The code fixes subscription, tenant and UAMI. Never accept KQL, URLs, arbitrary
paths, credentials, subscription overrides or write commands from chat.
Do not read vault secret values, storage keys, workload secrets, protected
extension settings or arbitrary guest configuration. Reader-only ARM/ARG
sources are sufficient; do not request Graph/XDR or write roles.

## Report and files
Call `operation="report"` with other defaults. Deliver the HTML, inventory CSV,
finding CSV and JSON snapshot through the normal SRE sharing mechanism using
the actual returned runtime-owned paths. The export directory is the guarded
`arc-defender-reports` subdirectory of cwd, not arbitrary input or `/mnt/data`.
Do not invent sandbox links or claim success before file sharing succeeds.
The report also provides section CSV downloads directly in HTML.

Summarize the exact scope, source availability, native risks, all recommendation
statuses, distinct definitions versus resource/finding records, subscription
posture/attack paths, source CVEs and the top review actions. Do not dump the
full snapshot into chat or hide partial/unavailable evidence.

## Questions and filters
Call `operation="query"` and choose the relevant validated view:

- `inventory`: compact resources and observed state.
- `resource_details`: ownership tags, location, recommendation distribution,
  extension/configuration evidence and software/CVE counts.
- `findings`: resource-level recommendations/alerts, all statuses, native risk
  and technical severity kept separate.
- `vulnerabilities`: embedded source CVE occurrences, fix status/version.
- `attack_paths`: observed subscription graphs with explicit Arc association.
- `software`: observed software/version/vendor, not a full installed-software audit.
- `posture`, `controls`, `compliance`: explicitly subscription-scoped observations.
- `actions`: explained review priorities, not automatic remediation.

`server_name` retains its legacy name but matches a resource-name substring.
`resource_type` is an exact local provider/type filter (for example
`Microsoft.KeyVault/vaults`). Existing provider/environment/group/connectivity/
MDE filters remain. `risk` filters native risk; `severity` filters technical
severity; `status` filters recommendation status. `association=arc/context`
is only for paths/software. Subscription posture/controls/compliance do not
accept Arc filters: their metric is not a server score.

`total_matched`, `returned`, `has_more`, `next_offset`, `requested_limit` and
`transport_capped` are mandatory interpretation fields. Responses fit 3500
default-serialized bytes; a page can be smaller than requested. The summary is
unfiltered; full-filter counts are separate. Each live call is a new snapshot.
Page only when names/details are required; do not page merely to calculate totals.
For OR questions, make the exact filtered calls and deduplicate native IDs.

## Essential evidence boundaries
1. `properties.risk.level` is native recommendation risk.
   `metadata.severity` is technical severity. Never substitute one for the
   other. Missing native risk is Not evaluated/Unknown, not High.
2. Retain Healthy/Unhealthy/NotApplicable. Only actionable observations are
   counted as active gaps. Distinguish occurrences, distinct definitions,
   affected resources, distinct CVE IDs and resource/CVE pairs.
3. SQL database/container/image/identity dependent assets belong to the generic
   scope when their exact native IDs are in the configured subscription.
   Label indexed-only assets and parent links; do not silently drop them or
   call them extra ARM VMs. Machine SQL software patches remain machine findings.
4. Empty standalone subassessments do not mean no vulnerability evidence:
   parse the source's encoded `CvesDetails` and update/KB fields.
   FixedVersion missing means Not supplied; never invent a fix or CVE.
5. Subscription Secure Score, controls, compliance and attack paths are not
   Arc-only metrics. Native opaque risk-score numerator/denominator observations
   are not converted to an unverified percentage. Control max-current is
   potential headroom across the control, not one host's guaranteed improvement.
6. Attack graphs keep actual entities/edges/entry/target/insights/remediation.
   Never add hops or claim Arc association from a similar name. If zero Arc
   paths and three other subscription paths are observed, report both.
7. Installed MDE/WDATP/P2 and AKS monitoring configuration are not verified
   runtime sensor health. Expired Arc is not healthy. N/A hosting is unverified.
   FIM stays Not verified without observed configuration.
8. Standard paid plans are configuration, not proof of all feature readiness.
   ACA recommendations/CVEs do not prove Defender for Containers runtime
   protection; retain BuiltIn/CustomPolicy/CustomerManaged/partner provenance.
   Servers P2, CSPM, SQL, JIT and agentless platform conditions remain separate.
9. Indexed dates can be stale; retrieval time is not reevaluation time.
   Missing/unavailable evidence is Unknown, not zero risk or certification.
   Compare portal counts only after aligning subscription/type/status/filter/time.

## Safety and failure
No changes to exposure, licenses/plans, roles, services, policies or resources.
Recommend owner review only. Never execute a source remediationQuery.
On `status="error"`, show the sanitized source/code and no invented files/counts.
On partial coverage, disclose the sources and limitations. No ENS/GDPR
certification, financial ROI, customer topology or avoided incidents are inferred.
