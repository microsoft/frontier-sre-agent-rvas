[< Previous Solution](./Solution-06.md) | **[Home](./README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Hybrid Ecosystem Telemetry

## Purpose

- Teach the hybrid-observability pattern: one investigation spans Azure Monitor and a non-Azure telemetry plane.
- This matters because real fleets rarely live entirely inside one monitoring stack.
- Expected time: 20–25 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the data split: Madrid lives in Azure-native telemetry; Berlin is third-party/OpenTelemetry via MCP.
- Reinforce that the Azure side may include Log Analytics plus Windows Event Logs/Linux Syslog reasoning, while Berlin comes from `@Access-to-3rd-Party-Logs`.
- Name the likely reusable skill for the Azure side: `connectivity-diagnostics` or related log/telemetry skills, depending on the agent’s routing.
- The Berlin MCP connector now ships in `Student/Resources/azure-sre-agent-config/connectors/` and is applied with `make connectors`.

## Expected Student Output

- Student gets a Madrid summary table with error counts and average response time from Azure-native telemetry.
- Berlin metrics are returned through the bundled MCP connector and compared with Azure-native telemetry.
- Student can name the skill or investigation structure used on the Azure side.

## Common Issues and Hints

- **Symptom:** Madrid query returns no recent data. **Fix:** run `make validate` again and widen the window from 1 hour to 6 hours.
- **Symptom:** Student gives a platform comparison with no source distinction. **Fix:** ask them to label which findings came from Azure Monitor vs. MCP.
- **Symptom:** `/agent access-to-3rd-party-logs` returns "subagent not found" or routes to the main agent instead. **Fix:** confirm the `access-to-3rd-party-logs` subagent was applied in Challenge 05 (`make subagents`) and that `make connectors` was re-run to register the `berlin-mcp` connector endpoint.

## Debrief Discussion Guide

- Why use MCP for Berlin instead of forcing everything into Azure Monitor? → Reflects real hybrid/partner telemetry boundaries.
- What breaks operationally if one monitoring plane is absent? → You still need graceful degradation, not silent omission.
- What did the agent add compared with a human manually switching dashboards? → Unified narrative and cross-source correlation.

## Success Criteria Notes

- Be strict that students distinguish Azure Monitor findings from MCP findings.
- Accept the skill-identification discussion at a conceptual level if the exact skill name is not exposed clearly in chat.
