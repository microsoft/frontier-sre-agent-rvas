"""
commitment_recommendations: Reservation and savings plan recommendations.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
reservation recommendations (covered by Reader) and, on a best effort basis,
savings plan benefit recommendations, for each subscription in scope.

Returns a JSON serializable dict. Heavy imports are loaded lazily inside
functions.
"""

import sys
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
SOURCES = [
    {"title": "Reservation recommendations", "url": "https://learn.microsoft.com/rest/api/consumption/reservation-recommendations/list"},
    {"title": "Benefit recommendations", "url": "https://learn.microsoft.com/rest/api/cost-management/benefit-recommendations/list"},
]


def _token():
    from agent_identity import agent_token

    return agent_token(f"{ARM_ENDPOINT}/.default")


def _get_all(headers, url):
    import azure_http as requests

    items = []
    pages = 0
    while url and pages < 20:
        if not url.startswith(ARM_ENDPOINT + "/"):
            raise ValueError("Unexpected commitment continuation host.")
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
        body = response.json()
        items.extend(body.get("value", []))
        url = body.get("nextLink")
        pages += 1
    if url:
        raise RuntimeError("Commitment pagination incomplete: page limit reached.")
    return items


def _reservation_recommendations(headers, subscription_id, look_back):
    url = (
        f"{ARM_ENDPOINT}/subscriptions/{subscription_id}"
        "/providers/Microsoft.Consumption/reservationRecommendations"
        f"?api-version=2023-05-01&$filter=properties/lookBackPeriod eq '{look_back}'"
    )
    out = []
    for item in _get_all(headers, url):
        props = item.get("properties", {})
        out.append(
            {
                "kind": "reservation",
                "recommendation_id": item.get("id"),
                "source_properties": props,
                "savings_horizon": "Not normalized to monthly",
                "sku": props.get("skuName") or props.get("displayName"),
                "scope": props.get("scope"),
                "term": props.get("term"),
                "recommended_quantity": props.get(
                    "recommendedQuantityNormalized", props.get("recommendedQuantity")
                ),
                "net_savings": props.get("netSavings"),
                "currency": props.get("currencyCode") or props.get("netSavingsCurrency"),
                "location": item.get("location"),
            }
        )
    return out


def _savings_plan_recommendations(headers, subscription_id, look_back):
    # Best effort. May return nothing under Reader in some tenants.
    url = (
        f"{ARM_ENDPOINT}/subscriptions/{subscription_id}"
        "/providers/Microsoft.CostManagement/benefitRecommendations"
        f"?api-version=2024-08-01&$filter=properties/lookBackPeriod eq '{look_back}'"
    )
    out = []
    for item in _get_all(headers, url):
        props = item.get("properties", {})
        out.append(
            {
                "kind": "savings_plan",
                "recommendation_id": item.get("id"),
                "source_properties": props,
                "savings_horizon": "Not normalized to monthly",
                "term": props.get("term"),
                "net_savings": props.get("savingsAmount") or props.get("netSavings"),
                "currency": props.get("currencyCode"),
                "scope": props.get("scope"),
            }
        )
    return out


def main(subscription_ids: list = None, look_back_period: str = "Last30Days") -> dict:
    """Return reservation and savings plan recommendations for the given subscriptions.

    subscription_ids: the subscriptions to analyze. Pass the selected_subscriptions
    from cost_rank. If omitted, returns an error asking for the list.
    look_back_period: one of Last7Days, Last30Days, Last60Days.
    """
    if not subscription_ids:
        return {"error": "Provide subscription_ids, for example the selected_subscriptions from cost_rank.", "assessment_status": "Not assessed", "sources": SOURCES}

    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    results = {}
    notes = []
    completed_sources = 0
    for subscription_id in subscription_ids:
        reservations = []
        savings_plans = []
        try:
            reservations = _reservation_recommendations(headers, subscription_id, look_back_period)
            completed_sources += 1
        except Exception as error:  # noqa: BLE001 - surface, continue with others
            notes.append(f"Subscription {subscription_id}: reservation recommendations unavailable ({error}).")
        try:
            savings_plans = _savings_plan_recommendations(headers, subscription_id, look_back_period)
            completed_sources += 1
        except Exception as error:  # noqa: BLE001 - best effort under Reader
            notes.append(f"Subscription {subscription_id}: savings plan recommendations unavailable ({error}).")
        if any(not rec.get("currency") or rec.get("net_savings") is None for rec in reservations + savings_plans):
            notes.append(f"Subscription {subscription_id}: recommendation amount or currency not established; inspect source_properties before pricing.")
        results[subscription_id] = {"reservations": reservations, "savings_plans": savings_plans}

    return {
        "look_back_period": look_back_period,
        "assessment_status": "Not assessed" if not completed_sources else ("Partial" if notes else "Complete"),
        "sources": SOURCES,
        "estimated_total_net_savings": None,
        "aggregation_policy": "Individual opportunities only. Currency, term, benefit scope, existing coverage and overlapping reservation/savings plan alternatives must be reconciled before estimating realizable monthly savings.",
        "by_subscription": results,
        "notes": notes,
    }


def _cli():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Reservation and savings plan recommendations.")
    parser.add_argument("--subscriptions", type=str, required=True, help="Comma separated subscription ids.")
    parser.add_argument("--look-back-period", type=str, default="Last30Days")
    args = parser.parse_args()
    subscription_ids = [s.strip() for s in args.subscriptions.split(",") if s.strip()]
    print(json.dumps(main(subscription_ids=subscription_ids, look_back_period=args.look_back_period), indent=2))


if __name__ == "__main__":
    _cli()
