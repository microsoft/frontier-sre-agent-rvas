<!-- Agent answer from the live Azure SRE Agent run of 2026-11-12, pseudonymized with the same mapping as the sample files in this folder. Links point to those files. -->

# Monthly Azure FinOps review: October 2026

**Files**
- [HTML report](finops-review-2026-10-20261112T161319Z-923eef2b.html): /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-c86c81611635/finops-review-reports/finops-review-2026-10-20261112T161319Z-923eef2b.html
- [JSON snapshot](finops-review-2026-10-20261112T161319Z-923eef2b-snapshot.json): /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-c86c81611635/finops-review-reports/finops-review-2026-10-20261112T161319Z-923eef2b-snapshot.json
- [Findings CSV](finops-review-2026-10-20261112T161319Z-923eef2b-findings.csv): /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-c86c81611635/finops-review-reports/finops-review-2026-10-20261112T161319Z-923eef2b-findings.csv
- [Cost-by-resource CSV](finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-resource.csv): /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-c86c81611635/finops-review-reports/finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-resource.csv
- [Cost-by-project CSV](finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-project.csv): /root/sreagent/terminalRoot/tmp/ThreadFiles/00000000-0000-4000-8000-c86c81611635/finops-review-reports/finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-project.csv

**Verdict: Action required.** November is on track to go about 29% over budget. October cost 5,051 USD, up 8.9% on September. The review found 26 ways to save, worth about 305 USD a month in total.

## Key numbers (USD, live data)
| Metric | Value |
|---|---|
| Last full month (Oct 2026) | **5,051.32**, up 8.9% (Sep: 4,639.02) |
| November so far | 1,870.80 |
| November forecast vs. budget | **4,846.51 vs. 3,750.00 (129%)**. Azure's own forecast for budget `budget-contoso-monthly` is 4,784.60 |
| Estimated savings per month | 304.78 |
| Untagged share | **100%** (every cost is missing at least one of `costcenter`, `owner`, `environment`) |
| Unusual days / jumps / new spend | 1 / 3 / 0 |

## Cost per project
The `Project` tag is used to group costs by project. I didn't set it: the review **picked it up automatically**, and it covers 98.4% of the cost across 6 projects. Please confirm it's the right tag or tell me the one you use. This is a separate check from the allocation tags in the 100% untagged figure above.

| Project | Oct | Sep | Change | Nov so far | Share | Savings/mo | Findings |
|---|---|---|---|---|---|---|---|
| Shared infrastructure | 1,953.66 | 1,889.82 | +3.4% | 720.58 | 38.7% | 22.89 | 8 |
| E-commerce web | 1,494.95 | 1,009.27 | **+48.1%** | 560.12 | 29.6% | 1.54 | 5 |
| Sandbox | 771.02 | 753.65 | +2.3% | 274.96 | 15.3% | 80.35 | 17 |
| Observability | 568.88 | 737.02 | −22.8% | 218.61 | 11.3% | 0.00 | 0 |
| Data platform | 159.06 | 153.90 | +3.3% | 58.63 | 3.1% | 0.00 | 0 |
| Security and identity | 21.80 | 21.03 | +3.7% | 7.75 | 0.4% | 0.00 | 0 |
| Unallocated | 81.95 | 74.33 | +10.3% | 30.16 | 1.6% | 0.00 | 0 |

## Actions (all 8)
| Severity | What | Where | Saving/mo |
|---|---|---|---|
| High | No compute is covered by a reservation or savings plan: 908.09 USD of eligible compute ran at on-demand prices in October | Azure Advisor | 200.00 |
| High | 100% of the cost is missing `costcenter`, `owner` or `environment`. Start tagging with `rg-network-hubs-eus` | Allocation | – |
| High | Resource group `MC_rg-aks-prod_aks-prod-swc_swedencentral` cost doubled (+100%): 368.14 → 734.49 | Resource group | – |
| High | Budget `budget-contoso-monthly`: forecast 4,784.60 vs. budget 3,750.00 | Contoso Production | – |
| Medium | Resource group `rg-aks-prod` cost doubled (+100%): 120.63 → 241.12 | Resource group | – |
| Medium | Virtual Machines cost rose 45%: 527.34 → 764.08 | Whole scope | – |
| Medium | Unusual cost on 28 Oct: 204.50 vs. a typical 162.56, driven by Foundry Tools (+42.58) | Daily cost | – |
| Low | VM `arcmgmt-Client` is deallocated but its disks still bill | rg-arc-management | 17.21 |

The rest of the 305 USD comes from the other savings items (idle or orphaned resources), which are listed in the HTML report and the findings CSV.

**Notes**
- The two AKS resource groups and Virtual Machines account for most of the October increase. Their owners should confirm whether the growth was planned.
- The 200 USD a month is Advisor's best single commitment option, either a reservation or a savings plan. Buying either is a finance decision, and only one should be bought, not both.
- All savings figures are estimates. This review changed nothing. Any tagging, deletion, budget change or purchase has to be done by a person through an approved change.

## Coverage
Status is **ok**: 1 subscription was read with no issues. Cost Management throttled a few requests (2 during the report run), but the retries succeeded, so nothing is missing. Reservation and savings plan usage isn't checked here because it needs tenant-level reader access.

## Artifacts & links
- [HTML report](finops-review-2026-10-20261112T161319Z-923eef2b.html)
- [JSON snapshot](finops-review-2026-10-20261112T161319Z-923eef2b-snapshot.json)
- [Findings CSV](finops-review-2026-10-20261112T161319Z-923eef2b-findings.csv)
- [Cost-by-resource CSV](finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-resource.csv)
- [Cost-by-project CSV](finops-review-2026-10-20261112T161319Z-923eef2b-cost-by-project.csv)
