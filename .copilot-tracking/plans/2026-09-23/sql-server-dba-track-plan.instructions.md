<!-- markdownlint-disable-file -->

# SQL Server DBA Track Implementation Plan

## User Requests

1. Create a new branch for an Azure SRE Agent track with a SQL Server DBA
   flavour.
2. Read the solution in `..\..\sre-agent-dba` without modifying it.
3. Adapt the required parts to this repository as a new track.
4. Add the SQL Server MCP code and deployment instructions under
   `Student/Resources/sql-server-mcp/`.
5. Map the source scenarios into challenges for the new track.

## Context Summary

The current repository has a single 20-challenge track, root-level Student and
Coach content, a static GitHub Pages experience, and a web build that only
copies root-level challenge files. The new content must use multi-track
navigation and preserve existing behavior.

Applicable guidance:

* RVAS content skill validation rules and templates
* Markdown and writing style instructions
* C# and C# test instructions for the copied server source
* Prompt builder instructions for the copied `SKILL.md`
* Frontend design skill for the GitHub Pages integration

## Implementation Checklist

### Phase 1: Resource bundle

<!-- parallelizable: true -->

* [x] Copy the MCP server source and tests without generated artifacts.
* [x] Copy the MIT license, SQL setup scripts, workloads, agent YAML, and skill.
* [x] Add an RVAS-specific deployment and validation guide.

### Phase 2: Student and Coach content

<!-- parallelizable: true -->

* [x] Create Challenge 00 through Challenge 08.
* [x] Create matching coach solutions.
* [x] Create the SQL Server DBA coach index and agenda.

### Phase 3: Repository integration

<!-- parallelizable: false -->

* [x] Add both tracks to the root README.
* [x] Make the web build preserve nested track paths.
* [x] Add Student and Coach track cards and drawer navigation to the website.
* [x] Add dependency update coverage for the MCP .NET and Docker assets.

### Phase 4: Validation

<!-- parallelizable: false -->

* [x] Validate challenge structure, numbering, and navigation links.
* [x] Treat the supplied MCP container as prevalidated, per user direction.
* [x] Build the GitHub Pages output and verify nested files.
* [x] Review the diff and confirm the source repository stayed unchanged.

## Success Criteria

* The branch contains a complete, navigable 00-08 SQL Server DBA track.
* Every source scenario maps to a student outcome and coach solution.
* `Student/Resources/sql-server-mcp/` builds independently and documents a
  secure Azure Container Apps deployment.
* Existing track links and behavior remain intact.
* Generated files and secrets are absent.
