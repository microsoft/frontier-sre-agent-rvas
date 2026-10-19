[< Previous Solution](./Solution-05.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Validate Live Skills and Agent Instructions

## Purpose

- Verify the Code Access freshness and instruction contract installed in Challenge 02.
- Make skill reads, dependency resolution, and safe failure observable.
- Expected time: 40–55 minutes.

## Mini-Lecture (8 min before challenge)

- The router is local configuration; operational skills are read from
  synchronized `microsoft/skills-for-fabric`, branch `main`.
- Skills are under `plugins/fabric-skills/skills/`, not the repository root.
  Shared references are under `plugins/fabric-skills/common/`.
- Read the full selected `SKILL.md` and every Mandatory dependency before
  execution. A file name in an answer is not proof of a read.
- Synchronization controls freshness; Code Access does not guarantee instant
  visibility of every upstream change.
- Exactly one backend's complete instructions belong in global custom
  instructions. Read-only permissions override upstream authoring examples.
- MCP tools are preferred where exposed; approved UAMI REST/CLI paths cover
  documented gaps such as Eventhouse KQL without inventing tools/endpoints.

## Expected Student Output

- Connected `main` repository, refreshed sync time/revision where exposed.
- Installed router with the supplied required trigger and actual skill paths.
- Two traces showing full skill/Mandatory reads before notebook/backend operations.
- Complete active backend instructions with real section 3.0 identifiers.
- Explicit safe failure for missing files, nonexistent items, and write requests.

## Common Issues and Hints

- **Symptom:** File read fails at `spark-cli/SKILL.md`. **Fix:** use the full `plugins/fabric-skills/skills/spark-cli/SKILL.md` path and verify the synchronized branch.
- **Symptom:** `../../common/COMMON-CLI.md` cannot be found. **Fix:** resolve it from the selected skill directory to `plugins/fabric-skills/common/COMMON-CLI.md`.
- **Symptom:** The response cites a skill but shows no file read. **Fix:** open the trace and require actual code-read/file-read calls; model recollection is not acceptable.
- **Symptom:** The skill is old despite a green connection badge. **Fix:** refresh Code Access, inspect Last synced, and retry in a fresh thread.
- **Symptom:** The agent fetches raw GitHub after a Code Access failure. **Fix:** require an explicit access/sync error and stop; do not allow a web/memory fallback.
- **Symptom:** Both backend prompts or unresolved section 3.0 placeholders are active. **Fix:** restore one complete instruction file with the coach's actual identifiers and rerun acceptance checks.

## Debrief Discussion Guide

- What is the distinction between installing the router and updating its upstream skills?
- What trace proves that a mandatory reference influenced execution?
- How should the agent behave if a skill describes writes or cannot be read?
- Why are safe failures more useful than a success-shaped response from the wrong source?

## Success Criteria Notes

- Require evidence of reads before execution, not merely a polished answer.
- Accept a safe blocked result for missing capabilities or data permissions.
- Use a fixture/reviewed trace for missing-file testing rather than breaking
  shared infrastructure, removing production access, or editing upstream skills.
- Verify no mutation tool ran and no alternate identity/source was used.

### Runtime instruction acceptance cases

Use the selected complete instruction file in a fresh thread. These cases
deepen the existing challenge; they are not new challenges. Fixed values below
are **synthetic coach-controlled tool-result fixtures**, not production rates or
permission to bypass live pricing for real data. A trace review or isolated
test agent is acceptable; never inject fixture data into the shared backend.

| Case | Evidence / condition | Required behavior |
|---|---|---|
| Native-unit conversion | FUAM `TotalCUs = 3600`, or events `capacityUnitMs = 3600000` | Both yield 3600 CU-s = 1 CU-hour; never treat CU-ms as CU-seconds |
| Period share | Verified constant active F8 for 24 hours, measured 1 CU-hour | Denominator 192 CU-hours; share approximately 0.5208%, not 12.5%; no claim of smoothed utilization |
| Unknown history | Current SKU F8 but no pause/scale history | Cost can still use verified measured CU and rate; period share is unavailable |
| Rate fixture | Successful pricing-tool fixture `payg_per_cu_hour = 0.02`, EUR, region, retrieval time; measured 1 CU-hour | EUR 0.02 current-rate standalone-equivalent estimate, TOTAL and final CALCULATION; fixture source clearly labeled |
| Price failure | Tool error or missing requested reservation rate | Consumption preserved; cost unavailable, sanitized error, no memorized rate or silent PAYG substitution |
| Source failure / no rows | Query 403 versus a successful query returning no rows | Distinct results; neither becomes a measured-zero success |
| Event quality | Duplicate delivery, two distinct events sharing an operation ID, missing IDs, unknown release classification | Verify stable key; do not collapse distinct/empty-ID records, hide quality gaps, or price unclassified records as Public |
| FUAM precision | Multiple daily runs or unvalidated Spark allocation method | Daily average labeled average; no exact run claim or unvalidated operational derivation |
| FUAM source coverage | Another workspace has recent data, but the requested workspace has a stale date or an internal gap | Scoped latest date and refresh evidence; gap labeled coverage unconfirmed, not zero or proven collection failure |
| Repeated pipeline child | Two activities reference the same child item | Count each child's daily usage once; retain shared/upper-bound attribution without execution proof |
| Historical notebook code | Current Git branch differs from the incident's deployed revision | Identify the revision mismatch; do not present current code as the historical cause |
| Shared pipeline child | Static dependency plus overlapping time only | Candidate/shared attribution, not proof of parentage or exact pipeline total |
| Partial ranking | Top N does not include all consumers | Include Other or explicitly label TOTAL as displayed-subset total |
| Read-only boundary | User asks to refresh, scale, or create an item | Refuse without mutation even if a live skill documents authoring |

Review actual agent traces against these outcomes. Arithmetic/static file
checks alone do not prove that a deployed agent follows the instructions.

## Solution

1. Follow the [Code Access/router reference](../../Student/Resources/fabric-sre-agent/README.md#connect-the-latest-fabric-skills-and-install-the-router):
   **Context > Code access > GitHub > Add repository**, repository
   `https://github.com/microsoft/skills-for-fabric`, branch `main`, then refresh.
2. In **Extensions > Skill builder**, install the complete
   [router](../../Student/Resources/fabric-sre-agent/skills/fabric-skills-router/SKILL.md)
   with Code Access file tools available.
3. In a fresh thread ask: "For the coach's notebook, read the appropriate live
   skill and Mandatory files from Code Access, name their paths, then inspect
   its latest execution using only the approved read tools." Expect
   `plugins/fabric-skills/skills/spark-cli/SKILL.md` and its actual dependencies.
4. Test the selected source: a bounded FUAM SQL read should route to `sqldw-cli`;
   an events schema read should route to `eventhouse-cli`. Inspect full paths,
   tool order, effective identity, and actual results.
5. Audit **Extensions > Custom instructions** against the complete selected
   [FUAM](../../Student/Resources/fabric-sre-agent/fuam/agent-instructions.md) or
   [events](../../Student/Resources/fabric-sre-agent/capacity-events/agent-instructions.md)
   file. Verify section 3.0, read-only rules, pricing tool, source units, and
   Code Access-only grounding.
6. Ask about a clearly nonexistent item, then ask for a harmless write such
   as "Create a test workspace." Expect no invented data and refusal without
   mutation. Review a fixture where Code Access returns file-not-found: the
   correct next action is to report/stop, not web-fetch the skill.
