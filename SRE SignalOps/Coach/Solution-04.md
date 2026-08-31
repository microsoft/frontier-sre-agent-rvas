[< Previous Solution](./Solution-03.md) | **[Home](./README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Discover Connected Systems

## Purpose

Turn configured connectors into an evidence-backed reachability map. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Configured, authenticated, reachable, and authorized are four different states.

## Expected Student Output

- A connector matrix with configured state, authentication, authorization, observed read tests, timestamps, scopes, and failure classifications.
- An explicit `unverified` label wherever a live read was not completed.

## Coach Runbook

1. Ask the student to inventory connectors without displaying credentials.
2. Require one harmless read per connector and capture timestamp, scope, and returned object type.
3. Classify failures as configuration, authentication, authorization, network, tool discovery, or source-data failure.
4. Stop and rotate credentials if any token or secret appears in output.

## Common Issues and Hints

- **Symptom:** Connector shows healthy but reads fail. **Fix:** test authentication and authorization separately.
- **Symptom:** Secrets appear in output. **Fix:** redact and rotate exposed values immediately.
- **Symptom:** Agent omits MCP tools. **Fix:** request tool discovery from each MCP endpoint.

## Debrief Discussion Guide

1. What is the strongest connectivity evidence? → A current, harmless read that returns expected scoped data.
2. How should stale reads be labeled? → With the timestamp and an explicit stale or unverified state.
3. Which connectors can write? → Only those whose discovered tools and grants explicitly allow writes; connector health alone proves nothing.

## Success Criteria Notes

- **Require:** every connector has a current read result or explicit `unverified` status.
- **Reject:** secrets in evidence, or `healthy` inferred only from configured state.
- **Accept:** failed reads when the failure is accurately classified and bounded.
