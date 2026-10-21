"""Unit tests for the pure helpers in identity_access (no Azure calls)."""

import identity_access as ia

OWNER = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
CONTRIB = "b24988ac-6180-42a0-ab88-20f7382dd24c"


def _assignment(role_id, ptype, scope):
    return {"properties": {"roleDefinitionId": f"/subscriptions/a/providers/Microsoft.Authorization/roleDefinitions/{role_id}", "principalId": "p1234567890abc", "principalType": ptype, "scope": scope}}


def test_role_name_from_id():
    assert ia.role_name_from_id(f"/.../{OWNER}") == "Owner"
    assert ia.role_name_from_id("/.../unknownguid") is None


def test_scope_kind():
    assert ia.scope_kind("/subscriptions/a", "a") == "subscription"
    assert ia.scope_kind("/providers/Microsoft.Management/managementGroups/mg1", "a") == "management group"
    assert ia.scope_kind("/subscriptions/a/resourceGroups/rg1", "a") == "resource group"


def test_service_principal_owner_is_high():
    finding = ia.classify_assignment(_assignment(OWNER, "ServicePrincipal", "/subscriptions/a"), "a")
    assert finding["severity"] == "High"
    assert finding["role"] == "Owner"


def test_user_owner_is_medium():
    finding = ia.classify_assignment(_assignment(OWNER, "User", "/subscriptions/a"), "a")
    assert finding["severity"] == "Medium"


def test_unknown_principal_is_medium():
    finding = ia.classify_assignment(_assignment(CONTRIB, "Unknown", "/subscriptions/a"), "a")
    assert finding["severity"] == "Medium"


def test_known_non_privileged_role_ignored_but_unresolved_reviewed():
    assignment = _assignment("some-reader-guid", "User", "/subscriptions/a")
    definitions = {assignment["properties"]["roleDefinitionId"].lower(): {"roleType": "BuiltInRole", "roleName": "Reader"}}
    assert ia.classify_assignment(assignment, "a", definitions) is None
    assert ia.classify_assignment(assignment, "a")["role"] == "Unresolved role definition"


def test_preserves_identifiers_and_unknown_is_not_removal():
    assignment = _assignment(OWNER, "Unknown", "/subscriptions/a/resourceGroups/FullScope")
    assignment["id"] = "/subscriptions/a/providers/Microsoft.Authorization/roleAssignments/full-id"
    finding = ia.classify_assignment(assignment, "a")
    assert finding["principal"] == "p1234567890abc"
    assert finding["scope"] == assignment["properties"]["scope"]
    assert finding["assignment_id"] == assignment["id"]
    assert "Confirm" in finding["recommendation"]
    assert "Remove this" not in finding["recommendation"]


def test_custom_roles_are_reviewed_without_name_based_privilege_assumption():
    assignment = _assignment("custom-guid", "ServicePrincipal", "/subscriptions/a")
    permissions = [{"actions": ["*"], "notActions": [], "dataActions": ["*"]}]
    definitions = {assignment["properties"]["roleDefinitionId"].lower(): {"roleType": "CustomRole", "roleName": "Friendly Reader", "permissions": permissions}}
    finding = ia.classify_assignment(assignment, "a", definitions)
    assert finding["role_permissions"] == permissions
    assert "NotDataActions" in finding["recommendation"]


def test_empty_scope_is_not_assessed_and_subscription_id_is_preserved():
    assert ia.build_report_data([], 0, {}, [])["assessment_status"] == "Not assessed"
    finding = ia.classify_assignment(_assignment(OWNER, "User", "/subscriptions/a"), "a")
    data = ia.build_report_data([finding], 1, {"a": "Display"}, ["Directory not assessed"])
    assert data["assessment_status"] == "Partial"
    assert data["findings"]["rows"][0]["subscription"] == "a"
    assert any("control plane" in note for note in data["method_notes"])


def test_assignment_read_failure_cannot_be_complete(monkeypatch):
    monkeypatch.setattr(ia, "_headers", lambda: {})
    monkeypatch.setattr(ia, "_list_subscription_names", lambda headers: {"a": "A"})
    def denied(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(ia, "_get_all", denied)
    assert ia.main()["assessment_status"] == "Not assessed"


def test_owner_sprawl():
    assert ia.owner_sprawl_finding("a", 5, threshold=3)["severity"] == "High"
    assert ia.owner_sprawl_finding("a", 2, threshold=3) is None


def test_build_report_data_counts_sp():
    findings = [ia.classify_assignment(_assignment(OWNER, "ServicePrincipal", "/subscriptions/a"), "a")]
    data = ia.build_report_data(findings, 1, {"a": "Sub A"}, [])
    assert data["summary_cards"][1]["value"] == "1"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all identity_access tests passed")
