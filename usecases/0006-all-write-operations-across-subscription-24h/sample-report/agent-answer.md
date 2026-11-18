<!-- Agent answer from the live Azure SRE Agent run of 2026-11-06, pseudonymized with the same mapping as the sample files in this folder. Links point to those files. -->

I ran the 24-hour change digest. In the `rg-app-prod-weu` resource group, there are still two open exposures: the `allow-ssh-office` rule on `nsg-app-frontend` was widened to allow SSH (port 22) from any source, and Key Vault `kv-app-prod-weu` was set to allow network access by default. The digest shows nothing that reversed either one.

**Report files**
- [HTML report](change-digest-20261106T115407Z-07932d59.html) — `sample-run/change-digest-20261106T115407Z-07932d59.html`
- [JSON snapshot](change-digest-20261106T115407Z-07932d59-snapshot.json) — `sample-run/change-digest-20261106T115407Z-07932d59-snapshot.json`
- [Changes CSV](change-digest-20261106T115407Z-07932d59-changes.csv) — `sample-run/change-digest-20261106T115407Z-07932d59-changes.csv`
- [Property diffs CSV](change-digest-20261106T115407Z-07932d59-property-diffs.csv) — `sample-run/change-digest-20261106T115407Z-07932d59-property-diffs.csv`

## Summary
Window: 2026-11-05 11:53:59 UTC to 2026-11-06 11:53:59 UTC.

**18 of 105 changes are relevant (8 high, 10 medium). There are also 9 events from role assignments and the Activity Log.**

| Total | High | Medium | Low | Noise | Deletes | Security | New role assignments | Activity Log gaps | First-time actors | Bursts | After hours | Click-ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 105 | 8 | 10 | 27 | 60 (57%) | 9 | 12 | 3 | 6 | 3 | 1 | 0 | 0 |

Almost all relevant activity was one session by `alex.ops@contoso.com` in `rg-app-prod-weu`, between about 10:36 and 10:47 UTC on 2026-11-06.

## High items
| When (UTC) | What | Where | Who | Why |
|---|---|---|---|---|
| 11-06 10:38:03 | Created `pip-temp-test` | rg-app-prod-weu | alex.ops@… | New public IP address (reachable from the Internet) |
| 11-06 10:39:24 | Updated `nsg-app-frontend` | rg-app-prod-weu | alex.ops@… | Added rule `allow-rdp-from-internet`: inbound Allow from Internet to 3389 (RDP) |
| 11-06 10:39:29 | Updated `nsg-app-frontend` | rg-app-prod-weu | alex.ops@… | Added rule `allow-ssh-office`: inbound Allow 198.51.100.0/24 to port 22 |
| 11-06 10:39:31 | Updated `kv-app-prod-weu` | rg-app-prod-weu | alex.ops@… | Network default action changed from (not set) to **Allow**; firewall allow rule added for 203.0.113.10/32 |
| 11-06 10:43:19 | Updated `nsg-app-frontend` | rg-app-prod-weu | alex.ops@… | `allow-ssh-office` widened to **any source (\*)** on port 22 (SSH) |
| 11-06 10:44:44 | Resource lock removed (Activity Log) | rg-app-prod-weu | alex.ops@… | Removed lock |
| 11-06 10:44:49 | Deleted `pip-temp-test` | rg-app-prod-weu | alex.ops@… | Deleted by a person |
| 11-06 10:45:02 | Diagnostic setting removed (Activity Log) | rg-app-prod-weu | alex.ops@… | Monitoring gap |
| 11-06 11:30:20 | Updated `nsg-app-frontend` | rg-app-prod-weu | `00000000-0000-4000-8000-93b7b7156451` | Removed `allow-rdp-from-internet`, so the RDP exposure is closed |
| 11-05 15:54:49 | Deleted `kv-shared-secrets-01` | rg-platform-shared | alex.ops@… | Key Vault deleted by a person |

The rule lists in chat were truncated: relevant changes showed 12 of 27 rows and security changes 11 of 21. The HTML report has every row.

## Medium items
- Created `kv-app-prod-weu`, `nsg-app-frontend`, `disk-app-data` and `stappprodweu` (10:36–10:37 UTC), all in `rg-app-prod-weu`.
- Two updates to `disk-app-data` at 10:39 and 10:43 UTC.
- A diagnostic setting created or changed in `rg-app-prod-weu` at 10:43:36 UTC. It was removed about 90 seconds later.
- `rg-app-prod-weu` recorded as created at 10:46:40 UTC, after its resources already existed. Check the property diffs CSV before reading anything into this.
- Created resource group `rg-shared-secrets` at 2026-11-05 16:04 UTC.
- The 3 new role assignments listed below.

