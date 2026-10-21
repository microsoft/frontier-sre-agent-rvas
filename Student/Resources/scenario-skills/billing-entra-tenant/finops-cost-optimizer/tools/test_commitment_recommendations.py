"""Commitment opportunities are alternatives, not an additive savings total."""

import sys
from types import SimpleNamespace

import pytest
import commitment_recommendations as cm


def test_opportunities_are_not_summed_across_kinds_or_currencies(monkeypatch):
    monkeypatch.setattr(cm, "_token", lambda: "test")
    monkeypatch.setattr(cm, "_reservation_recommendations", lambda *args: [{"net_savings": 100, "currency": "USD"}])
    monkeypatch.setattr(cm, "_savings_plan_recommendations", lambda *args: [{"net_savings": 90, "currency": "EUR"}])
    result = cm.main(["a"])
    assert result["estimated_total_net_savings"] is None
    assert result["by_subscription"]["a"]["reservations"][0]["net_savings"] == 100
    assert "overlapping" in result["aggregation_policy"]


def test_pagination_cap_is_not_complete(monkeypatch):
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"value": [], "nextLink": cm.ARM_ENDPOINT + "/next"}, status_code=200, headers={}, close=lambda: None)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *args, **kw: response))
    with pytest.raises(RuntimeError, match="incomplete"):
        cm._get_all({}, cm.ARM_ENDPOINT + "/first")


def test_unreadable_sources_are_not_assessed(monkeypatch):
    monkeypatch.setattr(cm, "_token", lambda: "test")
    def denied(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(cm, "_reservation_recommendations", denied)
    monkeypatch.setattr(cm, "_savings_plan_recommendations", denied)
    assert cm.main(["a"])["assessment_status"] == "Not assessed"
