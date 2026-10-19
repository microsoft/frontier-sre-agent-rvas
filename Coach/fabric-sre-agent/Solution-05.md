[< Previous Solution](./Solution-04.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Validate Model Choice and Data Residency

## Purpose

- Make the provider choice an operational and data-governance decision.
- Compare documented capabilities with reproducible, policy-approved observations.
- Expected time: 35–45 minutes.

## Mini-Lecture (10 min before challenge)

- SRE Agent offers Azure OpenAI/GPT and Anthropic/Claude provider families and
  routes among available models; avoid promising fixed model versions.
- Azure OpenAI emphasizes structured output/function calling; Anthropic
  emphasizes long-context/code reasoning and provides built-in web search.
- For EU/EFTA agent deployments, Azure OpenAI inference stays within Microsoft's
  EU Data Boundary. Anthropic inference can run globally and is excluded from
  that commitment, even if the agent and Fabric capacity are in Europe.
- Do not promise an EU Anthropic data center/inference path for SRE Agent.
  The documentation supports the service boundary above, not an absolute claim
  about all Anthropic physical data-center locations.
- Conversation storage, inference, Fabric data location, and agent AAU billing
  are separate subjects. Read-only tool results can still enter model context.
- An unapproved provider is not tested. A documented comparison is acceptable.

## Expected Student Output

- Portal evidence of agent region/provider and coach approval before real data.
- A provider comparison covering capabilities, EU inference, storage, AAUs,
  connector behavior, and the unchanged read-only/Code Access contract.
- Reproducible sanitized evaluation results or an explicit not-tested entry.
- Confirmation that the approved provider is selected for subsequent exercises.

## Common Issues and Hints

- **Symptom:** "Sweden Central means Claude stays in the EU." **Fix:** show the SRE Agent data-privacy table; Anthropic global processing is excluded from EUDB.
- **Symptom:** The agent claims a different provider than the portal. **Fix:** use Settings > Basics > Model provider as the authority and start a new conversation after a change.
- **Symptom:** Students upload real logs to compare an unapproved provider. **Fix:** stop before submission; use a sanitized fixed fixture only after approval or complete the documentation-only comparison.
- **Symptom:** Anthropic web search replaces a skill read. **Fix:** require Code Access file-read evidence regardless of provider.
- **Symptom:** A provider is unavailable or usage/latency results differ. **Fix:** record availability and observed results without fabricating a test or a universal winner; verify model AAU pricing separately from CU pricing.

## Debrief Discussion Guide

- Which boundary applies to inference versus stored conversations?
- Why does a European capacity not prove EU-only processing for the agent?
- Which measurements would justify changing a provider without weakening safety?
- What must happen before switching a provider on an agent with sensitive history?

## Success Criteria Notes

- Require the data-owner/compliance decision before a provider change.
- Accept documentation-only Anthropic comparison when policy forbids its use.
- Do not require Anthropic opt-in or treat missing global-processing approval as
  a student failure.
- Require fresh conversations, identical sanitized inputs, honest test limits,
  and restoration/confirmation of the approved provider.

## Solution

1. Review the [provider and privacy reference](../../Student/Resources/fabric-sre-agent/README.md#azure-openai-versus-anthropic-in-sre-agent)
   with current Microsoft Learn sources. Record the agent region and approved
   provider. Open **Settings > Basics > Model provider** (or **AI Model Provider**).
2. For EU-residency requirements, select **Azure OpenAI** on an EU/EFTA agent
   deployment and save. Verify the active setting before reading any real data.
3. Only if both providers are approved, save the alternate provider and start
   a fresh thread containing only a fixed synthetic fixture such as:

   ```text
   Synthetic evidence, not customer data:
   FUAM TotalCUs = 3600 CU-seconds; fixture rate = EUR 0.02/CU-hour.
   Validate the units and estimate. Read the router/required skills from
   Code Access first. This is a synthetic math-only test; do not call data
   or pricing tools or claim a real workspace was investigated.
   State what this evidence cannot establish about invoice allocation.
   ```

   Expected math: 1 CU-hour and EUR 0.02. Record instruction compliance,
   latency, and AAU usage if available. This fixture rate is **not** permitted
   as the rate in a real cost answer; the live pricing tool remains mandatory.
4. Restore/confirm the approved provider, start a fresh thread, and recheck
   one bounded skill/tool workflow. Do not reuse synthetic figures as telemetry.
