

# ----------------------------------------------------------------------------- permissions
def _graph_role(path):
    low = re.sub(r"^/?(v1\.0|beta)/", "", str(path).lower())
    for pattern, role in GRAPH_ROLES:
        if re.match(pattern, low):
            return role
    return "Directory.Read.All"


def _graph_cmd(role, principal):
    roles = [r.strip() for r in role.split("+")]
    out = ['GRAPH_SP=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query id -o tsv)']
    for r in roles:
        out += [f"ROLE_ID=$(az ad sp show --id 00000003-0000-0000-c000-000000000000 --query \"appRoles[?value=='{r}'].id\" -o tsv)",
                f"az rest --method POST --uri https://graph.microsoft.com/v1.0/servicePrincipals/{principal}/appRoleAssignments "
                f"--body \"{{\\\"principalId\\\":\\\"{principal}\\\",\\\"resourceId\\\":\\\"$GRAPH_SP\\\",\\\"appRoleId\\\":\\\"$ROLE_ID\\\"}}\""]
    return "\n".join(out)


def _ws_scope(workspace_id, env):
    for ws in (env or {}).get("log_analytics_workspaces", []):
        if str(ws.get("customerId", "")).lower() == str(workspace_id).lower():
            return ws.get("id")
    return "<workspace resource id: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<name>>"


def _sp_cmd(site, client_id, role):
    site_ref = site.get("site_id") or site.get("site_url", "<site url>")
    return ("# Microsoft Graph PowerShell, run by a SharePoint/Entra admin\n"
            "Connect-MgGraph -Scopes Sites.FullControl.All\n"
            + (f"$site = Get-MgSite -SiteId '{site_ref}'\n" if site.get("site_id") else
               f"$u = [uri]'{site_ref}'; $site = Get-MgSite -SiteId (\"{{0}}:{{1}}\" -f $u.Host, $u.AbsolutePath)\n")
            + f"New-MgSitePermission -SiteId $site.Id -BodyParameter @{{roles=@('{role}'); grantedToIdentities=@(@{{application=@{{id='{client_id}'; displayName='sre-agent'}}}})}}")


