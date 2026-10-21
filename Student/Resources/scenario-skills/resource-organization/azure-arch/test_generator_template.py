"""Offline regressions for the planning template. Never call Azure."""

import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest
import json
import shutil
import uuid
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("azure_arch_generator", Path(__file__).with_name("generator-template.py"))
arch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(arch)


def test_premium_ssd_v2_is_never_used_for_os_disk():
    premium = {"unitPrice": 10, "unitOfMeasure": "1/Month"}
    v2 = {"unitPrice": 1, "unitOfMeasure": "1 GiB/Month"}
    price, model = arch.disk_monthly(128, premium, v2, disk_role="os")
    assert model == "Premium SSD Managed Disks"
    assert price == 10
    _, data_model = arch.disk_monthly(128, premium, v2, disk_role="data")
    assert data_model == "Premium SSD v2"


def test_retail_catalog_failure_is_not_silently_static_catalog():
    arch.vm_sku_cache.clear()
    with patch.object(arch, "paged_items", side_effect=RuntimeError("unavailable")):
        with pytest.raises(RuntimeError, match="no fallback"):
            arch.available_vm_catalog()


def test_empty_catalog_is_not_deployability_proof():
    arch.vm_sku_cache.clear()
    with patch.object(arch, "paged_items", return_value=[]):
        with pytest.raises(RuntimeError, match="not assessed"):
            arch.available_vm_catalog()


def test_no_candidate_never_selects_undersized_fallback():
    with patch.object(arch, "available_vm_catalog", return_value=[{"sku": "small", "family": "D", "cpu": 2, "ram_gb": 8}]):
        with pytest.raises(ValueError, match="manual sizing"):
            arch.choose_sku({"vm_family": "E", "CPU": 64, "RAM": 512})


def test_disk_role_is_validated():
    with pytest.raises(ValueError):
        arch.disk_monthly(128, {}, {}, disk_role="unknown")


def test_workbook_generation_keeps_os_and_data_models_separate():
    output = Path(__file__).parent / f"test-output-{uuid.uuid4().hex}"
    inventory = arch.pd.DataFrame([{
        "Application Name": "Synthetic database", "Server Type": "Database",
        "Operating System": "Windows", "CPU": 8, "RAM": 64,
    }])
    candidate = {"sku": "Standard_E8ds_v5", "family": "E", "cpu": 8, "ram_gb": 64, "version": 5}
    def price(*args, **kwargs):
        return {"unitPrice": 1, "unitOfMeasure": "1 Hour" if kwargs.get("require_unit_contains") == "hour" else "1/Month",
                "meterName": "Synthetic meter", "productName": "Synthetic product", "armSkuName": kwargs.get("arm_sku", "")}
    try:
        with patch.object(arch, "THREAD_DIR", output), patch.object(arch, "USE_V2_DATA_DISKS", True), patch.object(arch.pd, "read_excel", return_value=inventory), patch.object(arch, "choose_sku", new=lambda _: candidate), patch.object(arch, "best_price", side_effect=price):
            arch.main()
        workbook = arch.pd.read_excel(output / f"azure-{arch.REGION}-cost-estimate.xlsx", sheet_name="VMEstimate")
        assert workbook.iloc[0]["OS Disk Model"] == "Premium SSD Managed Disks"
        assert workbook.iloc[0]["Data Disk Model"] == "Premium SSD v2"
        metadata = json.loads((output / f"azure-{arch.REGION}-estimate-metadata.json").read_text(encoding="utf-8"))
        assert metadata["assessment_status"] == "Partial"
        assert metadata["serverCount"] == 1
        assert metadata["sources"]
    finally:
        if output.exists():
            shutil.rmtree(output)


def test_retail_catalog_uses_shared_retry_policy_not_nested_retries():
    busy = SimpleNamespace(status_code=503, headers={"Retry-After": "0"}, close=Mock())
    ready = SimpleNamespace(status_code=200, headers={}, close=Mock(), raise_for_status=Mock(),
                            json=lambda: {"Items": [{"armSkuName": "synthetic"}]})
    get = Mock(side_effect=[busy, ready])
    with patch.dict(sys.modules, {"requests": SimpleNamespace(get=get)}), patch.object(arch.requests.time, "sleep"):
        assert arch.paged_items("synthetic-filter") == [{"armSkuName": "synthetic"}]
    assert get.call_count == 2
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["timeout"] == 90


def test_default_tools_do_not_require_optional_drawio_connector():
    skill = Path(__file__).with_name("SKILL.md").read_text(encoding="utf-8")
    header = skill.split("---", 2)[1]
    tools = [line.strip()[2:] for line in header.split("tools:", 1)[1].splitlines() if line.strip().startswith("- ")]
    assert tools == ["RunAzCliReadCommands", "RunInTerminal", "SaveFileToBlob"]
    assert "actual registered tool names" in skill
    assert "actual import and render validation" in skill


def test_local_drawio_draft_structure_and_explicit_unvalidated_boundary():
    path = Path(__file__).parent / "references" / "landing-zone-draft.drawio"
    root = ET.parse(path).getroot()
    assert root.tag == "mxfile"
    cells = root.findall("./diagram/mxGraphModel/root/mxCell")
    ids = [cell.get("id") for cell in cells]
    assert ids[:2] == ["0", "1"]
    assert len(ids) == len(set(ids))
    vertices = {cell.get("id") for cell in cells if cell.get("vertex") == "1"}
    for cell in cells[1:]:
        assert cell.get("parent") in ids
        if cell.get("vertex") == "1":
            geometry = cell.find("mxGeometry")
            assert geometry is not None
            assert all(geometry.get(key) is not None for key in ("x", "y", "width", "height", "as"))
        elif cell.get("edge") == "1":
            assert cell.get("source") in vertices and cell.get("target") in vertices
            assert cell.find("mxGeometry").get("relative") == "1"
    xml = path.read_text(encoding="utf-8")
    assert "UNVALIDATED XML DRAFT" in xml
    assert "Import and render validation is required" in xml
    assert "shape=image" not in xml and "mxgraph.azure" not in xml
