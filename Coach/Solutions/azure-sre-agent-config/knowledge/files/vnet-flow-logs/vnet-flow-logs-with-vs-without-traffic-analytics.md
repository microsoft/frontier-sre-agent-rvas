# VNet Flow Logs Without Traffic Analytics vs With Traffic Analytics

This document compares two operational modes:

- **VNet Flow Logs without Traffic Analytics**: raw flow log collection into Azure Storage.
- **VNet Flow Logs with Traffic Analytics**: raw collection into Azure Storage plus aggregation, enrichment, and publishing to Log Analytics.

For the complete Terraform procedure, prerequisites, activation order, RBAC, and the on-demand strategy, see [vnet-flow-logs-traffic-analytics-terraform-guide.md](vnet-flow-logs-traffic-analytics-terraform-guide.md).

## Executive Summary

| Aspect | VNet Flow Logs without Traffic Analytics | VNet Flow Logs with Traffic Analytics |
| --- | --- | --- |
| Primary output | Raw JSON in Azure Storage. | Raw JSON in Storage plus aggregated and enriched data in Log Analytics. |
| Consumption | DIY: storage, export, parser, SIEM, data lake, custom pipeline. | Native Azure: `NTANetAnalytics`, `NTAIpDetails`, KQL, workbooks, custom alerts. |
| Granularity | Maximum raw granularity available in blobs. | Aggregated view in Log Analytics; raw logs remain in Storage. |
| Enrichment | Not automatic: you must enrich with asset inventory, GeoIP, threat intel, topology. | Automatic: topology, geography, security, flow types, public IP details, and threat context. |
| Operational complexity | Lower on the Azure Monitor side, higher on the custom analytics side. | Higher on the Azure Monitor configuration side, lower on the operational consumption side. |
| Cost | Flow logs + storage + optional custom platform. | Flow logs + storage + Traffic Analytics processing + Log Analytics ingestion/retention. |
| When to use | Archival, compliance, SIEM/data lake export, full pipeline control. | Dashboards, troubleshooting, KQL, alerts, security posture, network operations. |

Riferimenti ufficiali: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview, https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics, https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema, https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions

## 1. How VNet Flow Logs Without Traffic Analytics Works

VNet Flow Logs records IP traffic traversing a virtual network. The service operates at Layer 4, collects logs through the Azure platform at one-minute intervals, is not in the data path, and does not impact throughput or latency. Logs are written in JSON format to an Azure Storage Account.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#how-logging-works
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#flow-logs

The raw log contains information such as the flow log resource ID, target resource, MAC address, ACL/rule, traffic tuple, source IP, destination IP, ports, protocol, direction, flow status, encryption status, packets, and bytes. In raw logs the protocol is expressed with IANA values; the documentation shows for example `6` for TCP.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format
- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#sample-log-record

In this mode, Azure produces the source data but does not automatically produce Traffic Analytics tables such as `NTANetAnalytics` or `NTAIpDetails`. To analyze, visualize, or query the data you must use your own tools: JSON parsers, data lake, SIEM, IDS, ETL pipeline, notebooks, Azure Data Explorer, Microsoft Sentinel via custom ingestion, or another platform.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-does-flow-logging-do

## 2. How VNet Flow Logs With Traffic Analytics Works

With Traffic Analytics, VNet Flow Logs continues to write raw JSON to the Storage Account. In addition, Traffic Analytics reads the blobs from Storage, aggregates the flows, enriches them with security, topology, and geography information, and publishes them to a Log Analytics workspace.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#how-traffic-analytics-works
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation

Traffic Analytics aggregates flows with the same source, destination, destination port, NSG name, NSG rule, direction, and TCP/UDP protocol. The default processing interval is 60 minutes; accelerated processing at 10 minutes is also available. The process may take up to 1 hour before the enriched record is available in Azure Monitor Logs.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-frequently-does-traffic-analytics-process-data

Consumption is done through Log Analytics and KQL on the `NTANetAnalytics` and `NTAIpDetails` tables. Microsoft documentation provides queries for subnets communicating with public IPs, subnet-to-subnet, cross-region traffic, traffic by subscription, ExpressRoute, load balancer, public IPs, and malicious flows.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#traffic-analytics-schema
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries

## 3. Capabilities Provided

