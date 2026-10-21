# Customer sharing

## Skill library

Skill content is generic operational guidance, not a statement about a real customer's posture. Examples must use synthetic values or typed placeholders. Do not put customer exports, access tokens, tenant configuration snapshots, production identifiers, internal account commentary, support correspondence or personal contact details in the library.

Descriptions must state what the skill actually does. A proposed schedule is not active automation; a local workbook or support request draft is not a deployed workbook or submitted ticket. Do not claim Microsoft certification or guaranteed savings, security, uptime, RTO or RPO.

## Report review checklist

Before delivery, a human confirms:

- [ ] The named audience, customer scope and approved destination are correct.
- [ ] The report is a synthetic demonstration or an actual assessment, clearly identified.
- [ ] Scope, UTC window, evidence timestamps, permissions and completeness are shown.
- [ ] Findings distinguish observed facts, hypotheses and missing evidence.
- [ ] No credentials, SAS signatures, connection strings or secret values remain.
- [ ] Personal identifiers, principal IDs, subscription IDs, internal hostnames and IP addresses are removed or necessary and explicitly approved for that customer's audience.
- [ ] Internal commentary, other customer information and unverified conclusions are removed.
- [ ] Every material recommendation has evidence, a current source and stated limits.
- [ ] Any prices retain currency, date, commercial assumptions and verified source.
- [ ] Tables, links, filtering, light/dark mode and print output have been checked.
- [ ] The exact attachment or upload destination is approved. Nothing is sent or uploaded merely because a report was generated.

## Shared renderer

The shared HTML renderer creates a sanitized draft by default. Structured identifiers and common sensitive patterns are replaced with consistent aliases. Its output includes a review notice and redaction count. `--include-identifiers` is an explicit option for an authorized customer audience; credentials are still redacted.

Automated pattern matching cannot identify every sensitive business name, custom payload or unsupported credential format. It is a safeguard, not a release approval. Review free text and attachments separately. Keep the original evidence private, do not overwrite it with the export, and do not execute aliased commands.

For JSON, CSV, diagrams, PDF, Bicep and workbook drafts, apply the same checklist. Validate the final format, not just an intermediate HTML file. Preserve source attribution and license notices when distributing the skill package.

## Sources

- [SRE Agent permissions and approval flows](https://learn.microsoft.com/azure/sre-agent/permissions).
- [SRE Agent skill content and tools](https://learn.microsoft.com/azure/sre-agent/skills).