def _permissions(config, env=None):
    env = env or {}
    ident = env.get("identity") or {}
    principal = ident.get("principal_id") or "<agent managed identity principal (object) id>"
    client_id = ident.get("client_id") or "<agent managed identity client id>"
    tenant = ident.get("tenant_id") or "<tenant id>"
    granted_graph = set(env.get("graph_app_roles") or [])
    granted_azure = env.get("azure_roles") or []
    plan, seen = [], set()

    def add(key, need, scope, command, why, check=None):
        if key in seen:
            return
        seen.add(key)
        already = bool(check and check())
        plan.append({"need": need, "scope": scope, "why": why, "status": "ALREADY_GRANTED" if already else "TO_GRANT",
                     "command": "" if already else command})

    def has_role(names, scope_hint=""):
        return any(r.get("role") in names and (not scope_hint or str(scope_hint).lower().startswith(str(r.get("scope", "")).lower()))
                   for r in granted_azure)

    rbac = "az role assignment create --assignee-object-id {p} --assignee-principal-type ServicePrincipal --role \"{r}\" --scope \"{s}\""
    for src in config["sources"]:
        t = src["type"]
        if t == "log_analytics":
            scope = _ws_scope(src.get("workspace_id"), env)
            add("la:" + scope, "Log Analytics Reader", scope, rbac.format(p=principal, r="Log Analytics Reader", s=scope),
                f"run KQL for source '{src['id']}'", lambda s=scope: has_role({"Log Analytics Reader", "Reader", "Monitoring Reader", "Contributor", "Owner"}, s))
        elif t in ("resource_graph", "arm"):
            subs = src.get("subscriptions") or ([m.group(1) for m in [re.search(r"/subscriptions/([^/?]+)", str(src.get("path", "")))] if m] or ["<subscription id>"])
            for sub in subs:
                scope = f"/subscriptions/{sub}"
                add("reader:" + scope, "Reader", scope, rbac.format(p=principal, r="Reader", s=scope), f"read resources for source '{src['id']}'",
                    lambda s=scope: has_role({"Reader", "Contributor", "Owner"}, s))
        elif t == "cost_management":
            scope = src.get("scope", "<scope>")
            add("cost:" + scope, "Cost Management Reader", scope, rbac.format(p=principal, r="Cost Management Reader", s=scope),
                f"query cost for source '{src['id']}'", lambda s=scope: has_role({"Cost Management Reader", "Reader", "Contributor", "Owner"}, s))
        elif t == "graph":
            role = _graph_role(src.get("path"))
            add("graph:" + role, f"Microsoft Graph application permission {role}", "tenant", _graph_cmd(role, principal),
                f"call Graph {str(src.get('path')).split('?')[0]} (needs Privileged Role Administrator or Global Administrator to grant)",
                lambda r=role: all(x.strip() in granted_graph for x in r.split("+")))
        elif t == "adx":
            db = src.get("database", "<database>")
            add("adx:" + db, "ADX database viewer", f"{src.get('cluster_url')} / {db}",
                f".add database ['{db}'] viewers ('aadapp={client_id};{tenant}') 'sre-agent'", f"query ADX for source '{src['id']}'")
        elif t == "sharepoint_file":
            add("graph:Sites.Selected", "Microsoft Graph application permission Sites.Selected", "tenant", _graph_cmd("Sites.Selected", principal),
                "allow per-site access only (least privilege)", lambda: "Sites.Selected" in granted_graph)
            add("sp:read:" + str(src.get("site_url") or src.get("site_id")), "SharePoint site read", src.get("site_url") or src.get("site_id"),
                _sp_cmd(src, client_id, "read"), f"read the file for source '{src['id']}'")
        elif t == "blob_file":
            scope = f"<storage account resource id of '{src.get('account')}'>/blobServices/default/containers/{src.get('container')}"
            add("blobr:" + scope, "Storage Blob Data Reader", scope, rbac.format(p=principal, r="Storage Blob Data Reader", s=scope),
                f"read blobs for source '{src['id']}'")
    pub = config.get("publish") or {}
    if pub.get("sharepoint"):
        add("graph:Sites.Selected", "Microsoft Graph application permission Sites.Selected", "tenant", _graph_cmd("Sites.Selected", principal),
            "allow per-site access only (least privilege)", lambda: "Sites.Selected" in granted_graph)
        add("sp:write:" + str(pub["sharepoint"].get("site_url") or pub["sharepoint"].get("site_id")), "SharePoint site write",
            pub["sharepoint"].get("site_url") or pub["sharepoint"].get("site_id"), _sp_cmd(pub["sharepoint"], client_id, "write"),
            "publish reports and keep history in the folder " + str(pub["sharepoint"].get("folder")))
    if pub.get("blob"):
        b = pub["blob"]
        scope = f"<storage account resource id of '{b.get('account')}'>/blobServices/default/containers/{b.get('container')}"
        add("blobw:" + scope, "Storage Blob Data Contributor", scope, rbac.format(p=principal, r="Storage Blob Data Contributor", s=scope),
            "publish reports and keep history")
    return plan


# ----------------------------------------------------------------------------- humanized text
def _human(cond):
    if not cond:
        return "always"
    if "all" in cond:
        return " AND ".join(_human(c) for c in cond["all"])
    if "any" in cond:
        return "(" + " OR ".join(_human(c) for c in cond["any"]) + ")"
    if "not" in cond:
        return "NOT (" + _human(cond["not"]) + ")"
    op, value = cond.get("op", "eq"), cond.get("value")
    words = {"eq": "=", "ne": "≠", "gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "in": "in", "not_in": "not in", "contains": "contains",
             "regex": "matches", "empty": "is empty", "not_empty": "has a value", "expired": "is in the past",
             "expires_within_days": "expires within", "older_than_days": "older than", "newer_than_days": "within the last"}
    suffix = " days" if op.endswith("_days") else ""
    return f"`{cond.get('field')}` {words.get(op, op)}" + ("" if op in NO_VALUE_OPS else f" {json.dumps(value, ensure_ascii=False)}{suffix}")


