# KQL Catalog

This catalog documents the KQL queries for the Azure VNet Flow Logs + Traffic Analytics demo. Each query includes its purpose, the full query, a line-by-line explanation, the parameters used, the key fields, the functions, and the role of the query in troubleshooting.

Official sources:

- VNet Flow Logs: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview
- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Traffic Analytics queries: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries

## VNet Flow Logs And Traffic Analytics

VNet Flow Logs records IP traffic at Layer 4 and writes raw JSON logs to the Storage Account. The raw logs describe traffic tuples with timestamp, source IP, destination IP, ports, protocol, direction, flow status, encryption status, bytes, and packets.

Traffic Analytics reads the raw logs from the Storage Account, aggregates them, and enriches them in Log Analytics. For VNet Flow Logs the main table is `NTANetAnalytics`; for details on public IPs use `NTAIpDetails`.

### Outbound, Return, TCP And UDP

VNet Flow Logs and Traffic Analytics are not packet captures: they do not show payload, application handshake, or every packet. They show flows and aggregated counters.

For a `SrcIp -> DestIp` tuple, the main fields are:

| Field | Meaning |
| --- | --- |
| `BytesSrcToDest` | Bytes from the source to the destination of the tuple. |
| `BytesDestToSrc` | Bytes from the destination to the source of the same tuple. |
| `PacketsSrcToDest` | Packets from the source to the destination. |
| `PacketsDestToSrc` | Packets from the destination to the source. |
| `FlowDirection` | Inbound/outbound direction relative to the capture point. |
| `L4Protocol` | Protocol: `T` for TCP, `U` for UDP. |

So yes: when return traffic is observed and aggregated into the same flow, Traffic Analytics exposes both the forward and return directions via the `SrcToDest` and `DestToSrc` counters. This applies to both TCP and UDP as byte and packet metrics. The difference is semantic: TCP is connection-oriented; UDP is stateless and should not be interpreted as a session with handshake and teardown.

The return direction does not always appear as a second row with inverted IPs. Often the response is inside the same tuple via `BytesDestToSrc` and `PacketsDestToSrc`. To find independent conversations in the opposite direction, filter both combinations: `A -> B` and `B -> A`.

## Lab Conventions

| Name | IP | Role |
| --- | --- | --- |
| Client | `10.20.1.10` | VM that generates demo traffic. |
| Internal Load Balancer | `10.20.2.100` | Internal web frontend. |
| API | `10.30.1.10` | Application endpoint in the data spoke. |
| DB listener | `10.30.2.10` | TCP 5432 listener for the database scenario. |
| Azure Firewall | Terraform output `azure_firewall_private_ip` | Centralized next hop for inter-spoke and Internet-bound traffic. |
| NVA Linux | `10.10.2.10` | Educational reference appliance; not the default path for the demo. |

## Query 1: Ingestion Verification

**Purpose:** verify that Traffic Analytics is writing records to the Log Analytics workspace.

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Selects the table of flows enriched by Traffic Analytics. |
| `| where SubType == "FlowLog"` | Filters only flow log records. `where` keeps rows that satisfy the condition, `SubType` identifies the subtype, `==` checks equality, `"FlowLog"` is the expected value. |
| `| take 10` | Returns at most 10 rows. Used for a quick smoke test. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `NTANetAnalytics` | Table | Flow data source. |
| `where` | Operator | Reduces the dataset to the correct records. |
| `SubType` | Field | Distinguishes flow logs from other records. |
| `take` | Operator | Limits the output for quick verification. |
| `10` | Parameter | Maximum number of rows. |

## Query 2: Top Talkers

