# Scenario skill library

This library contains **110 categorized skills** supporting **92 scenarios**.
Foundational scenario identification comes from
[alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios).
Skill contributions are adapted from
[smragav/azure-sre-agent-skills](https://github.com/smragav/azure-sre-agent-skills) and
[onsenturk/SreAgentExtensions](https://github.com/onsenturk/SreAgentExtensions),
using adapted local working copies with redistribution permission confirmed by
the user. Existing upstream notices are preserved, not replaced with a new license.
The workshop's default agent configuration is unchanged.

## Categories

| Explorer category | Folder | Skills |
| --- | --- | ---: |
| Billing & Entra Tenant | [billing-entra-tenant](./billing-entra-tenant/) | 13 |
| Identity & Access | [identity-access](./identity-access/) | 6 |
| Resource Organization | [resource-organization](./resource-organization/) | 14 |
| Network Topology | [network-topology](./network-topology/) | 14 |
| Security | [security](./security/) | 4 |
| Management | [management](./management/) | 45 |
| Governance | [governance](./governance/) | 9 |
| Platform & DevOps | [platform-devops](./platform-devops/) | 5 |
| **Total** | | **110** |

The six additional Management scenarios cover SLO and error budget analysis,
backup and restore validation, release regression detection, AKS application
incident triage, messaging delivery failure triage, and AI inference reliability.
The Explorer presents all scenarios consistently, without source type badges.
Provenance remains in the source catalogs for attribution and maintenance.

## Use case document coverage

The [coverage record](./catalog/docx-use-cases.json) accounts for all eleven
numbered use cases in `Azure SRE Agent - Use Cases.docx`, with its SHA256 digest,
review date, scenario mappings and scope boundaries. Cost optimization already
had coverage. The two consultation use cases share one scenario. Nine broader
scenario entries fill the remaining navigation and workflow gaps.

| Use case | Scenario or handling |
| --- | --- |
| Vulnerability management | Vulnerability management workflow |
| Azure expertise gaps and contextual consultation | One workload context and Azure consultation workflow |
| Cost optimization | Existing cost scenarios plus the FinOps assessment |
| Incident management and RCA | Incident and postmortem assessment skills |
| Historical operational data | Recurring signal analysis, not inferred distinct incident totals |
| WAF health checks | Curated Well Architected assessment, not certification |
| Defender and Advisor | Cross source recommendation triage |
| CI/CD failures | Build timeline and bounded log investigation |
| Standard platform requests | Request validation and local change planning |
| Lifecycle and CCoE alignment | Lifecycle evidence and mapped governance workflows |

Five dedicated skills were authored for the missing evidence workflows.
Incident investigation, recurring patterns, WAF review and lifecycle tracking
reuse the imported skills. Tooling integrations are enabling context rather than
extra scenarios. External systems require approved configured connectors;
tickets, repository updates, remediation and messages are not automatic.

Scenario tiles follow the category order above, retaining the catalog order
within each category. The Explorer summary is calculated from scenario data.
The six additional scenarios have heuristic operator time savings ratings:
Medium for SLO and error budget analysis and backup and restore validation,
High for release regression detection, AKS incident triage, messaging failure
triage and AI inference reliability. These are estimates, not measured results
or Azure bill savings. Each scenario explains its assumptions in the detail
panel. Quick win selections are unchanged.

## Sources of truth

- [Skill catalog](./catalog/skills.json): category, path, description, analysis
  rules, limitations and original source records for each imported skill.
- [Import record](./catalog/import.json): source commit, explicit working file
  snapshot, import dates, file digests, authorized assessment membership and the
  historical exclusion list from the first import.
- [Original scenario records](./catalog/upstream-scenarios.json) and
  [six extensions](./catalog/extension-scenarios.json): exact import membership.
- [Document coverage](./catalog/docx-use-cases.json): eleven use cases, nine added
  scenario records and their skill mappings.
- Each category folder contains `<skill-id>/SKILL.md`. Dedicated evidence
  workflows use `references/workflow.md` and `references/output-contract.json`.
  Imported assessments preserve their skill specific checks, report layouts
  and runtime contracts rather than inventing a replacement schema.
- [Shared dependencies](./shared/): assessment and sharing rules, governance
  configuration, report rendering and local evidence analysis.

Scenario mappings are explicit `skills` arrays in the repository's
[scenario data](../../../web/assets/js/scenarios-data.js). A scenario can name
multiple skill IDs, and one skill can support multiple scenarios. The initial
import maps each scenario to its dedicated skill. Dedicated evidence workflows
must be mapped; assessment skills can also remain standalone in the Skills tab.

## Customer use

Use the separate [Skills tab](../../../web/skills.html) to search all skills and
filter by category without opening a scenario. Skill setup, download guidance and
validation boundaries live on that page. Alternatively, open a scenario in
Scenario Explorer to use its mapped skills. Both views let you:

1. View each mapped skill's category and instructions.
2. Copy its SKILL.md instructions.
3. Download a complete ZIP with the required references and runtime tools.
4. Follow the linked installation and safety guide.

Copying SKILL.md alone is **not** a complete installation. Source links to shared
references are rewritten into portable local links in the downloaded bundle.
Each ZIP contains:

```text
README.md
LICENSE
THIRD-PARTY-NOTICES.md
skills/
  <skill-id>/
    skill.yaml
    SKILL.md
    references/
    tools/
    shared/          # Present for assessments whose tools discover shared runtime
```

The manifest is for **this repository's configuration script**, not a documented
native portal ZIP importer. The ZIP is a distribution package. Only dependencies
required by the selected skill are bundled. Assessment archives preserve nested
`shared/tools/` and `shared/references/` so their original import and policy
discovery work in isolation. Keep these paths intact. Optional agent, sample
report and IaC files are retained where supplied; they are not automatically
installed, executed or deployed. Use the repository manifest for the complete
file list rather than assuming an older optional deployment script bundles
every nested dependency.

### Install into an existing agent

Microsoft Learn documents skill creation in **Builder > Skills**, with SKILL.md,
optional tools and supporting files. Review the current portal attachment
controls and preserve the supporting file paths. Alternatively, use this
repository's existing configuration script with the extracted bundle as its
explicit configuration root.

Run the repository automation in **Linux Bash**, from the repository root, with
the workshop prerequisites installed. The following commands first validate and
preview one skill; they do not apply it:

```bash
CONFIG_DIR="/absolute/path/to/extracted-bundle"
SKILL_ID="cost-anomaly-detection"
CONFIG_SCRIPT="$PWD/Student/Resources/infra/scripts/sre-agent-config.sh"

bash "$CONFIG_SCRIPT" validate \
  --config "$CONFIG_DIR" --target skills --name "$SKILL_ID"

bash "$CONFIG_SCRIPT" plan \
  --config "$CONFIG_DIR" --target skills --name "$SKILL_ID" \
  --subscription "<subscription-id>" \
  --resource-group "<agent-resource-group>" --agent "<agent-name>"
```

After the customer has reviewed the manifest, identity, tools and plan, the
operator can explicitly approve installation and run:

```bash
bash "$CONFIG_SCRIPT" apply \
  --config "$CONFIG_DIR" --target skills --name "$SKILL_ID" \
  --subscription "<subscription-id>" \
  --resource-group "<agent-resource-group>" --agent "<agent-name>"
```

This updates the selected agent's skill definition and can replace a skill with
the same name. It does not authorize changes to the resources investigated by
the skill. Review existing skills before applying. No command above is run by
viewing or downloading from the website, and this library is not part of the
default workshop agent deployment.

### Runtime and approval boundaries

- Confirm tenant, explicit subscription and resource allowlist, identity, UTC
  window, permissions and customer approved objectives before collecting evidence.
- Preserve each code block's shell. Imported workflows contain Azure CLI
  templates, PowerShell collection snippets and Python examples. PowerShell
  blocks require an approved PowerShell execution host; they are not Bash scripts.
  The workshop's configuration automation still requires Linux Bash.
- Run local analyzer commands from `skills/<skill-id>/` after extraction.
  The six additional Management skills include synthetic evidence fixtures and
  a Python analyzer that performs no cloud calls.
- The six local evidence analyzers use the Python standard library. Imported
  live collectors also need host dependencies such as `requests` and
  `azure-identity`. The architecture generator additionally needs `pandas` and
  an Excel engine such as `openpyxl`. These are runtime prerequisites, not needed
  to build the site; provision them in the approved host as required.
- Configure identity explicitly using `AZURE_CLIENT_ID` for the approved user
  assigned identity, or the supported `SRE_IDENTITY_MODE`. Do not fall back to a
  different principal after an authentication failure. Review
  [environment settings](./.env.example), `SRE_LIFECYCLE_EVIDENCE` and
  `SRE_REPORT_OUTPUT_DIR`. Missing or stale lifecycle evidence stays Unknown.
- Run the architecture generator in its extracted skill directory with the
  bundled shared runtime intact. Do not copy the Python template alone.
- Scheduling tools are not enabled by the imported SQL CMDB skill. It prepares
  a proposal; an operator must separately authorize and configure scheduling.
- The CI/CD workflow can use sanitized exports. Live Azure DevOps access needs
  a separately approved organization, project and GET endpoint allowlist. The
  default governance policy does not enable that endpoint.
- Enforce the explicit tool allowlist and [governance policy](./shared/references/governance.json)
  in the host. In particular, terminal tools require constrained execution;
  instructions and a policy file alone do not enforce authorization.
- Missing, denied, stale or truncated evidence is not a healthy result.
- Changes, deployment, scheduling, uploads and external delivery require separate
  approval. Do not enable an upload tool merely because it appears in the source
  skill's declared tools.
- Follow the [sharing checklist](./shared/references/customer-sharing.md).
  Local tests and bundled examples are not live Azure validation.

## Build and maintain

Building the website now requires Python 3.10 or later and Node.js in addition
to the existing GNU Make environment. No Python package is needed to build.

From the repository root:

```bash
python Student/Resources/scenario-skills/scripts/build_library.py
make build-web
```

The first command refreshes the committed browser catalog and generates ignored
downloads under `web/assets/skill-bundles/`. `make build-web` independently
rebuilds the complete downloads and publishes the library documentation into
`_site`. Serve `_site` to test the same paths used by GitHub Pages.

After editing a skill or mapping, regenerate and validate:

```bash
python Student/Resources/scenario-skills/scripts/build_library.py --check
python -m pytest Student/Resources/scenario-skills -q
```

Install test dependencies from [requirements-dev.txt](./requirements-dev.txt)
in a Python 3.11 or later test environment. The architecture tests use pandas
and openpyxl with synthetic local workbooks; no live pricing call is made.
Never edit the generated
[browser skill catalog](../../../web/assets/js/scenario-skills-data.js) directly.
The builder checks exact import membership, authorization records, categories, scenario
mappings, frontmatter, contracts, shared dependencies and portable Markdown links.
Tests also run all six analyzers from their actual downloaded archive layouts.
All imported collector and shared runtime regression tests are included in CI.
Every assessment archive is extracted and its shared imports and policy file
are checked in an isolated Python process with no Azure calls.

## Verification and sources

| Claim | Status | Evidence |
| --- | --- | --- |
| Builder > Skills creates skills with instructions, tools and supporting files. | Verified | [Microsoft Learn skills article](https://learn.microsoft.com/en-us/azure/sre-agent/skills), checked 2026-10-21. |
| The portal accepts these ZIPs as a native import format. | Uncertain | Not documented in the consulted skills article; no such support is assumed. |
| Imported collection commands work in every customer environment. | Uncertain | Requires current service documentation and approved live testing. Recorded source dates remain in each skill. |

Additional sources:

- [Repository configuration conventions](https://github.com/microsoft/frontier-sre-agent-rvas/blob/main/Student/Resources/azure-sre-agent-config/README.md).
- [Existing configuration script](https://github.com/microsoft/frontier-sre-agent-rvas/blob/main/Student/Resources/infra/scripts/sre-agent-config.sh).
- [Pinned upstream scenario provenance](./catalog/upstream-scenarios.json).
- [Scenario license notices](./THIRD-PARTY-NOTICES.md).
- [Onur Senturk's skill repository](https://github.com/onsenturk/SreAgentExtensions).
- [Document use case coverage](./catalog/docx-use-cases.json).
