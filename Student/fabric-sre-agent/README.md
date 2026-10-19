**[Home](../../README.md)**

# Fabric SRE Agent Track

This track develops a read-only Azure SRE Agent for Microsoft Fabric FinOps
and root-cause analysis (RCA). It supports either of the two consumption-data
backends in [`../Resources/fabric-sre-agent/`](../Resources/fabric-sre-agent/README.md):

| Backend | Consumption detail | Main trade-off |
|---|---|---|
| FUAM | Daily by item and operation; notebook execution CU can be derived from Spark allocation | Lower ongoing Fabric cost; less precise for individual non-Spark executions |
| Capacity events | Exact per-operation CU from streamed capacity operation events | Better execution-level attribution; Eventstream and Eventhouse run continuously |

Choose one backend for an agent. The two backend-specific instruction files are
not interchangeable; custom instructions apply to the whole agent. The
challenges compare their precision, freshness, history, and operating-cost
trade-offs while keeping the analysis workflow consistent.

The coach deploys **both backends once**, shares the relevant items with the
audience, and grants read access to each team agent's managed identity.
The infrastructure deliverable provisions the shared Fabric capacity and a
separate SRE Agent per team. Every participant configuring an agent needs
**SRE Agent Administrator** on that agent. Students validate shared telemetry
and configure agent capabilities; they do not provision telemetry stacks or
change the shared infrastructure.

The agent uses Fabric read APIs, the SQL endpoint or Eventhouse, Spark
monitoring APIs, the live `microsoft/skills-for-fabric` repository, and a
pricing tool backed by the Azure Retail Prices API. Cost values are
standalone-equivalent CU-based estimates, not an allocation of an actual
capacity invoice. The agent remains read-only.

## Challenges

| Challenge | Focus |
|---|---|
| [00](./Challenge-00.md) | Prerequisites and access readiness |
| [01](./Challenge-01.md) | Select and validate a shared consumption backend |
| [02](./Challenge-02.md) | Connect and ground the agent |
| [03](./Challenge-03.md) | Validate the cost calculation and precision |
| [04](./Challenge-04.md) | Explain spend by workspace and item |
| [05](./Challenge-05.md) | Validate model choice and EU data residency |
| [06](./Challenge-06.md) | Validate live skills and backend agent instructions |
| [07](./Challenge-07.md) | Optimize a measured Spark workload |
| [08](./Challenge-08.md) | Assess monitoring coverage and capacity context |
| [09](./Challenge-09.md) | Build and present a production-ready Fabric SRE agent |

**Coaches:** see [`Coach/fabric-sre-agent/README.md`](../../Coach/fabric-sre-agent/README.md).

## Resources

The backend deployment guides, agent instructions, sample notebook, pricing
tool, and shared skills router are under
[`Student/Resources/fabric-sre-agent/`](../Resources/fabric-sre-agent/README.md).
Its [configuration reference](../Resources/fabric-sre-agent/README.md#agent-connection-and-configuration-reference)
covers exact MCP settings, SRE Agent outbound hosts, synchronized Code Access,
router installation, backend instructions, and Azure OpenAI/Anthropic residency.
