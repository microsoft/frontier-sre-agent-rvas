[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Subagents & Incident Filters

## Purpose

This challenge is the architectural heart of the workshop. Students learn that the SRE Agent's incident response behavior is **fully declarative** — you define the routing, the persona, and the tool scope in YAML. Understanding this makes Challenges 04–09 much more meaningful: the agent doesn't have magic; it follows the rules you wrote.

Expected time: **25–30 minutes**.

## Mini-Lecture (10 min before challenge)

Cover the domain-routing architecture (draw this on a whiteboard):

```
Azure Monitor Alert
        │
        ▼
  Incident Platform (AzMonitor)
        │
  ┌─────┴──────────────────────────────────────────┐
  │  Incident Filters (routing rules)               │
  │  ┌──────────────────────────────────────────┐   │
  │  │ titleContains: "food"  ──► aca-app-handler│   │
  │  │ titleContains: "nginx" ──► iaas-vm-handler│   │
  │  │ (else)                 ──► network-analyst│   │
  │  └──────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────┘
        │
  ┌─────▼──────────┐
  │   Subagent     │  ← system_prompt + tools + skills
  │  (specialist)  │
  └────────────────┘
```

Key points:
- Filters are evaluated in priority order; first match wins
- `titleContains` is case-insensitive
- A subagent can handle multiple filters (e.g., `network-traffic-analyst` handles both S5 and S6)
- `agentMode: Autonomous` means act immediately; `Interactive` means wait for human
- Agent-to-agent handoffs (`handoffs:`) are NOT supported in workspace mode — capabilities must be inlined

## Expected Student Output

- A valid subagent YAML with: meaningful `description`, appropriate `agentMode`, well-structured `system_prompt`, constrained `tools` list
- A valid incident filter YAML referencing the subagent by exact name
- Both applied and visible in portal; manual chat test confirms the subagent responds in persona

## Common Issues and Hints

### `handlingAgent` mismatch (most common)
- The filter's `handlingAgent` must exactly match the subagent's `metadata.name` (case-sensitive)
- If apply succeeds but portal shows no agent assignment, this is the cause

### Subagent system prompt is too vague
- The agent will still work but produce generic, unhelpful responses
- Coach prompt: "What would happen if two different SREs with different experience levels received this same system prompt as their job description? Would they both do the same thing?" — if no, the prompt needs tightening
- Good system prompts: named domain, named investigation steps, named output format

### `agentMode: Interactive` student chose but filter is `Autonomous`
- Technically valid but the filter overrides — the agent will act autonomously even if it's configured as Interactive
- Discuss: the filter's agentMode is the runtime override; the subagent's agentMode is its default for direct invocation

### Student tries to add `handoffs:`
- The API will return 400: "Agent-to-agent handoffs are not supported in workspace mode"
- Explain: this is a platform constraint. Show how `aca-app-incident-handler` inlines code-analysis capability instead of delegating to `code-analyzer`

### Filter keyword overlaps with existing filter
- If a student chooses `titleContains: food` or `titleContains: nginx`, their filter will conflict
- Explain: the existing filters will still match first (priority order) — the student's filter may never fire
- Resolution: choose a unique keyword or change the priority to `Sev3` (won't conflict with Sev1/Sev2 lab alerts)

## Debrief Discussion Guide (10 min)

1. **What is the blast radius of a write-capable subagent?** — An agent with `RunAzCliWriteCommands` can modify Azure resources. How do you limit that? (Answer: narrow the system prompt's scope, use ManagedIdentity with minimal RBAC, review audit logs)
2. **Why not have one general-purpose agent instead of specialists?** — Specialists produce more consistent, predictable output. A general agent's behavior varies more per incident. Also: smaller tool scope = smaller blast radius.
3. **How would you design incident routing for YOUR team's alerts?** — Surfaces real-world alert taxonomy the students already have.

## Success Criteria Notes

- The filter's `titleContains` keyword uniqueness is the main technical verification — ask the student to explain why they chose their keyword
- The chat test (talking to the subagent in portal) is the qualitative check — does it respond in the right persona?
- Partial credit: student wrote valid YAML but apply failed → walk through the error together; the debugging process is itself valuable
