# Example use case

What problem this solves, who it is for and what the agent produces.

## Prerequisites

List the permissions, roles and data sources the agent needs. Declare them under `package.requires`.

## Setup

1. Run `permissions/grant-example-permission.ps1`.
2. Run `usecases/_framework/usecases.sh deploy <folder> --endpoint <url>` to create the tool, skill, subagent and scheduled task.
3. Run `usecases.sh verify <folder> --endpoint <url>` to check the agent.

Use `usecases.sh diff <folder> --endpoint <url>` to compare local manifests with the live agent, or `usecases.sh portal-blocks <folder>` for copy-ready text.

## Test prompts

* Run the example check.
