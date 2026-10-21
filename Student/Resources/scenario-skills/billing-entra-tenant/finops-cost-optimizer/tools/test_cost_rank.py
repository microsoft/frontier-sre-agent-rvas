"""Unit test for the cost_rank selection math. No Azure calls are made.

Run from the tools directory:
    python test_cost_rank.py
"""

from cost_rank import _select_top
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import cost_rank as cr


def _make(n):
    return [{"name": f"item-{i}", "cost": float(n - i)} for i in range(n)]


def _selected_count(items):
    return sum(1 for item in items if item["selected"])


def test_floor_applies_for_three_subscriptions():
    items, count = _select_top(_make(3), top_percent=10, minimum=3)
    assert count == 3
    assert _selected_count(items) == 3


def test_floor_for_six_subscriptions():
    items, count = _select_top(_make(6), top_percent=10, minimum=3)
    assert count == 3
    assert _selected_count(items) == 3


def test_top_decile_for_two_hundred():
    items, count = _select_top(_make(200), top_percent=10, minimum=3)
    assert count == 20
    assert _selected_count(items) == 20


def test_resource_group_floor():
    items, count = _select_top(_make(6), top_percent=10, minimum=5)
    assert count == 5


def test_ranks_are_one_based_and_ordered():
    items, _ = _select_top(_make(4), top_percent=10, minimum=3)
    assert [item["rank"] for item in items] == [1, 2, 3, 4]


def test_empty_set():
    items, count = _select_top([], top_percent=10, minimum=3)
    assert count == 0
    assert items == []


def _response(body):
    return SimpleNamespace(json=lambda: body, raise_for_status=lambda: None, status_code=200, headers={}, close=Mock())


def test_cost_management_follows_properties_next_link(monkeypatch):
    columns = [{"name": name} for name in ("Cost", "ResourceGroupName", "Currency")]
    post = Mock(side_effect=[
        _response({"properties": {"columns": columns, "rows": [[10, "rg", "USD"]], "nextLink": cr.ARM_ENDPOINT + "/next"}}),
        _response({"properties": {"columns": columns, "rows": [[20, "rg", "EUR"]]}}),
    ])
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    rows, currency = cr._query_cost_management({}, "a", "start", "end")
    assert rows == [("rg", 10, "USD"), ("rg", 20, "EUR")]
    assert currency is None
    assert post.call_count == 2


def test_cost_management_uses_shared_transient_retries(monkeypatch):
    import azure_http

    columns = [{"name": name} for name in ("Cost", "ResourceGroupName", "Currency")]
    throttled, unavailable = _response({}), _response({})
    throttled.status_code, unavailable.status_code = 429, 503
    throttled.headers = unavailable.headers = {"Retry-After": "0"}
    post = Mock(side_effect=[throttled, unavailable, _response({"properties": {"columns": columns, "rows": [[10, "rg", "USD"]]}})])
    sleep = Mock()
    monkeypatch.setattr(azure_http.time, "sleep", sleep)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    rows, currency = cr._query_cost_management({}, "a", "start", "end")
    assert rows == [("rg", 10, "USD")] and currency == "USD"
    assert post.call_count == 3 and sleep.call_count == 2
    assert all(call.kwargs["allow_redirects"] is False and call.kwargs["timeout"] == 120 for call in post.call_args_list)
    throttled.close.assert_called_once()
    unavailable.close.assert_called_once()


def test_cost_management_retry_budget_is_bounded(monkeypatch):
    import azure_http
    import pytest

    response = _response({})
    response.status_code = 503
    response.headers = {"Retry-After": "0"}
    response.raise_for_status = Mock(side_effect=RuntimeError("service unavailable"))
    post = Mock(return_value=response)
    monkeypatch.setattr(azure_http.time, "sleep", lambda delay: None)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    with pytest.raises(RuntimeError, match="unavailable"):
        cr._query_cost_management({}, "a", "start", "end")
    assert post.call_count == 3


def test_cost_management_does_not_retry_authorization_failures(monkeypatch):
    import pytest

    response = _response({})
    response.status_code = 403
    response.raise_for_status = Mock(side_effect=RuntimeError("access denied"))
    post = Mock(return_value=response)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    with pytest.raises(RuntimeError, match="denied"):
        cr._query_cost_management({}, "a", "start", "end")
    post.assert_called_once()
    response.close.assert_not_called()


