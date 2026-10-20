[< Previous Challenge](./Challenge-01.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Connect and Ground the Fabric SRE Agent

> **Capabilities added in this challenge**: MCP Connection · Workspace Hosts · Fabric Skills · Agent Instructions

## Introduction

The agent needs a dependable path to the selected consumption data and to live
Fabric operational evidence. A clear identity boundary, read-only tools, and
current Fabric guidance are essential so its explanations can be checked and
repeated.

## Description

Using **SRE Agent Administrator** on your infrastructure-provisioned team agent,
configure it for the shared backend chosen in Challenge 01, using the matching
instructions and the agent-configuration sections of the setup guide:

First ask the agent to identify the shared source and explain a bounded
consumption question. Record the missing connectivity or grounding before
configuration, then compare with a fresh thread after configuration.
The [shared configuration reference](../Resources/fabric-sre-agent/README.md#agent-connection-and-configuration-reference)
provides the exact portal locations, endpoint/transport settings, identity
checks, router installation, and instruction procedure.

- Validate the coach-granted read access for the agent's user-assigned managed
  identity to the tenant APIs, workspaces, SQL endpoint, or KQL database required
  by that backend. Ask the coach to resolve missing grants; do not grant yourself
  tenant or capacity administration.
- Establish `fabric-mcp` and `sqlendpoint-operations-mcp`, select the required
  read-only tools, and prove actual calls work under the approved UAMI path.
  Distinguish remote Core's documented delegated OAuth from managed identity;
  escalate unsupported UAMI connections rather than silently switching identities.
- Configure the **SRE Agent** workspace Additional hosts with `prices.azure.com`
  and `*.database.fabric.microsoft.com`; for Capacity Events also include
  `*.kusto.fabric.microsoft.com`. Include the actual handed-over SQL hostname
  if it uses a different suffix, then test each path separately.
- Add and test the retail-price lookup tool; for Capacity Events validate the
  configured Eventhouse KQL path, not just Core MCP item discovery.
- Connect `https://github.com/microsoft/skills-for-fabric`, branch `main`, under
  Code Access and refresh it. Verify file-read access to
  `plugins/fabric-skills/skills/` and `plugins/fabric-skills/common/`.
- Install the shared Fabric skills router and attach exactly one backend's
  custom instructions, filling in its documented connection identifiers.
- Use the supplied complete [FUAM](../Resources/fabric-sre-agent/fuam/agent-instructions.md)
  or [Capacity Events](../Resources/fabric-sre-agent/capacity-events/agent-instructions.md)
  runtime instructions as the baseline, not both. Preserve its report contract,
  safe failure behavior, identity boundary, and native-unit rules while filling
  section 3.0 with the coach's approved scope and configuration.
- Verify discovery/query access with harmless read requests and confirm that
  write-capable tools and KQL management commands are unavailable.

## Success Criteria

- [ ] The agent's managed identity is authorized to read the chosen backend and the required Fabric metadata.
- [ ] Required read-only connectors are connected and return data from the intended workspace, endpoint, or Eventhouse.
- [ ] Connection ID, transport, enabled tools, and effective runtime identity are evidenced; a delegated sign-in is not misreported as UAMI access.
- [ ] The saved SRE Agent host configuration includes `prices.azure.com`, `*.database.fabric.microsoft.com`, and (for Capacity Events) `*.kusto.fabric.microsoft.com`; separate price/SQL/KQL checks pass as applicable.
- [ ] The pricing tool returns regional PAYG and reservation values from the Azure Retail Prices API.
- [ ] The active custom instructions match the chosen backend; the Fabric skills router reads current skill files from Code Access.
- [ ] The response names the full skill path and Mandatory dependencies actually read from synchronized `main`, with no web-copy or memory substitution.
- [ ] A change request is refused without attempting a write or falling back to another identity.
- [ ] **Explain to your coach** — what security boundary prevents a prompt from turning the investigation agent into a Fabric administrator?

## Learning Resources

- [FUAM agent setup guide](../Resources/fabric-sre-agent/fuam/README.md)
- [Capacity Events agent setup guide](../Resources/fabric-sre-agent/capacity-events/README.md)
- [Shared connection, skills, and instruction procedure](../Resources/fabric-sre-agent/README.md#agent-connection-and-configuration-reference)
- [Fabric Core MCP connection guide](https://learn.microsoft.com/rest/api/fabric/articles/mcp-servers/core-remote/get-started-core)
- [SRE Agent MCP setup](https://learn.microsoft.com/azure/sre-agent/mcp-connector)
- [Fabric skills repository](https://github.com/microsoft/skills-for-fabric)

## Tips

- A connected MCP tool is not proof that the agent's managed identity has the correct Fabric data-plane permissions.
- Never configure both backend-specific instruction files as global custom instructions on the same agent.
- SRE Agent Administrator governs agent configuration, not Fabric data access. Your agent's runtime identity remains read-only.
