[< Previous Solution](./Solution-13.md) | **[Home](./README.md)** | [Next Solution >](./Solution-15.md)

# Coach Guide — Challenge 14: Application Root Cause Analysis

## Purpose

- Deliver the end-to-end “wow” moment: telemetry → failing endpoint → source code evidence → GitHub artifact.
- This challenge demonstrates multi-plane reasoning better than any other in the workshop.
- Expected time: 25–30 minutes.

## Mini-Lecture (5–7 min before challenge)

- Walk the failure sequence: `make break-food` sends ~200 POSTs to `/api/cart/demo-user/items` → OOM/HTTP 500 window → `alert-food-http-5xx` → `aca-app-incident-handler`.
- Call out the key Sample Food facts from knowledge: valid health routes are `/WeatherForecast` and `/api/FoodItems`; `/health` is not real.
- Explain the two explicit outcomes: S1 completes the Azure diagnosis/remediation without GitHub; S2 invokes `code-analyzer` for read-only source correlation and GitHub issue creation.
- Emphasize that Grubify source is immutable: no branch, pushed file, commit, or pull request is acceptable evidence.

## Expected Student Output

- Incident appears and is routed by `sample-food-http-errors` to `aca-app-incident-handler`.
- Agent identifies `/api/cart/{user}/items` as the failing path from logs/telemetry.
- Root-cause output references actual Grubify source, ideally `CartController.cs` or the cart write path with file/line evidence.
- With OAuth write authorization complete, a GitHub issue is created with telemetry evidence, code evidence, and remediation guidance.

## Common Issues and Hints

- **Symptom:** Agent or student checks `/health`. **Fix:** correct to `/WeatherForecast` or `/api/FoodItems` using the knowledge doc.
- **Symptom:** Alert is slow. **Fix:** wait up to 10 minutes, then use the manual prompt from the challenge.
- **Symptom:** GitHub issue creation reports that the user must be logged in. **Fix:** complete the `github-mcp` connector OAuth authorization, confirm `code-analyzer`'s `mcp_tools` list includes the needed `github-mcp_*` write tools.

## Debrief Discussion Guide

- Why is this stronger than “investigate in portal, then file a ticket manually”? → One continuous evidence chain across observability and source.
- What governance controls matter here? → Narrow GitHub scope, explicit repo and connector grants, immutable source, and issue-only write behavior.
- Why is file/line evidence more persuasive than “probably the cart code”? → It makes follow-up engineering actionable.

## Success Criteria Notes

- Be strict on the failing endpoint and the GitHub issue artifact.
- Require S1 and S2 as separate but evidence-linked outcomes; do not require an unsupported automatic handoff.
- If the app self-heals before students inspect it, accept portal history plus the GitHub issue as evidence.
