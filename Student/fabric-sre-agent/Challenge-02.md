[< Previous Challenge](./Challenge-01.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Connect and Ground the Fabric SRE Agent

> **Capabilities added in this challenge**: Managed Identity · MCP Connectors · Fabric Skills

## Introduction

The agent needs a dependable path to the selected consumption data and to live
Fabric operational evidence. A clear identity boundary, read-only tools, and
current Fabric guidance are essential so its explanations can be checked and
repeated.

## Description

Configure the Azure SRE Agent for the backend chosen in Challenge 01, using the
matching instructions and setup guide:

- Grant the agent's user-assigned managed identity only the tenant, workspace,
  capacity, SQL endpoint, or KQL read permissions required by that backend.
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
