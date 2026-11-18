# Test prompts

In a new chat, type `/agent`, select `sre-usecase-builder` and describe an idea in one or two sentences, in any language. The builder needs no configuration; live checks use only what the agent identity can already read.

## 1. Orphaned managed disks (Azure Resource Graph)

```text
I need a weekly report of orphaned managed disks (not attached to any VM) across my subscriptions, with size and SKU, so we can clean up waste.
```

**Expected:** No questions. The builder calls catalog, environment and scaffold, then answers with the use case, the verification (lint, self_test, live discover, status READY_LIVE_VERIFIED), the permissions with exact az commands, the four blocks (Python tool, skill, subagent, scheduled task) and file links, including the self-test report in HTML and PDF.

## 2. Expiring Entra app secrets (Microsoft Graph)

```text
Every Monday, warn me about Entra ID application secrets that have expired or expire in the next 30 days, so no integration breaks.
```

**Expected:** A generated Microsoft Graph use case; when the identity lacks Application.Read.All, the permissions section gives the exact grant and the status is not LIVE_VERIFIED.

## 3. Kit smoke test from the Test playground

```text
Run the kit catalog.
```

Tool call:

```json
{"operation": "catalog"}
```

**Expected:** status OK, kit_version 3.1.1 and the six recipes, in a result under the tool-result size limit.

## 4. Customer branding

```text
Build a monthly report of public IPs not associated with any resource for Contoso (https://www.contoso.com), with its logo and colours.
```

**Expected:** The builder calls brand with the website, shows the sample branded report and generates the use case with that identity; the logo is embedded by the kit, never passed through the chat.
