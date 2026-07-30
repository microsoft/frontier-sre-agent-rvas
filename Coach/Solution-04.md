[< Previous Solution](./Solution-03.md) | **[Home](./README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Discover Connected Systems

## Purpose

- Show how MCP connectors extend the agent to live external systems, using Microsoft Learn as the safe first example.
- This matters because operational agents must combine local investigation with current vendor guidance.
- Expected time: 10–15 minutes.

## Mini-Lecture (3–5 min before challenge)

- Distinguish skills from connectors: a skill governs built-in tool usage; a connector surfaces new external tools.
- Call out the working Learn connector details: `microsoft-learn-mcp`, Streamable HTTP endpoint `https://learn.microsoft.com/api/mcp`, no auth beyond empty custom headers.
- Mention the three surfaced tools at a concept level: docs search, docs fetch, code sample search.
- Demonstrate the before/after difference with “cite the official article” prompts.

## Expected Student Output

- Before setup, docs answers are uncited or training-data-only.
- After `make connectors`, the `microsoft-learn-mcp` connector is green.
- The agent returns a real Learn URL and can blend it with Grubify/Azure troubleshooting guidance.

## Common Issues and Hints

- **Symptom:** Connector exists but tools are unavailable in chat. **Fix:** confirm the connector is connected and the MCP tools are visible to the meta agent.
- **Symptom:** Student expects OAuth. **Fix:** clarify this public connector requires no user auth; GitHub was the auth-required example.
- **Symptom:** Agent gives a URL from memory but not fetched live. **Fix:** ask for a current recommendation plus citation and article URL.

## Debrief Discussion Guide

- When do you use a connector instead of adding more knowledge docs? → When freshness and live retrieval matter.
- Why is Microsoft Learn a good demo connector? → Safe, public, clearly verifiable, and operationally useful.
- What governance boundary remains? → The agent still cannot call arbitrary APIs not wired as connectors.

## Success Criteria Notes

- Be strict on the presence of a live URL.
- Accept minor variance in article choice if it is current and relevant.
- Students do not need to name the individual MCP tool IDs, only the connector concept and behavior.