def test_bootstrap_discovers_flat_root_tools_layout_without_pythonpath(monkeypatch):
    root = cr.Path(__file__).resolve().parent / "synthetic-bundle"
    tool = root / "tools" / "azure_http.py"
    monkeypatch.setattr(cr, "__file__", str(root / "collector.py"))
    monkeypatch.setattr(cr.Path, "is_file", lambda path: path == tool)
    monkeypatch.setattr(sys, "path", [])
    cr._bootstrap_shared_tools()
    assert sys.path == [str(root / "tools")]


def test_consumption_page_cap_is_explicit_incomplete(monkeypatch):
    import pytest

    monkeypatch.setattr(cr, "MAX_PAGES", 1)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *a, **kw: _response({"value": [], "nextLink": cr.ARM_ENDPOINT + "/next"})))
    with pytest.raises(RuntimeError, match="incomplete"):
        cr._query_consumption({}, "a", "start", "end")


def test_cost_management_cap_and_unknown_amount_fail_explicitly(monkeypatch):
    import pytest

    columns = [{"name": name} for name in ("Cost", "ResourceGroupName", "Currency")]
    monkeypatch.setattr(cr, "MAX_PAGES", 1)
    post = Mock(return_value=_response({"properties": {"columns": columns, "rows": [], "nextLink": cr.ARM_ENDPOINT + "/next"}}))
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    with pytest.raises(RuntimeError, match="incomplete"):
        cr._query_cost_management({}, "a", "start", "end")
    post.return_value = _response({"properties": {"columns": columns, "rows": [[None, "rg", "USD"]]}})
    with pytest.raises(ValueError, match="unknown"):
        cr._query_cost_management({}, "a", "start", "end")


def test_consumption_preserves_currencies_in_one_resource_group(monkeypatch):
    get = Mock(side_effect=[
        _response({"value": [{"properties": {"resourceGroup": "rg", "cost": 10, "currency": "USD"}}], "nextLink": cr.ARM_ENDPOINT + "/next"}),
        _response({"value": [{"properties": {"resourceGroup": "rg", "costInBillingCurrency": 20, "billingCurrencyCode": "EUR"}}]}),
    ])
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    rows, currency = cr._query_consumption({}, "a", "start", "end")
    assert rows == [("rg", 10, "USD"), ("rg", 20, "EUR")]
    assert currency is None


def test_currency_and_baseline_ranking_are_separate(monkeypatch):
    monkeypatch.setattr(cr, "_token", lambda: "test")
    monkeypatch.setattr(cr, "_query_cost_management", lambda headers, sub, start, end: ([("rg", 100, "USD"), ("rg", 200, "EUR")], None))
    result = cr.main(subscription_ids=["a"])
    assert result["subscriptions"][0]["total_cost"] is None
    assert result["subscriptions"][0]["totals_by_currency"] == {"USD": 100, "EUR": 200}
    assert set(result["ranking_groups"]) == {"EUR:AmortizedCost", "USD:AmortizedCost"}
    assert {row["currency"] for row in result["resource_groups"]["a"]} == {"USD", "EUR"}


def test_fallback_is_not_amortized_and_failure_is_not_zero(monkeypatch):
    monkeypatch.setattr(cr, "_token", lambda: "test")
    def denied(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(cr, "_query_cost_management", denied)
    monkeypatch.setattr(cr, "_query_consumption", lambda *args: ([("rg", 5, "USD")], "USD"))
    result = cr.main(subscription_ids=["a"])
    assert result["assessment_status"] == "Partial"
    assert result["subscriptions"][0]["cost_basis"] == "UsageDetailsActualCost"
    monkeypatch.setattr(cr, "_query_consumption", denied)
    result = cr.main(subscription_ids=["a"])
    assert result["assessment_status"] == "Not assessed"
    assert result["subscriptions"][0]["total_cost"] is None
    assert result["selected_subscriptions"] == []


if __name__ == "__main__":
    test_floor_applies_for_three_subscriptions()
    test_floor_for_six_subscriptions()
    test_top_decile_for_two_hundred()
    test_resource_group_floor()
    test_ranks_are_one_based_and_ordered()
    test_empty_set()
    print("All cost_rank selection tests passed.")