## Deletes
| When (UTC) | Resource | Type | Who | Client | correlationId |
|---|---|---|---|---|---|
| 11-06 10:44:49 | pip-temp-test | Public IP address | alex.ops@… (recovered from the Activity Log; Change Analysis recorded no actor) | Unspecified | 00000000-0000-4000-8000-feabc6e16ff8 |
| 11-05 15:54:49 | kv-shared-secrets-01 | Key Vault | alex.ops@… | CLI | 00000000-0000-4000-8000-de5873c1a987 |
| 11-05 12:53 | AKS node `aks-default-node1`: VM, extensions, NIC, disk | Low; AKS cleanup in a platform-managed resource group | aks-prod-weu and Azure services | Go SDK and service apps | e8836f04-…, 7136341a-… |

## Security-relevant changes
- **Still open:** `nsg-app-frontend` rule `allow-ssh-office` allows SSH from any source.
- **Still open:** `kv-app-prod-weu` network default action is Allow.
- **Closed:** RDP from the Internet was opened at 10:39:24 and removed at 11:30:20 UTC.
- **Closed:** public IP `pip-temp-test` existed for about 7 minutes.
- **Monitoring and protection gaps:** in `rg-app-prod-weu`, a resource lock and a diagnostic setting were both removed, and the digest shows neither restored.

The chat views showed no later change to the SSH rule or the Key Vault default action. The chat lists were truncated, though, so check the HTML report before acting.

## New role assignments
All three were created by alex.ops@… and are medium level:
- **Reader** on resource group `rg-app-prod-weu`, given to `id-sre-agent` (this agent's managed identity), 11-06 10:39:52 UTC.
- **Key Vault Secrets User** on `kv-shared-secrets-02`, given to `id-sre-agent`, 11-05 15:56:32 UTC.
- **Key Vault Administrator** on `kv-shared-secrets-02`, given to user `00000000-0000-4000-8000-d88f5dbb6ae5`, 11-05 15:56:28 UTC.

## Activity Log gap events (6)
These are changes that Change Analysis cannot see, so they come from the Activity Log. Three are shown above: lock removed, diagnostic setting removed, and diagnostic setting created or changed. The other 3 are in the HTML report.

## Unusual activity
- **Burst:** 13 changes by alex.ops@… in `rg-app-prod-weu` between 10:36 and 10:46 UTC. They include creates, NSG and Key Vault exposure changes, the delete of `pip-temp-test`, and the lock and diagnostic setting removals.
- **First-time actors on a resource group:**
  - `00000000-0000-4000-8000-93b7b7156451` on `rg-app-prod-weu` (the RDP rule removal). This principal's name could not be looked up because application names are not configured (see Coverage).
  - alex.ops@… on `rg-app-prod-weu` and on `rg-shared-secrets`.
- No after-hours changes and no click-ops (manual changes in the Azure portal).

The flags and fields above do not establish intent. Before deciding anything, check each change's `changedByType`, `clientType`, `operation` and `correlationId` in the property diffs CSV.

## Coverage
Status is **ok**: 16 sources read, Activity Log complete, no issues reported.
- **Not configured:** names for applications and service principals (Microsoft Graph), which is why `e888bb96-…` shows only as an ID. Optional fix: grant the agent's identity the Microsoft Graph `Application.Read.All` permission.
- **Not covered by this digest:** data-plane changes, and anything outside the configured subscription.

## Suggested actions
I have not changed anything. These would need a person to carry them out through an approved change:
1. Restrict or remove `allow-ssh-office` on `nsg-app-frontend`, which currently allows any source.
2. Set the network default action on `kv-app-prod-weu` back to Deny.
3. Restore the resource lock and the diagnostic setting in `rg-app-prod-weu`.
4. Identify principal `00000000-0000-4000-8000-93b7b7156451`.
5. Confirm the deletion of `kv-shared-secrets-01` was intended. If it wasn't, it may be recoverable with soft delete.
6. Review whether user `bcc1a6f4-…` needs the Key Vault Administrator assignment.

## Artifacts & links
- [HTML report](change-digest-20261106T115407Z-07932d59.html)
- [JSON snapshot](change-digest-20261106T115407Z-07932d59-snapshot.json)
- [Changes CSV](change-digest-20261106T115407Z-07932d59-changes.csv)
- [Property diffs CSV](change-digest-20261106T115407Z-07932d59-property-diffs.csv)