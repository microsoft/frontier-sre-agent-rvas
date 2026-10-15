[< Previous Solution](./Solution-01.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Connect and Ground the Fabric SRE Agent

## Purpose

- Validate the managed-identity read path, source connector, price tool, and live Fabric skill grounding.
- Demonstrate that the agent declines changes rather than bypassing its read-only contract.
- Expected time: 45–60 minutes.

## Mini-Lecture (8 min before challenge)

- The agent's managed identity is distinct from a human's interactive sign-in.
- The SQL endpoint MCP and Fabric MCP serve separate query and item/API responsibilities.
- Capacity Events KQL uses the documented authenticated REST path; it does not imply KQL management rights.
- The router should load a current official skill from Code Access for the relevant operation.
- Backend instructions must match exactly one configured source.
- Participants need SRE Agent Administrator on their team agent. The coach
  owns tenant settings and shared backend grants; runtime access remains read-only.

## Expected Student Output

- Read-only connector(s) work against the selected backend.
- The pricing tool returns a regional rate and retrieval timestamp.
- The right source-specific instructions are saved and identifiers are populated.
- The agent identifies the skill file it consulted and refuses a safe test request to change data.

## Common Issues and Hints

- **Symptom:** Fabric MCP returns `401` or `403`. **Fix:** verify the Fabric public API tenant setting and that the agent UAMI has access to the relevant workspace, then test one harmless read operation.
- **Symptom:** SQL endpoint `execute_query` returns permission denied. **Fix:** the coach verifies the UAMI's telemetry workspace/SQL read grants; the team confirms the correct SQL endpoint server/database are configured.
- **Symptom:** Eventhouse KQL returns `403`. **Fix:** check workspace access and database-level viewer permissions for the UAMI; do not use a human token as a runtime fallback.
- **Symptom:** Price tool fails to reach `prices.azure.com`. **Fix:** add the documented allowed host and verify the tool's code and input region.
- **Symptom:** Agent gives stale instructions without reading Code Access. **Fix:** confirm repository sync and require it to name the live skill file it read.

## Debrief Discussion Guide

- Which authentication boundary does each connector represent?
- What would be lost if the agent silently used a human's delegated token?
- Why is a prompt refusal useful but not a replacement for read-only authorization?

## Success Criteria Notes

- Be strict that runtime calls use the agent identity and the expected source.
- Require a visible refusal and no alternative write path.
- Accept transport differences for the Fabric MCP if the documented UAMI path is healthy.