| Capability | Without Traffic Analytics | With Traffic Analytics | Official reference |
| --- | --- | --- | --- |
| Raw flow logs in Storage | Yes. | Yes. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#how-logging-works |
| Raw JSON format | Yes. | Yes, because raw logs remain in Storage. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format |
| Access to complete raw tuples | Yes. | Yes in Storage; not as one-to-one detail in `NTANetAnalytics`, which is aggregated. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Log Analytics table `NTANetAnalytics` | No, unless using custom ingestion not via Traffic Analytics. | Yes. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#traffic-analytics-schema |
| Public IP details in `NTAIpDetails` | No, you must enrich yourself. | Yes. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema |
| Ready-to-use KQL queries | No, you must build the query platform yourself. | Yes, Microsoft documents queries on `NTANetAnalytics` and `NTAIpDetails`. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries |
| Geography/security/topology enrichment | Not automatic. | Yes. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#how-traffic-analytics-works |
| Flow type such as `IntraVNet`, `InterVNet`, `S2S`, `AzurePublic`, `ExternalPublic`, `MaliciousFlow` | Not automatic. | Yes, in the Traffic Analytics schema. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#notes |
| Traffic Analytics workbook/dashboard | No. | Yes, via the Traffic Analytics experience and Log Analytics workbooks. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics |
| Native Traffic Analytics alerts | No. | No specific built-in alerts; custom alerts are created on Log Analytics. | https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-can-i-set-alerts-on-traffic-analytics-data |
| SIEM/IDS export | Yes, from raw logs. | Yes, from raw logs and/or from Log Analytics/Sentinel. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases |

## 4. How Service Consumption Changes

Without Traffic Analytics, the service is a raw data source. Consumption is oriented toward storage, compliance, export, and custom integration. You have full control over the original data, but you must build or purchase the parsing, normalization, enrichment, query, dashboard, detection, and alerting layer.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-does-flow-logging-do

With Traffic Analytics, the service becomes an operational network analytics solution. You can use KQL in Log Analytics, Microsoft-provided queries, workbooks, visualizations, enriched fields, and custom alerts. Consumption shifts from raw data engineering to the network operations workflow.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-can-i-set-alerts-on-traffic-analytics-data

The most important difference is this: without Traffic Analytics you have the rawest and most complete data, but it is less ready to use; with Traffic Analytics you have more consumable and enriched data, but it is aggregated. To see all individual flows, Microsoft indicates using the blob reference; in Log Analytics the user sees the reduced, aggregated record.

Official reference:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation

## 5. What You Can Do With One Solution And Not The Other

### With VNet Flow Logs Without Traffic Analytics You Can

- Retain raw JSON in Storage for audit, compliance, and forensics.
- Export data to SIEM, IDS, data lake, or custom visualization tools.
- Process the original format with your own pipelines.
- Maintain maximum raw granularity, including the source port in the flow tuple.
- Fully control retention, parsing, enrichment, and normalization.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases
- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-does-flow-logging-do

### With VNet Flow Logs Without Traffic Analytics You Do Not Automatically Get

- The `NTANetAnalytics` table in Log Analytics.
- The `NTAIpDetails` table for public IP intelligence.
- Geography, topology, and security enrichment managed by Microsoft.
- Microsoft-provided KQL queries on the Traffic Analytics schema.
- Traffic Analytics dashboards/workbooks.
- Custom alerts on Traffic Analytics data without first bringing the data into Log Analytics.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#how-traffic-analytics-works
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#traffic-analytics-schema
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries

### With VNet Flow Logs With Traffic Analytics You Can Additionally

- Visualize network activity across subscriptions and identify hot spots.
- Identify open ports, applications attempting internet access, and VMs communicating with rogue networks.
- Understand traffic patterns between Azure regions and the internet.
- Identify misconfigurations leading to failed connections.
- Query aggregated data with KQL in `NTANetAnalytics`.
- Analyze public IPs with WHOIS, location, DNS domain, and threat type in `NTAIpDetails`.
- Create custom alerts on Log Analytics queries.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-can-i-set-alerts-on-traffic-analytics-data

### With Traffic Analytics You Must Accept

