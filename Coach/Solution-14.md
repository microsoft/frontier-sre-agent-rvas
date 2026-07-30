[< Previous Solution](./Solution-13.md) | **[Home](./README.md)** | [Next Solution >](./Solution-15.md)

# Coach Guide — Challenge 14: Application Root Cause Analysis

## Purpose

- Deliver the end-to-end “wow” moment: telemetry → failing endpoint → source code evidence → GitHub artifact.
- This challenge demonstrates multi-plane reasoning better than any other in the workshop.
- Expected time: 25–30 minutes.

## Mini-Lecture (5–7 min before challenge)

- Walk the failure sequence: `make break-food` sends ~200 POSTs to `/api/cart/demo-user/items` → OOM/restart window → `alert-vflta-food-http-5xx` → `aca-app-incident-handler`.
- Call out the key Sample Food facts from knowledge: valid health routes are `/WeatherForecast` and `/api/FoodItems`; `/health` is not real.
- Explain the ideal architecture students should describe: app specialist uses Container Apps + App Insights evidence, then correlates to code and opens a GitHub issue.
- Important coach nuance: some tenants may show explicit `code-analyzer` handoff; current repo YAML may inline code correlation inside `aca-app-incident-handler` due workspace-mode limits. Accept either pattern if the outcome includes file/line evidence.

## Expected Student Output

- Incident appears and is routed by `sample-food-http-errors` to `aca-app-incident-handler`.
- Agent identifies `/api/cart/{user}/items` as the failing path from logs/telemetry.
- Root-cause output references actual Grubify source, ideally `CartController.cs` or the cart write path with file/line evidence.
- A GitHub issue is created with telemetry evidence, code evidence, and remediation guidance.

## Common Issues and Hints

- **Symptom:** Agent or student checks `/health`. **Fix:** correct to `/WeatherForecast` or `/api/FoodItems` using the knowledge doc.
- **Symptom:** Alert is slow. **Fix:** wait up to 10 minutes, then use the manual prompt from the challenge.
- **Symptom:** GitHub issue lacks code evidence. **Fix:** verify `github` connector + `grubify` repo link, then ask explicitly for file/line references.
- **Symptom:** No visible handoff to `code-analyzer`. **Fix:** explain current config may inline the code step; grade on outcome, not choreography.

## Debrief Discussion Guide

- Why is this stronger than “investigate in portal, then file a ticket manually”? → One continuous evidence chain across observability and source.
- What governance controls matter here? → Narrow GitHub scope, explicit repo link, and write-capable specialists only where intended.
- Why is file/line evidence more persuasive than “probably the cart code”? → It makes follow-up engineering actionable.

## Success Criteria Notes

- Be strict on the failing endpoint and the GitHub issue artifact.
- Be flexible on whether the code step is separate-agent handoff or inlined by the app specialist.
- If the app self-heals before students inspect it, accept portal history plus the GitHub issue as evidence.