**Purpose:** identify the conversations with the highest volume in the last 24 hours.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowType
| top 20 by TotalBytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Queries the enriched flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Keeps only recent flow logs. `and` requires both conditions; `ago(24h)` calculates the current moment minus 24 hours. |
| `| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowType` | Groups by endpoint, port, protocol, and traffic type; sums forward and return bytes. |
| `| top 20 by TotalBytes desc` | Shows the 20 largest conversations, from largest to smallest. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `TimeGenerated` | Datetime field | Defines the time window. |
| `ago(24h)` | Function | Creates a dynamic 24-hour window. |
| `summarize` | Operator | Aggregates many records into conversations. |
| `sum()` | Aggregate function | Calculates the total volume. |
| `BytesSrcToDest`, `BytesDestToSrc` | Numeric fields | Measure forward and return traffic. |
| `by` | Clause | Defines the grouping keys. |
| `SrcIp`, `DestIp`, `DestPort` | Fields | Identify endpoint and service. |
| `L4Protocol` | Field | Distinguishes TCP and UDP. |
| `FlowType` | Field | Classifies internal, public, etc. traffic. |
| `top 20`, `desc` | Operators/parameters | Limit and sort by priority. |

## Query 3: Denied Flows By Rule

**Purpose:** find blocked traffic and the responsible rules.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, AclGroup, SrcIp, DestIp, DestPort, L4Protocol
| order by DeniedFlows desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Uses the enriched flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Limits to flow logs from the last 24 hours. |
| `| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0` | Keeps only denied flows. The `FlowStatus` field uses the full word `Denied`/`Allowed` (not `D`/`A`); the OR on the `DeniedInFlows`/`DeniedOutFlows` counters makes the match robust. |
| `| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, AclGroup, SrcIp, DestIp, DestPort, L4Protocol` | Sums inbound and outbound denies by rule, ACL/NSG group, endpoint, port, and protocol. |
| `| order by DeniedFlows desc` | Brings rules with the most blocks to the top. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `FlowStatus` | Field | Separates allow and deny. |
| `"D"` | Parameter | Selects blocked traffic. |
| `DeniedInFlows`, `DeniedOutFlows` | Numeric fields | Quantify inbound and outbound blocks. |
| `AclRule` | Field | Shows the responsible rule. |
| `AclGroup` | Field | Indicates the group/NSG to investigate. |
| `order by` | Operator | Prioritizes triage. |

## Query 4: Subnet-To-Subnet Conversations

**Purpose:** see which subnets communicate and on which ports/protocols.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where isnotempty(SrcSubnet) and isnotempty(DestSubnet)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcSubnet, DestSubnet, L4Protocol, DestPort
| order by TotalBytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Queries enriched flows with subnet information. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent flow logs. |
| `| where isnotempty(SrcSubnet) and isnotempty(DestSubnet)` | Excludes rows without a source or destination subnet. |
| `| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcSubnet, DestSubnet, L4Protocol, DestPort` | Aggregates total bytes between subnets, separated by protocol and port. |
| `| order by TotalBytes desc` | Shows the most trafficked paths first. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `isnotempty()` | Function | Verifies that a field has a value. |
| `SrcSubnet`, `DestSubnet` | Fields | Identify network segments. |
| `and` | Boolean operator | Requires both subnets. |

## Query 5: Internet And Public Traffic

**Purpose:** identify traffic toward or from public IPs and traffic classified as malicious.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowType in ("ExternalPublic", "AzurePublic", "MaliciousFlow")
| summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, SrcIp, DestIp, DestPort, FlowStatus
| order by Bytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Limits the dataset. |
| `| where FlowType in ("ExternalPublic", "AzurePublic", "MaliciousFlow")` | Keeps only public or risky categories. `in` checks membership in a list. |
| `| summarize Flows=..., Bytes=... by FlowType, SrcIp, DestIp, DestPort, FlowStatus` | Aggregates flow count and bytes by category, endpoint, port, and status. |
| `| order by Bytes desc` | Sorts by volume. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `FlowType` | Field | Classifies the traffic. |
| `ExternalPublic` | Value | Public internet, not Azure/Microsoft. |
| `AzurePublic` | Value | Azure/Microsoft public services. |
| `MaliciousFlow` | Value | IPs classified as malicious. |
| `AllowedInFlows`, `AllowedOutFlows` | Fields | Count allowed flows. |
| `DeniedInFlows`, `DeniedOutFlows` | Fields | Count denied flows. |

## Query 6: Public IP Details

**Purpose:** enrich the analysis of public IPs with ownership, geography, threat type, and domain.

