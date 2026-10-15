# `rvas-sre-agent-jumpstart` plugin package

This directory packages the `rvas-sre-agent-jumpstart` skill as an installable
GitHub Copilot CLI plugin, registered through
[`.github/plugin/marketplace.json`](../../.github/plugin/marketplace.json).

## Source of truth

The skill lives only here, under `skills/rvas-sre-agent-jumpstart/` in this
plugin directory. There is no separate copy under `.agents/skills/` — edit the
skill's `SKILL.md`, `assets/`, `references/`, and `evals/` directly in this
directory.

The packaged copy does not bundle the `grilling` or `azure-sre-agent`
dependency skills. Install those separately with `gh skill install` (see the
install guidance in `Student/Challenge-19.md`,
`Student/sql-server-dba/Challenge-09.md`, and `web/jumpstart.html`).

## MCP servers

[`mcp.json`](mcp.json) registers the `microsoft-learn` MCP server
(`https://learn.microsoft.com/api/mcp`) automatically when this plugin is
installed. The separately-installed `azure-sre-agent` dependency skill's
research step relies on this server's `microsoft_docs_fetch` tool to retrieve
current Azure SRE Agent documentation; no separate MCP configuration step is
required.
