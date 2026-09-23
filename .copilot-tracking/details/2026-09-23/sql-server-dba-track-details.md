<!-- markdownlint-disable-file -->

# SQL Server DBA Track Implementation Details

## Resource Operations

Copy `mcp-mssql-main/` into `Student/Resources/sql-server-mcp/`, excluding
`bin/`, `obj/`, local launch profiles, and repository-specific agent
instructions. Place the source agent definition under `agent/`, SQL setup
scripts under `sql/`, and deterministic workloads under `workloads/`.

Replace the upstream README with a workshop-specific deployment guide. Keep the
upstream server code and tests unchanged.

## Content Operations

Use multi-track Home links to `../../README.md`. Challenge 00 includes runnable
pre-flight checks. Agent challenges use capability callouts and checkbox
success criteria. Student content describes outcomes rather than revealing
diagnostic queries. Coach solutions contain exact workload commands, expected
evidence, errors, and recovery guidance.

## Integration Operations

Update the root README with a track selector and complete SQL Server challenge
table. Add a dedicated web section rather than mixing DBA challenges into the
existing 00-19 sequence. Extend the drawer file arrays and make `build-web`
copy nested challenge and solution paths.

## Validation Operations

Run `dotnet test` from the MCP resource root, `make build-web`, a local link and
structure validator, and `git diff --check`. Verify nested pages exist in
`_site/` and confirm the source repository has no worktree changes.

