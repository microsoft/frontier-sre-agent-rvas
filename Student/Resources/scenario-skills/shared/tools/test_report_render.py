import pytest

import report_render


def test_default_export_redacts_and_escapes():
    document = report_render.render_html({
        "title": "Synthetic posture review",
        "assessment_status": "Partial",
        "findings": {"columns": ["resource", "detail"], "rows": [
            {"resource": "private-workload", "detail": "<script>unsafe()</script> password=do-not-export"}]},
    })
    assert "private-workload" not in document
    assert "do-not-export" not in document
    assert "<script>unsafe()" not in document
    assert "&lt;script&gt;unsafe()" in document
    assert "customer sharing review required" in document
    assert "Partial" in document
    assert ">Sources<" in document


def test_local_report_and_filename_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(report_render, "OUTPUT_DIR", str(tmp_path))
    result = report_render.main({"title": "Synthetic report"}, filename="example.html")
    assert (tmp_path / "example.html").is_file()
    assert result["bytes"] > 0
    with pytest.raises(ValueError):
        report_render.main({"title": "Synthetic report"}, filename="..\\escape.html")


def test_invalid_report_is_not_success_shaped():
    with pytest.raises(ValueError):
        report_render.main({})


def test_explicit_identifier_export_still_blocks_credentials():
    document = report_render.render_html({
        "title": "Example",
        "findings": {"columns": ["resource", "detail"],
                     "rows": [{"resource": "customer-vm", "detail": "Bearer abc.xyz.123"}]},
    }, include_identifiers=True)
    assert "customer-vm" in document
    assert "abc.xyz.123" not in document