```kql
NTAIpDetails
| where TimeGenerated > ago(24h)
| summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType, DNSDomain
| order by Count desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTAIpDetails` | Uses the table with public IP details. |
| `| where TimeGenerated > ago(24h)` | Considers the most recent records. |
| `| summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType, DNSDomain` | Counts occurrences by category, IP detail, location, threat, and domain. |
| `| order by Count desc` | Shows the most frequent IPs/details first. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `NTAIpDetails` | Table | Source for public IP details. |
| `count()` | Aggregate function | Counts records. |
| `PublicIPDetails` | Field | Indicates ownership or service. |
| `Location` | Field | Adds geographic context. |
| `ThreatType` | Field | Highlights potential threats. |
| `DNSDomain` | Field | Aids security investigation. |

## Query 7: UDR And Asymmetric Routing Signal

**Purpose:** analyze client/DB traffic during a UDR scenario on a centralized Azure Firewall baseline.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp in ("10.20.1.10", "10.30.2.10") or DestIp in ("10.20.1.10", "10.30.2.10")
| project TimeGenerated, SrcIp, DestIp, DestPort, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, IsFlowCapturedAtUDRHop, SrcSubnet, DestSubnet
| order by TimeGenerated desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Queries enriched flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent records. |
| `| where SrcIp in (...) or DestIp in (...)` | Includes records where the client or DB are source or destination. |
| `| project TimeGenerated, ...` | Shows only columns useful for troubleshooting. `project` selects columns and removes noise. |
| `| order by TimeGenerated desc` | Shows the most recent records first. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `10.20.1.10`, `10.30.2.10` | IP parameters | Endpoints of the conversation to investigate. |
| `or` | Boolean operator | Includes both source/destination roles. |
| `FlowDirection` | Field | Helps read inbound/outbound. |
| `IsFlowCapturedAtUDRHop` | Field | Useful signal in route table/firewall/NVA scenarios. |
| `SrcSubnet`, `DestSubnet` | Fields | Show the involved segments. |

## Query 8: Load Balancer Distribution

**Purpose:** observe traffic associated with the internal load balancer.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcLoadBalancer contains "web" or DestLoadBalancer contains "web" or DestIp == "10.20.2.100"
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestLoadBalancer, SrcLoadBalancer
| order by TotalBytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent flow logs. |
| `| where SrcLoadBalancer contains "web" or DestLoadBalancer contains "web" or DestIp == "10.20.2.100"` | Finds records linked to the load balancer by name or frontend IP. |
| `| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestLoadBalancer, SrcLoadBalancer` | Aggregates traffic by endpoint and load balancer. |
| `| order by TotalBytes desc` | Sorts by volume. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `SrcLoadBalancer`, `DestLoadBalancer` | Fields | Azure resource enrichment. |
| `contains` | String operator | Searches for a substring in the name. |
| `"web"` | String parameter | Match on the demo name. |
| `"10.20.2.100"` | IP parameter | Frontend IP of the ILB. |

## Query 9: Source To Destination Traffic

**Purpose:** isolate a specific direction, for example client to database on TCP 5432.

