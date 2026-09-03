[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Application Dependency Mapping

## Purpose

- Show how live telemetry can be turned into topology: dependencies, call counts, latency, and hotspots.
- This challenge advances students from “what is broken?” to “what depends on what?”
- Expected time: 25 minutes.

## Mini-Lecture (3–5 min before challenge)

- Explain the difference between Application Insights `requests` and `dependencies`: entry-point work vs downstream calls.
- Call out the desired output formats: Mermaid or ASCII diagram plus a summary table.
- Mention the Berlin caveat again: the Berlin Parking API's OpenTelemetry data is outside Grubify's Application Insights and is fetched separately via the Berlin MCP connector (deployed in Challenge 04/07 as `berlin-monitoring-v6`).
- Mention that the workshop bundle now includes `/agent dependency-analyzer` for this challenge.
- Coach hint: dependency maps are often sparse until telemetry exists, so `make food-traffic` matters.

## Expected Student Output

- A dependency diagram for Grubify (Sample Food) showing frontend/backend relationships with calls and average response times.
- A matching table highlighting highest error rate and any dependencies above 500 ms.
- The Berlin Parking API's OpenTelemetry data is appended as a separately-sourced dependency, blended in from a connector distinct from Application Insights.
- Student can explain why `dependencies` telemetry is the primary map-building source.

## Common Issues and Hints

- **Symptom:** Diagram is too generic or missing numbers. **Fix:** ask the student to request call counts and average response time explicitly.
- **Symptom:** Dependency table is empty. **Fix:** run `make food-traffic` and retry after ~5 minutes of ingestion.
- **Symptom:** Berlin is omitted without comment. **Fix:** coach should require an explicit note that Berlin telemetry comes from the OpenTelemetry MCP connector, not Application Insights, and confirm the connector was applied in an earlier challenge.

## Debrief Discussion Guide

- Why are `dependencies` better than `requests` for topology inference? → They show outbound calls and downstream targets.
- What does a single point of failure look like in a telemetry-derived graph? → Central node with no alternative path.
- Why is adding Berlin separately useful? → It exposes the boundary between first-party and third-party observability.

## Success Criteria Notes

- Accept Mermaid, ASCII, or a clearly structured textual graph.
- Be strict that the output includes metrics, not just nodes.
- Missing Berlin should not block completion if the student documents the connector gap clearly.
