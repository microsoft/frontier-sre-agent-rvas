"""
cost_rank: Rank Azure subscriptions and resource groups by amortized spend.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to
query Azure Cost Management at subscription scope over a trailing window, groups
cost by resource group, and selects the top decile with a floor so small tenants
still return a usable set. Falls back to the Consumption usage details read when
the Cost Management query action is not available under the current permissions.

Returns a JSON serializable dict. See references/ranking-method.md.

Heavy imports (azure-identity, requests) are loaded lazily inside functions so
the pure ranking helper can be imported and unit tested without those packages.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _bootstrap_shared_tools():
    here = Path(__file__).resolve().parent
    candidates = [here, here / "tools"] + [parent / "shared" / "tools" for parent in list(here.parents)[:5]]
    for candidate in candidates:
        if (candidate / "azure_http.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ModuleNotFoundError("Bundle shared tools, including azure_http.py, with this collector.")


_bootstrap_shared_tools()

ARM_ENDPOINT = "https://management.azure.com"
MAX_PAGES = 200
SOURCES = [
    {"title": "Cost Management query pagination", "url": "https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties"},
    {"title": "Consumption usage details", "url": "https://learn.microsoft.com/rest/api/consumption/usage-details/list"},
]


def _select_top(items, top_percent, minimum):
    """Tag each item with a 1-based rank and a selected flag.

    items: a list of dicts already sorted by cost descending.
    Selection count: min(N, max(minimum, ceil(N * top_percent / 100))).
    Returns (items, selected_count).
    """
    n = len(items)
    if n == 0:
        return items, 0
    count = min(n, max(int(minimum), math.ceil(n * float(top_percent) / 100.0)))
    for index, item in enumerate(items):
        item["rank"] = index + 1
        item["selected"] = index < count
    return items, count


def _token():
    from agent_identity import agent_token

    return agent_token(f"{ARM_ENDPOINT}/.default")


def _list_subscriptions(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    subscriptions = []
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        for item in body.get("value", []):
            if item.get("state") in (None, "Enabled"):
                subscriptions.append(
                    {
                        "id": item["subscriptionId"],
                        "name": item.get("displayName", item["subscriptionId"]),
                    }
                )
        url = body.get("nextLink")
    return subscriptions


def _query_cost_management(headers, subscription_id, start, end):
    """Amortized cost grouped by resource group at subscription scope.

    Returns (rows, currency) with (resource_group, cost, currency) rows.
    Raises on failure so the caller can fall back to Consumption.
    """
    import azure_http as requests

    url = (
        f"{ARM_ENDPOINT}/subscriptions/{subscription_id}"
        "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    )
    payload = {
        "type": "AmortizedCost",
        "timeframe": "Custom",
        "timePeriod": {"from": start, "to": end},
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceGroupName"}],
        },
    }
    rows = []
    for _ in range(MAX_PAGES):
        if not url.startswith(ARM_ENDPOINT + "/"):
            raise ValueError("Unexpected Cost Management continuation host.")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        properties = response.json().get("properties", {})
        columns = [c["name"] for c in properties.get("columns", [])]
        cost_index = columns.index("Cost")
        rg_index = columns.index("ResourceGroupName")
        currency_index = columns.index("Currency")
        for row in properties.get("rows", []):
            if row[cost_index] is None:
                raise ValueError("Cost Management row cost unknown; baseline not established.")
            rows.append((row[rg_index] or "(unassigned)", float(row[cost_index]), row[currency_index] or "Unknown"))
        url = properties.get("nextLink")
        if not url:
            currencies = {row[2] for row in rows}
            return rows, next(iter(currencies)) if len(currencies) == 1 else None
    raise RuntimeError("Cost Management pagination incomplete: page limit reached.")


def _query_consumption(headers, subscription_id, start, end):
    """Fallback: aggregate Consumption usage details cost by resource group."""
    import azure_http as requests

    url = (
        f"{ARM_ENDPOINT}/subscriptions/{subscription_id}"
        "/providers/Microsoft.Consumption/usageDetails"
        f"?api-version=2023-05-01&$filter=properties/usageStart ge '{start}'"
        f" and properties/usageEnd le '{end}'"
    )
    totals = {}
    pages = 0
    while url and pages < MAX_PAGES:
        if not url.startswith(ARM_ENDPOINT + "/"):
            raise ValueError("Unexpected Consumption continuation host.")
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
        body = response.json()
        for item in body.get("value", []):
            props = item.get("properties", {})
            resource_group = props.get("resourceGroup") or props.get("resourceGroupName") or "(unassigned)"
            cost = props.get("cost", props.get("costInBillingCurrency"))
            if cost is None:
                raise ValueError("Consumption row cost unknown; baseline not established.")
            currency = props.get("billingCurrency") or props.get("billingCurrencyCode") or props.get("currency") or "Unknown"
            key = (resource_group, currency)
            totals[key] = totals.get(key, 0.0) + float(cost)
        url = body.get("nextLink")
        pages += 1
    if url:
        raise RuntimeError("Consumption pagination incomplete: page limit reached.")
    currencies = {key[1] for key in totals}
    return [(rg, cost, currency) for (rg, currency), cost in totals.items()], next(iter(currencies)) if len(currencies) == 1 else None


def main(
    top_percent: float = 10.0,
    min_subscriptions: int = 3,
    min_resource_groups: int = 5,
    lookback_days: int = 30,
    subscription_ids: list = None,
) -> dict:
    """Rank visible subscriptions and resource groups by amortized spend.

    top_percent: the top percentage to select at each level.
    min_subscriptions: floor on the number of subscriptions to select.
    min_resource_groups: floor on the number of resource groups per subscription.
    lookback_days: the trailing window in days.
    subscription_ids: optional explicit list; when omitted, enumerate visible subscriptions.
    """
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=int(lookback_days))
    start = start_date.isoformat()
    end = end_date.isoformat()

    notes = []

    if subscription_ids:
        subscriptions = [{"id": sub, "name": sub} for sub in subscription_ids]
    else:
        try:
            subscriptions = _list_subscriptions(headers)
        except Exception as error:  # noqa: BLE001 - surface the failure to the agent
            return {"error": f"Could not list subscriptions: {error}", "subscriptions": [], "assessment_status": "Not assessed", "sources": SOURCES}

    currencies = set()
    resource_groups = {}
    ranking_groups = {}
    assessed = 0
    for sub in subscriptions:
        rows = []
        sub["data_source"] = "CostManagement"
        sub["cost_basis"] = "AmortizedCost"
        sub["assessment_status"] = "Complete"
        try:
            rows, currency = _query_cost_management(headers, sub["id"], start, end)
        except Exception as cost_error:  # noqa: BLE001 - fall back to Consumption
            try:
                rows, currency = _query_consumption(headers, sub["id"], start, end)
                sub["data_source"] = "Consumption"
                sub["cost_basis"] = "UsageDetailsActualCost"
                sub["assessment_status"] = "Partial"
                notes.append(f"Subscription {sub['id']}: used Consumption fallback, not an amortized baseline ({cost_error}).")
            except Exception as consumption_error:  # noqa: BLE001
                notes.append(f"Subscription {sub['id']}: no cost data ({consumption_error}).")
                sub["assessment_status"] = "Not assessed"
        if sub["assessment_status"] != "Not assessed":
            assessed += 1
        totals = {}
        rg_totals = {}
        for rg, cost, currency in rows:
            currencies.add(currency)
            totals[currency] = totals.get(currency, 0.0) + cost
            rg_totals[(rg, currency)] = rg_totals.get((rg, currency), 0.0) + cost
        rg_items = []
        for currency in sorted(totals):
            group = sorted(
                [{"name": rg, "cost": round(cost, 2), "currency": curr} for (rg, curr), cost in rg_totals.items() if curr == currency],
                key=lambda item: item["cost"], reverse=True,
            )
            _select_top(group, top_percent, min_resource_groups)
            rg_items.extend(group)
            key = f"{currency}:{sub['cost_basis']}"
            ranking_groups.setdefault(key, []).append({"id": sub["id"], "name": sub["name"], "cost": totals[currency], "currency": currency})
        resource_groups[sub["id"]] = rg_items
        sub["totals_by_currency"] = {c: round(v, 2) for c, v in totals.items()}
        sub["currency"] = next(iter(totals)) if len(totals) == 1 else None
        sub["total_cost"] = round(next(iter(totals.values())), 2) if len(totals) == 1 else None
        sub["selected"] = False

    selected = set()
    for group in ranking_groups.values():
        group.sort(key=lambda item: item["cost"], reverse=True)
        _select_top(group, top_percent, min_subscriptions)
        selected.update(item["id"] for item in group if item["selected"])
    for sub in subscriptions:
        sub["selected"] = sub["id"] in selected

    if len(currencies) > 1:
        notes.append(f"Mixed currencies across subscriptions: {sorted(currencies)}. Totals are not converted.")

    selected_ids = [sub["id"] for sub in subscriptions if sub.get("selected")]
    selected_resource_groups = {sid: resource_groups.get(sid, []) for sid in selected_ids}

    return {
        "assessment_status": "Not assessed" if not assessed else ("Partial" if notes or "Unknown" in currencies else "Complete"),
        "sources": SOURCES,
        "lookback_days": int(lookback_days),
        "window": {"from": start, "to": end},
        "currency": sorted(currencies)[0] if len(currencies) == 1 else None,
        "data_source": next(iter({s["data_source"] for s in subscriptions})) if len({s["data_source"] for s in subscriptions}) == 1 else "Mixed",
        "ranking_groups": ranking_groups,
        "subscriptions": subscriptions,
        "selected_subscriptions": selected_ids,
        "resource_groups": selected_resource_groups,
        "notes": notes,
    }


def _cli():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Rank Azure subscriptions and resource groups by amortized spend.")
    parser.add_argument("--top-percent", type=float, default=10.0)
    parser.add_argument("--min-subscriptions", type=int, default=3)
    parser.add_argument("--min-resource-groups", type=int, default=5)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--subscriptions", type=str, default=None, help="Comma separated subscription ids.")
    args = parser.parse_args()
    subscription_ids = [s.strip() for s in args.subscriptions.split(",") if s.strip()] if args.subscriptions else None
    result = main(
        top_percent=args.top_percent,
        min_subscriptions=args.min_subscriptions,
        min_resource_groups=args.min_resource_groups,
        lookback_days=args.lookback_days,
        subscription_ids=subscription_ids,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
