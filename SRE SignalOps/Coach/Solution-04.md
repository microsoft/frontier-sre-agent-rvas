[< Previous Solution](./Solution-03.md) | **[Home](./README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Discover Connected Systems

## Purpose

Turn configured connectors into an evidence-backed reachability map. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Configured, authenticated, reachable, and authorized are four different states.

## Expected Student Output

A connector matrix with observed read tests, timestamps, scopes, and failure classifications.

## Common Issues and Hints

- **Symptom:** Connector shows healthy but reads fail. **Fix:** test authentication and authorization separately.
- **Symptom:** Secrets appear in output. **Fix:** redact and rotate exposed values immediately.
- **Symptom:** Agent omits MCP tools. **Fix:** request tool discovery from each MCP endpoint.

## Debrief Discussion Guide

1. What is the strongest connectivity evidence?
2. How should stale reads be labeled?
3. Which connectors can write?

## Success Criteria Notes

Every configured connector needs a current read test or an explicit unverified label.
