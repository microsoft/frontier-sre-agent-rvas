[< Previous Challenge](./Challenge-04.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Validate Model Choice and Data Residency

> **Capabilities added in this challenge**: Azure OpenAI vs Anthropic · EU Data Boundary · Model Evaluation

## Introduction

The SRE Agent's model provider affects reasoning, tool behavior, agent-unit
cost, and where inference can take place. An EU Fabric capacity or an EU agent
storage region does not, by itself, make every model provider EU-local.

## Description

Review the active provider and the coach-approved data policy before continuing.
First ask the agent to explain its provider and processing boundary, then
verify its claim against the portal and current Microsoft documentation.
Use the [provider comparison reference](../Resources/fabric-sre-agent/README.md#azure-openai-versus-anthropic-in-sre-agent)
to evaluate the existing agent, not create another challenge or deployment.

- Record the agent region, active provider, documented inference boundary, and
  the difference between inference and conversation storage.
- Compare Azure OpenAI's structured/tool-oriented strengths with Anthropic's
  long-context/code reasoning and built-in web search; do not assume either
  provider always gives the best operational answer.
- Explain that **Anthropic EU-local inference is not guaranteed for SRE Agent**:
  it can process globally and is excluded from Microsoft's EU Data Boundary.
  Select Azure OpenAI with an EU/EFTA agent deployment when EU residency is required.
- With coach approval, evaluate the same sanitized, non-sensitive prompt and
  frozen sample evidence under each permitted provider in separate fresh threads.
  Compare tool selection, instruction compliance, calculation correctness,
  latency, and available AAU usage. Do not send restricted telemetry to an
  unapproved provider just to complete a comparison.
- If Anthropic is not approved or available, compare its documented behavior
  only, mark runtime results as not tested, and keep the approved provider.

Changing models does not change Fabric item permissions, MCP identity, skills,
or the requirement to read skills from Code Access rather than web search.

## Success Criteria

- [ ] The portal's active provider and agent region are recorded with the coach's approval.
- [ ] The comparison distinguishes inference residency, stored conversation data, model capabilities, and AAU charges from Fabric CU costs.
- [ ] The EU recommendation states that Azure OpenAI inference for EU/EFTA agent deployments stays within the EU Data Boundary, while Anthropic processing may be global.
- [ ] Any runtime comparison uses identical sanitized inputs and fresh threads; prohibited or unavailable provider tests are explicitly marked not run.
- [ ] The approved provider is restored/confirmed before real-data exercises, with no broadened permissions or web-based skill substitutes.
- [ ] **Explain to your coach** — why does placing Fabric and the agent in Europe not establish EU-only processing when Anthropic is selected?

## Learning Resources

- [SRE Agent model provider selection](https://learn.microsoft.com/azure/sre-agent/model-provider-selection)
- [SRE Agent data residency and privacy](https://learn.microsoft.com/azure/sre-agent/data-privacy)
- [SRE Agent pricing and AAU billing](https://learn.microsoft.com/azure/sre-agent/pricing-billing)
- [Workshop provider comparison reference](../Resources/fabric-sre-agent/README.md#azure-openai-versus-anthropic-in-sre-agent)

## Tips

- Trust the portal and documented service guarantees, not an agent's self-reported identity or an assumed data-center location.
- Anthropic's built-in web search does not waive the router's Code Access-only rule.
- Never switch to a globally processed provider using a thread containing sensitive historical tool outputs.