def _sources_line(config):
    names = {"log_analytics": "Log Analytics", "resource_graph": "Azure Resource Graph", "graph": "Microsoft Graph", "arm": "Azure Resource Manager",
             "cost_management": "Cost Management", "adx": "Azure Data Explorer", "sharepoint_file": "SharePoint file", "blob_file": "Blob Storage file"}
    return ", ".join(f"{s['id']} ({names.get(s['type'], s['type'])})" for s in config["sources"])


# ----------------------------------------------------------------------------- generated blocks
TOOL_PARAMS = [
    {"name": "mode", "type": "string", "required": False, "value": "report",
     "description": "report = full branded HTML + PDF + CSV/JSON report; discover = read a few live rows per source and list columns (no report); "
                    "self_test = simulated data, no Azure calls, proves the logic and HTML"},
    {"name": "publish", "type": "string", "required": False, "value": "no",
     "description": "yes = also upload the report and its snapshot to the configured SharePoint/Blob target (history for next comparison); no = thread only"},
    {"name": "lookback_days", "type": "integer", "required": False, "value": "0",
     "description": "Days of data to analyse; 0 = CONFIG default"},
]


def _tool_description(config, meta):
    desc = meta["description"] or config["title"]
    return (f"{desc} Reads {_sources_line(config)} with the agent managed identity (read-only), evaluates {len(config['rules'])} rules, "
            "compares with the previous run and writes a branded HTML report, its PDF and CSV + JSON to the thread.")[:1000]


def _skill_md(config, meta):
    rules = "\n".join(f"| `{r['id']}` | {r.get('severity', 'medium')} | {r.get('title', r['id'])} | {_human(r.get('when'))} |" for r in config["rules"]) or "| - | - | no rules | - |"
    kpis = "\n".join(f"| {k.get('label', k['id'])} | {k.get('agg', 'count')}{(' of `' + k['field'] + '`') if k.get('field') else ''}"
                     f"{(' where ' + _human(k['where'])) if k.get('where') else ''} | {'lower' if k.get('good') == 'down' else 'higher' if k.get('good') == 'up' else 'n/a'} |"
                     for k in config["kpis"])
    pub = config.get("publish") or {}
    target = ("SharePoint " + str(pub["sharepoint"].get("folder"))) if pub.get("sharepoint") else ("Blob " + pub["blob"].get("container", "")) if pub.get("blob") else "none (thread only)"
    return f"""---
name: {meta['skill']}
description: {(meta['description'] or config['title']).strip()} Use when the user asks about {config['title'].lower()}, wants the report, the latest status, what changed since the last report, or to publish it.
---

# {config['title']}

**Business value:** {meta['description'] or config['title']}
**Data sources:** {_sources_line(config)} - read-only, with the agent managed identity.
**Publishing target:** {target}. **History / comparison:** {config.get('history', 'none')}.

## Tool

Always use `{meta['tool']}`. Never answer from memory or invent numbers.

| Parameter | Values | Use |
|---|---|---|
| `mode` | `report` (default), `discover`, `self_test` | `report` for any status question; `discover` to troubleshoot data/columns; `self_test` only to prove the tool works without Azure access |
| `publish` | `no` (default), `yes` | `yes` only when the user asks to publish/save/share or in the scheduled run |
| `lookback_days` | integer, 0 = default {config['lookback_days']} | when the user gives a period ("last 30 days") |

## Workflow

1. Call `{meta['tool']}` with `mode=report` (and `lookback_days` if the user gave a period).
2. Check `status`:
   - `OK` - answer with the structure below.
   - `PARTIAL` - answer with the data you have and say clearly which source failed (`sources[].status`, `sources[].error`); a failed source is **unknown, not zero**.
   - `FAILED` - do not show a report. Explain the error with the troubleshooting table and give the exact fix.
   - `SIMULATED` - only after `self_test`: say the data is synthetic.
3. If the user asks to publish, call again with `publish=yes` and give the `published[].url` links.

## Answer structure (user's language)

1. **Verdict** - one sentence: healthy / needs attention / critical, with the count of critical+high findings.
2. **Key indicators** - table of `kpis` with the change versus `previous_report_utc` from `comparison.kpis` (arrow and delta; say "first run" if there is no history).
3. **What changed** - `new_findings` and `resolved_findings` since the previous report.
4. **Top findings** - up to 10 from `top_findings`, most severe first, with the affected item.
5. **Report** - links from `files`: the HTML report first, then the PDF (same design, for e-mail and printing), then CSV/JSON; and `published` when present. Never rebuild, restyle or summarise the report into another document: deliver these files.
6. **Next step** - one concrete action for the owner of the most severe finding.

## Rules evaluated

| Rule | Severity | Title | Condition |
|---|---|---|---|
{rules}

## Indicators

| Indicator | Calculation | Better when |
|---|---|---|
{kpis}

## Troubleshooting

| `sources[].status` | Meaning | Fix |
|---|---|---|
| `FORBIDDEN` / `UNAUTHORIZED` | The agent managed identity lacks the permission | Grant the permission listed in the setup guide for that source, wait 5-10 minutes, run again |
| `NOT_FOUND` | Workspace, site, folder, file or container does not exist | Check the value in CONFIG (run `mode=discover`) |
| `BAD_REQUEST` | Query or path rejected | Fix the query in CONFIG; test it in the portal first |
| `CONFIG_ERROR` | Placeholder `<...>` still in CONFIG or missing identity | Edit CONFIG in the tool code |
| `AUTH_FAILED` | No managed identity token | Check the agent identity; `identity_client_id` or `AZURE_CLIENT_ID` |
| `NETWORK_ERROR` / `HTTP_ERROR` | Transient | Run again later |

## Guardrails

- Read-only: never change Azure resources, permissions or files other than publishing this report when asked.
- Never invent values, owners or dates; unknown is not zero.
- Do not paste the full CSV in chat; give the links.
"""