```kql
let SourceIp = "10.20.1.10";
let DestinationIp = "10.30.2.10";
let DestinationPort = 5432;
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp == SourceIp and DestIp == DestinationIp and DestPort == DestinationPort
| summarize Flows=sum(AllowedOutFlows + AllowedInFlows + DeniedOutFlows + DeniedInFlows), BytesForward=sum(BytesSrcToDest), BytesReturn=sum(BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, AclRule
| order by BytesForward desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `let SourceIp = "10.20.1.10";` | Defines a reusable parameter for the source IP. |
| `let DestinationIp = "10.30.2.10";` | Defines the parameter for the destination IP. |
| `let DestinationPort = 5432;` | Defines the port of the service to search for. |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Uses only recent flow logs. |
| `| where SrcIp == SourceIp and DestIp == DestinationIp and DestPort == DestinationPort` | Filters exactly the source-to-destination direction and port. |
| `| summarize ... by SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, AclRule` | Calculates flows, forward bytes, and return bytes, separated by protocol, status, and rule. |
| `| order by BytesForward desc` | Sorts by bytes in the requested direction. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `let` | Construct | Parameterizes IP and port. |
| `SourceIp`, `DestinationIp`, `DestinationPort` | Variables | Make the query reusable. |
| `BytesForward` | Alias | Sums `BytesSrcToDest`, i.e. the requested direction. |
| `BytesReturn` | Alias | Sums `BytesDestToSrc`, i.e. the response observed in the same flow. |
| `AclRule` | Field | Links traffic to NSG/admin rules. |

## Query 10: Reverse Traffic From Destination To Source

**Purpose:** find separate records in the opposite direction, for example DB to client.

```kql
let SourceIp = "10.20.1.10";
let DestinationIp = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp == DestinationIp and DestIp == SourceIp
| project TimeGenerated, SrcIp, DestIp, DestPort, L4Protocol, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, PacketsSrcToDest, PacketsDestToSrc, AclRule
| order by TimeGenerated desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `let SourceIp = "10.20.1.10";` | Keeps the original endpoint A. |
| `let DestinationIp = "10.30.2.10";` | Keeps the original endpoint B. |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent flow logs. |
| `| where SrcIp == DestinationIp and DestIp == SourceIp` | Inverts source and destination relative to the previous query. |
| `| project ...` | Shows technical fields for comparison. |
| `| order by TimeGenerated desc` | Shows the most recent records first. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `SrcIp == DestinationIp` | Condition | The original destination becomes the source. |
| `DestIp == SourceIp` | Condition | The original source becomes the destination. |
| `PacketsSrcToDest`, `PacketsDestToSrc` | Fields | Measure packets in the current direction and the return. |
| `project` | Operator | Selects diagnostic columns. |

Note: the absence of reverse records does not automatically mean the absence of return traffic; the return may already be in the `BytesDestToSrc` counters of the direct query.

## Query 11: Normalized Bidirectional View

**Purpose:** show A->B and B->A in a single view.

```kql
let EndpointA = "10.20.1.10";
let EndpointB = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)
| extend DirectionLabel = case(SrcIp == EndpointA and DestIp == EndpointB, "A-to-B", SrcIp == EndpointB and DestIp == EndpointA, "B-to-A", "Other")
| summarize Records=count(), ForwardBytes=sum(BytesSrcToDest), ReturnBytes=sum(BytesDestToSrc), TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by DirectionLabel, SrcIp, DestIp, DestPort, L4Protocol, FlowStatus
| order by TotalBytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `let EndpointA = "10.20.1.10";` | Defines the first endpoint. |
| `let EndpointB = "10.30.2.10";` | Defines the second endpoint. |
| `NTANetAnalytics` | Queries the flow table. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent flow logs. |
| `| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)` | Includes both directions. Parentheses avoid ambiguity between `and` and `or`. |
| `| extend DirectionLabel = case(...)` | Adds a human-readable label for the logical direction. |
| `| summarize Records=count(), ForwardBytes=sum(BytesSrcToDest), ReturnBytes=sum(BytesDestToSrc), TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by ...` | Aggregates records, forward bytes, return bytes, and total by direction, endpoint, port, protocol, and status. |
| `| order by TotalBytes desc` | Sorts by total volume. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `EndpointA`, `EndpointB` | Variables | Pair of endpoints to compare. |
| `extend` | Operator | Adds computed columns. |
| `case()` | Function | Maps conditions to labels. |
| `count()` | Aggregate function | Counts records per group. |
| `ForwardBytes`, `ReturnBytes`, `TotalBytes` | Aliases | Separate forward, return, and total volume. |

## Query 12: TCP And UDP Comparison Between Two Endpoints

**Purpose:** verify whether a pair communicates via TCP, UDP, or both.

```kql
let EndpointA = "10.20.1.10";
let EndpointB = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)
| summarize Flows=sum(AllowedInFlows + AllowedOutFlows + DeniedInFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc), Packets=sum(PacketsSrcToDest + PacketsDestToSrc) by L4Protocol, DestPort, FlowStatus
| extend ProtocolName = case(L4Protocol == "T", "TCP", L4Protocol == "U", "UDP", "Other")
| order by Bytes desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `let EndpointA = "10.20.1.10";` | First endpoint. |
| `let EndpointB = "10.30.2.10";` | Second endpoint. |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent data. |
| `| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)` | Includes both directions. |
| `| summarize Flows=..., Bytes=..., Packets=... by L4Protocol, DestPort, FlowStatus` | Aggregates flows, bytes, and packets by protocol, port, and status. |
| `| extend ProtocolName = case(L4Protocol == "T", "TCP", L4Protocol == "U", "UDP", "Other")` | Translates the protocol code into a human-readable name. |
| `| order by Bytes desc` | Sorts by volume. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `L4Protocol == "T"` | Condition | Identifies TCP. |
| `L4Protocol == "U"` | Condition | Identifies UDP. |
| `PacketsSrcToDest`, `PacketsDestToSrc` | Fields | Measure forward and return packets. |
| `ProtocolName` | Alias | Makes the output readable in the demo. |

