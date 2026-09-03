[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Explore the Knowledge Base

## Purpose

- Show how knowledge docs reduce hallucination by grounding the agent in the workshop’s actual topology, runbooks, and KQL.
- This is the bridge from generic model knowledge to lab-specific answers with real names, IPs, and tables.
- Expected time: 15–20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Explain retrieval-augmented behavior: the model does not read all docs every turn; it retrieves the most relevant ones.
- Point out the three knowledge families: `sample-food/`, `vnet-flow-logs/`, and `cost/`.
- Useful contrast demo: ask about Grubify topology before and after `make knowledge-files`.
- Highlight facts students should hear in answers: `ca-food-api`, `ca-food-frontend`, `lb-internal-web`, `10.20.2.100`, `Syslog`, Application Insights, and the three VNet flow logs. (Traffic Analytics / `NTANetAnalytics` is not introduced until Challenge 03.)

## Expected Student Output

- Portal shows all 9 certified knowledge documents after `make knowledge-files`.
- Agent names lab-specific components instead of generic Azure advice.
- For nginx failure questions, agent references the `Syslog` table and correct VM/web-tier context.
- When asked, the agent can cite or name the document it relied on.

## Common Issues and Hints

- **Symptom:** Answers remain generic right after upload. **Fix:** wait ~30 seconds for ingestion, then re-ask with a very specific lab question.
- **Symptom:** Agent cites wrong concepts like `/health` for Sample Food. **Fix:** steer students to docs showing `/WeatherForecast` and `/api/FoodItems` as valid checks.
- **Symptom:** Student uploads only one folder of docs. **Fix:** make sure all knowledge files from `knowledge/files/` are applied.
- **Symptom:** No citation when asked. **Fix:** have students explicitly prompt for the knowledge source by name.

## Debrief Discussion Guide

- Why not just rely on the model’s Azure training data? → It lacks your environment’s names, topology, and exceptions.
- What belongs in knowledge vs. a skill? → Reference context in knowledge; executable procedure/tool policy in skills.
- What is a healthy answer when the knowledge base lacks a fact? → “I don’t know,” not confident invention.

## Success Criteria Notes

- Be strict that answers must contain concrete lab details, not merely better prose.
- Accept semantic citations (“from the Sample Food architecture doc”) even if the agent does not quote exact filenames every time.
- If students surface one clean before/after example, that is enough.
