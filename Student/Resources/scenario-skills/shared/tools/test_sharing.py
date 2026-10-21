from copy import deepcopy

import pytest

from sharing import sanitized_copy


def test_identifiers_are_consistent_and_original_is_not_modified():
    original = {"findings": {"rows": [{"resource": "private-vm", "detail": "Investigate private-vm",
                                      "subscription": "11111111-2222-3333-4444-555555555555"}]}}
    before = deepcopy(original)
    result = sanitized_copy(original)
    row = result["findings"]["rows"][0]
    assert "private-vm" not in str(result)
    assert row["resource"] in row["detail"]
    assert original == before
    assert result["sharing_review"]["redactions"] >= 3


def test_credentials_redacted_even_when_identifiers_are_approved():
    result = sanitized_copy({"resource": "customer-vm", "password": "do-not-export",
                             "detail": "Bearer abc.xyz.123 AccountKey=do-not-export"},
                            include_identifiers=True)
    assert result["resource"] == "customer-vm"
    assert "do-not-export" not in str(result)
    assert "abc.xyz.123" not in str(result)
    assert result["sharing_review"]["identifiers_included"]
    camel_case = sanitized_copy({"clientSecret": "never-export", "apiKey": "never-export"})
    assert "never-export" not in str(camel_case)


def test_missing_policy_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        sanitized_copy({}, policy_path=tmp_path / "missing.json")


def test_arbitrary_text_is_escaped_by_renderer_not_treated_as_instructions():
    result = sanitized_copy({"title": "<script>alert('test')</script>"})
    assert result["title"] == "<script>alert('test')</script>"


def test_pascal_case_inventory_identifiers_are_redacted():
    result = sanitized_copy({"ResourceName": "private-sql", "ResourceGroupName": "private-group"})
    assert "private-sql" not in str(result)
    assert "private-group" not in str(result)


def test_public_documentation_assessment_ids_are_not_broken():
    url = "https://learn.microsoft.com/assessments/00000000-0000-0000-0000-000000000000"
    assert sanitized_copy({"sources": [{"url": url}]})["sources"][0]["url"] == url