## Query 13: Temporal Details Of A Conversation

**Purpose:** see when the aggregated flow starts and ends within the Traffic Analytics processing interval.

```kql
let EndpointA = "10.20.1.10";
let EndpointB = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)
| project TimeGenerated, FlowIntervalStartTime, FlowIntervalEndTime, FlowStartTime, FlowEndTime, SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, CompletedFlows
| order by FlowStartTime desc
```

### Line-By-Line Explanation

| Line | Explanation |
| --- | --- |
| `let EndpointA = "10.20.1.10";` | First endpoint. |
| `let EndpointB = "10.30.2.10";` | Second endpoint. |
| `NTANetAnalytics` | Queries the flows. |
| `| where SubType == "FlowLog" and TimeGenerated > ago(24h)` | Filters recent flow logs. |
| `| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)` | Keeps both directions. |
| `| project TimeGenerated, FlowIntervalStartTime, FlowIntervalEndTime, FlowStartTime, FlowEndTime, SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, CompletedFlows` | Shows temporal and identifying columns for the flow. |
| `| order by FlowStartTime desc` | Sorts from the most recent flow. |

### Elements Used

| Element | Type | Purpose In Context |
| --- | --- | --- |
| `FlowIntervalStartTime`, `FlowIntervalEndTime` | Datetime fields | Delimit the Traffic Analytics processing bucket. |
| `FlowStartTime`, `FlowEndTime` | Datetime fields | Show the first and last occurrence of the flow. |
| `CompletedFlows` | Numeric field | Indicates completed flows when available. |
| `project` | Operator | Reduces the output to useful columns. |

## Query 14: No-Data Diagnostic

**Purpose:** determine whether the problem is a complete absence of data, an incorrect time window, or a lack of recent records.

```kql
NTANetAnalytics
| where TimeGenerated > ago(48h)
| summarize Records=count(), FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by SubType, FlowType, TargetResourceId
| order by LastSeen desc
```

### How To Interpret It

| Result | Interpretation | Action |
| --- | --- | --- |
| No rows | Traffic Analytics has not yet written data or is not enabled. | Check flow logs, `traffic_analytics.enabled`, workspace, and the 10/60-minute cycle. |
| Old rows but no recent ones | Ingestion stopped or no traffic generated in the window. | Generate baseline traffic and check raw blobs. |
| Missing target | The expected VNet/subnet/NIC is not in the target set. | Verify `target_resource_id` and VNet/subnet/NIC scope. |

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema#data-aggregation

## Query 15: Duplicate-Safe Bytes By Device

**Purpose:** avoid double counting when a flow is captured at multiple points in the conversation.

```kql
let DeviceIp = "10.20.1.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == DeviceIp and FlowDirection == "Outbound") or (DestIp == DeviceIp and FlowDirection == "Inbound")
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc), Records=count() by SrcIp, DestIp, DestPort, L4Protocol, FlowDirection, MacAddress
| order by TotalBytes desc
```

### How To Interpret It