def _instructions(config, meta):
    return f"""You are the {config['title']} assistant. {meta['description']}

Use the skill `{meta['skill']}` and the tool `{meta['tool']}` for every answer; never answer from memory.

Intent -> call:
- status, report, findings, "what changed", "how are we" -> `{meta['tool']}` mode=report
- "publish", "save", "share", "send to SharePoint/storage" -> mode=report publish=yes
- a period ("last 30 days") -> lookback_days=30
- "which columns", "why is it empty", troubleshooting -> mode=discover
- "test the tool", "does it work" -> mode=self_test, then mode=discover

Answer in the user's language with the structure in the skill: verdict, key indicators with change versus the previous report, what changed, top findings, report links, next step.
If a source fails, say which one and how to fix it; a failed source is unknown, not zero. You are read-only: never modify Azure resources or permissions."""


def _task_prompt(config, meta):
    publish = "yes" if config.get("publish") else "no"
    return (f"Run `{meta['tool']}` with mode=report and publish={publish}. "
            f"Then write a short executive summary in {'Spanish' if config['language'] == 'es' else 'English'}: verdict, key indicators with change "
            "versus the previous report, new and resolved findings, the top 5 findings and the report links. "
            "If status is FAILED or PARTIAL, start the message with 'ACTION NEEDED' and say which source failed and the fix from the skill. "
            "Do not make any change in Azure.")


def _test_prompts(config, meta):
    """Prompts to send after picking the subagent with /agent in a new chat (the portal shows it as a chip, not as text)."""
    return ["run the self test of the tool and tell me if it works",
            "check the live data sources and show me the columns you see",
            f"give me the {config['title'].lower()} report for the last {config['lookback_days']} days",
            "what changed since the previous report and what should I fix first?"]
