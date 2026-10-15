[< Previous Challenge](./Challenge-01.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Connect and Ground the Fabric SRE Agent

> **Capabilities added in this challenge**: Managed Identity · MCP Connectors · Fabric Skills

## Introduction

The agent needs a dependable path to the selected consumption data and to live
Fabric operational evidence. A clear identity boundary, read-only tools, and
current Fabric guidance are essential so its explanations can be checked and
repeated.

## Description

Using **SRE Agent Administrator** on your infrastructure-provisioned team agent,
configure it for the shared backend chosen in Challenge 01, using the matching
instructions and the agent-configuration sections of the setup guide:

- Validate the coach-granted read access for the agent's user-assigned managed
  identity to the tenant APIs, workspaces, SQL endpoint, or KQL database required
  by that backend. Ask the coach to resolve missing grants; do not grant yourself
  tenant or capacity administration.
- Connect the supported Fabric MCP and SQL endpoint MCP. For Capacity Events,
  configure Eventhouse query access through the documented KQL path.
- Add the retail-price lookup tool and allow only the required outbound price
  domain; allow the Eventhouse query domain when using Capacity Events.
- Install the shared Fabric skills router and attach exactly one backend's
  custom instructions, filling in its documented connection identifiers.
- Verify discovery/query access with harmless read requests and confirm that
  write-capable tools and KQL management commands are unavailable.

## Success Criteria

- [ ] The agent's managed identity is authorized to read the chosen backend and the required Fabric metadata.
- [ ] Required read-only connectors are connected and return data from the intended workspace, endpoint, or Eventhouse.
- [ ] The pricing tool returns regional PAYG and reservation values from the Azure Retail Prices API.
- [ ] The active custom instructions match the chosen backend; the Fabric skills router reads current skill files from Code Access.
- [ ] A change request is refused without attempting a write or falling back to another identity.
- [ ] **Explain to your coach** — what security boundary prevents a prompt from turning the investigation agent into a Fabric administrator?

## Learning Resources

- [FUAM agent setup guide](../Resources/fabric-sre-agent/fuam/README.md)
- [Capacity Events agent setup guide](../Resources/fabric-sre-agent/capacity-events/README.md)
- [Fabric MCP server](https://github.com/microsoft/fabric-mcp)
- [Fabric skills repository](https://github.com/microsoft/skills-for-fabric)

## Tips

- A connected MCP tool is not proof that the agent's managed identity has the correct Fabric data-plane permissions.
- Never configure both backend-specific instruction files as global custom instructions on the same agent.
- SRE Agent Administrator governs agent configuration, not Fabric data access. Your agent's runtime identity remains read-only.