| Field | Why It Is Needed |
| --- | --- |
| `FlowDirection` | Distinguishes the direction relative to the capture point. |
| `MacAddress` | Helps distinguish the device on which the flow is captured. |
| `Records` | Highlights whether the conversation appears more than once. |

Source: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries#prevent-duplicate-records

## Query 16: Private Endpoint Visibility

**Purpose:** find traffic toward Private Endpoints from the source VM side.

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where isnotempty(PrivateEndpointResourceId) or DestSubnet has "privatelink" or DestIp startswith "10.30.3."
| project TimeGenerated, SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, FlowDirection, PrivateEndpointResourceId, SrcSubnet, DestSubnet, BytesSrcToDest, BytesDestToSrc
| order by TimeGenerated desc
```

### How To Interpret It

| Result | Interpretation | Action |
| --- | --- | --- |
| `PrivateEndpointResourceId` populated | Traffic Analytics has enriched the flow with the Private Endpoint reference. | Correlate with the PaaS resource and private DNS. |
| Only private IPs/subnets | Enrichment incomplete or different naming. | Validate the private endpoint IP from Terraform outputs/portal. |
| No rows | No recent traffic or query too narrow. | Generate traffic toward the private endpoint and broaden the IP/subnet filter. |

Note: Microsoft documents that traffic is not recorded at the Private Endpoint itself; it must be observed from the source side. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic

## Quick Reference For KQL Functions Used

| Function/operator | How it works | When to use it |
| --- | --- | --- |
| `where` | Filters rows based on a condition. | Reduce the dataset by time, IP, status, or traffic type. |
| `summarize` | Aggregates rows into groups. | Calculate bytes, packets, flows, and counts. |
| `sum()` | Sums numeric values. | Calculate total volumes. |
| `count()` | Counts rows. | Understand how many rows make up a group. |
| `by` | Defines the grouping keys. | Separate results by IP, port, protocol, rule. |
| `order by` | Sorts results. | Bring the most relevant records to the top. |
| `top N by` | Sorts and limits to the top N records. | Show top talkers or top denies. |
| `ago()` | Calculates a relative timestamp. | Create dynamic time windows. |
| `isnotempty()` | Verifies that a field is not empty. | Eliminate records without useful enrichment. |
| `in (...)` | Checks membership in a list. | Filter multiple values at once. |
| `contains` | Searches for a substring. | Search for partial resource names. |
| `project` | Chooses columns to display. | Make the output readable. |
| `extend` | Adds computed columns. | Create labels such as `A-to-B` or `ProtocolName`. |
| `case()` | Returns different values based on conditions. | Translate codes into readable labels. |
| `let` | Defines variables or subqueries. | Parameterize IPs, ports, and time windows. |

## Sample Food Ordering App: Container Apps Logs

These queries do not use `NTANetAnalytics`, because Azure Container Apps is not supported by VNet Flow Logs. For the Sample Food Ordering App the correct approach is Container Apps logs + Application Insights. Source: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services

### Query 17: Sample Food HTTP Errors

```kql
let AppName = "<sample-food-api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| summarize Errors=count(), SampleStatusCodes=make_set(StatusCode, 5), P95DurationMs=percentile(RequestDuration, 95) by Method, Path, ResponseCodeDetails
| order by Errors desc
```

### Query 18: Sample Food Latency

```kql
let AppName = "<sample-food-api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| summarize Requests=count(), P50=percentile(RequestDuration, 50), P95=percentile(RequestDuration, 95), P99=percentile(RequestDuration, 99) by Path
| order by P95 desc
```

### Query 19: Sample Food Console Logs

```kql
let AppName = "<sample-food-api-container-app-name>";
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(2h)
| where ContainerAppName_s == AppName
| project TimeGenerated, RevisionName_s, ContainerName_s, Log_s
| order by TimeGenerated desc
| take 100
```

### Query 20: Sample Food System Logs

```kql
let AppName = "<sample-food-api-container-app-name>";
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == AppName
| where Log_s has_any ("ErrImagePull", "ContainerCrashing", "Timeout", "Error", "revision")
| project TimeGenerated, EnvironmentName_s, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated desc
```

Source Container Apps logs: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
