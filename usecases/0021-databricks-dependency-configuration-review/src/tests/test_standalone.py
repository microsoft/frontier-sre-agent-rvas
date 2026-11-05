import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from support import REFERENCE, ROOT, STANDALONE, fixture, load_engine
from test_engine import cwd


class StandaloneTests(unittest.TestCase):
    def test_committed_standalone_is_current_build(self):
        spec = importlib.util.spec_from_file_location("builder", ROOT / "build_tool.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        self.assertEqual(STANDALONE.read_text(encoding="utf-8"), builder.build())

    def test_wholefile_paste_loads_without_network_or_stdout_even_as_main(self):
        source = STANDALONE.read_text(encoding="utf-8")
        self.assertLess(max(len(line) for line in source.splitlines()), 10000)
        stdout = io.StringIO()
        namespace = {"__name__": "__main__"}
        with redirect_stdout(stdout):
            exec(compile(source, "SRE-wholefile-paste", "exec"), namespace)
        self.assertEqual(stdout.getvalue(), "")
        result = namespace["main"]()
        self.assertEqual(result["error"]["code"], "configuration_required")
        self.assertEqual(result["artifact_status"], "not_written")

    def test_copied_file_has_all_assets_and_writes_complete_real_files(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "whole-file.py"
            shutil.copyfile(STANDALONE, copied)
            spec = importlib.util.spec_from_file_location("isolated_canonical_tool", copied)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(len(module.CATALOG["rules"]), 36)
            self.assertEqual(module.HTML_TEMPLATE.count("__REPORT_DATA_JSON__"), 1)
            configured = load_engine(standalone=True)
            module.SUBSCRIPTION_ID = configured.SUBSCRIPTION_ID
            module.SRE_TENANT_ID = configured.SRE_TENANT_ID
            module.TARGET_TENANT_ID = configured.TARGET_TENANT_ID
            module.MANAGED_IDENTITY_CLIENT_ID = configured.MANAGED_IDENTITY_CLIENT_ID
            module.FEDERATED_APP_CLIENT_ID = configured.FEDERATED_APP_CLIENT_ID
            module.APPROVED_WORKSPACES = configured.APPROVED_WORKSPACES
            raw = fixture(module)
            snapshot = module.finish_snapshot(raw, REFERENCE, "SIMULATED", "LAB")
            with cwd(directory):
                result = module.write_report(snapshot)
            self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)
            actual = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
            self.assertEqual(actual, snapshot)
            html = Path(result["report_path"]).read_text(encoding="utf-8")
            embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
            self.assertEqual(json.loads(embedded), snapshot)
            self.assertEqual(len(list((Path(directory) / "databricks-dependency-reports").iterdir())), 4)

    def test_canonical_main_reports_once_and_queries_without_fixture_imports(self):
        module = load_engine(standalone=True)
        raw = fixture(module)
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(module, "collect_live", return_value=raw) as collect:
            result = module.main()
            self.assertEqual(result["artifact_status"], "written")
            collect.assert_called_once()
        with patch.object(module, "collect_live", return_value=fixture(module)) as collect:
            result = module.main(operation="query", view="dependencies", classification="OBSERVED", limit=2)
            self.assertEqual(result["returned"], 2)
            collect.assert_called_once()
        self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)


if __name__ == "__main__":
    unittest.main()