- Additional costs for Traffic Analytics processing, on top of flow logs, storage, and Log Analytics.
- Non-real-time processing: default 60 minutes, optional 10 minutes; first dashboard display may take time.
- Aggregated data in Log Analytics, not all raw flow records one-to-one.
- Dependency on the Log Analytics workspace, DCR, and DCE managed by Traffic Analytics.
- Possible temporarily `Unknown` values until resource discovery completes.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-is-traffic-analytics-priced
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#i-configured-the-solution-why-am-i-not-seeing-anything-on-the-dashboard
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-are-the-other-resources-created-with-my-workspace
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#why-do-some-resources-appear-as-unknown-in-traffic-analytics

## 6. When to Choose VNet Flow Logs Without Traffic Analytics

Choose this mode when the primary requirement is to retain or export raw network evidence, and the organization already has a data or security platform that ingests and interprets JSON logs. It is suitable for teams with mature SIEM/IDS/data lake stacks, requirements for full control over parsing, or a need for maximum raw granularity.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases
- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format

Also choose it when you want to minimize additional Azure Monitor components and have no need for Traffic Analytics dashboards, automatic enrichment, or native KQL queries. In this scenario you still pay for flow log collection and storage, but not for Traffic Analytics processing.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-is-traffic-analytics-priced

## 7. When to Choose VNet Flow Logs With Traffic Analytics

Choose Traffic Analytics when the objective is operational network observability: dashboards, KQL, troubleshooting, security posture, top talkers, open ports, traffic distribution, malicious public IPs, failed connections, workbooks, and custom alerts. It is the best choice for customer demos, NOC/SOC, cloud operations, and environments where the value lies in immediate consumption, not just archival.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-can-i-set-alerts-on-traffic-analytics-data

Also choose it when you want to reduce custom enrichment work. Traffic Analytics enriches the reduced logs with geography, security, and topology; publishes fields such as `FlowType`, source/destination resources, region, load balancer, ExpressRoute, Private Endpoint, and UDR hop; and makes these data queryable in Log Analytics.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#how-traffic-analytics-works
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#traffic-analytics-schema
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema

## 8. Principal Architect Recommendation

For a **customer demo** or a **first enterprise operational model**, choose **VNet Flow Logs with Traffic Analytics**. Reason: it demonstrates immediate value with KQL, workbooks, enrichment, public IP intelligence, troubleshooting, and custom alerts. Still retain raw logs in Storage for audit, export, and point-in-time verification.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation
- https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries

For an **already mature data/security platform**, evaluate **VNet Flow Logs without Traffic Analytics** if the customer wants only raw evidence and already has parsing, enrichment, dashboard, detection, and retention pipelines in place. This choice reduces dependencies on Traffic Analytics, but shifts responsibility and complexity to the customer.

Official references:

- https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases
- https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-does-flow-logging-do

## 9. Decision Matrix

| Scenario | Recommended choice | Rationale | Official reference |
| --- | --- | --- | --- |
| Customer demo focused on visibility and troubleshooting | With Traffic Analytics | KQL, dashboards, enrichment, security/topology/geography insights. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#why-traffic-analytics |
| Raw archival only for audit | Without Traffic Analytics | Raw JSON in Storage, exportable and externally processable. | https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#what-does-flow-logging-do |
| SOC/NOC that wants queries and alerts | With Traffic Analytics | Data in Log Analytics and custom alerts based on queries. | https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions#how-can-i-set-alerts-on-traffic-analytics-data |
| Already standardized data lake/SIEM | Without Traffic Analytics or hybrid | Export raw to existing tools; Traffic Analytics optional for Azure-native operations. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#common-use-cases |
| Analysis of top talkers, subnets, regions, load balancers | With Traffic Analytics | Microsoft queries on `NTANetAnalytics` are already documented. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries |
| Need for maximum raw detail | Without Traffic Analytics, or with Traffic Analytics also consulting Storage | `NTANetAnalytics` is aggregated; raw records remain in blobs. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation |
| Minimum cost optimization | Depends | Without Traffic Analytics you avoid TA processing costs, but must account for storage and custom platform costs. | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#pricing |
| Security enrichment on public IPs and malicious flows | With Traffic Analytics | `NTAIpDetails` includes WHOIS, location, threat type, and DNS domain for public/malicious IPs. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#public-ip-details-schema |

## 10. Official Sources Consulted and Validated

- Virtual network flow logs overview: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview
- Traffic analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- Traffic analytics schema and data aggregation: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Use queries in traffic analytics: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- Network Watcher frequently asked questions: https://learn.microsoft.com/en-us/azure/network-watcher/frequently-asked-questions
