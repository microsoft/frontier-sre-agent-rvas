import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

from support import REFERENCE, fixture, load_engine
from test_engine import cwd


THREAD = "55555555-5555-4555-8555-555555555555"
NEXT_THREAD = "66666666-6666-4666-8666-666666666666"
SRE_ROOTS = ("/root/sreagent/terminalRoot/tmp/ThreadFiles", "/usr/terminalRoot/tmp/ThreadFiles")


def native_paths(root, stem="aks-20261010T120000Z-123456abcdef"):
    return {key: root / "aks-waf-reports" / (stem + suffix) for key, suffix in (
        ("report_path", ".html"), ("snapshot_path", "-snapshot.json"),
        ("findings_csv_path", "-findings.csv"), ("inventory_csv_path", "-inventory.csv"))}


class NativeSharingTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.snapshot = self.e.finish_snapshot(fixture(self.e), REFERENCE, "SIMULATED", "LAB")

    def test_both_verified_runtime_roots_return_four_relative_native_links(self):
        for prefix in SRE_ROOTS:
            root = PurePosixPath(prefix) / THREAD
            paths = native_paths(root)
            result = self.e.report_envelope(self.snapshot, paths, root)
            with self.subTest(prefix=prefix):
                self.assertEqual(result["sharing_mode"], "native_ui")
                self.assertFalse(result["http_verified"])
                self.assertEqual(len([key for key in result if key.endswith("_url")]), 4)
                for key, path in paths.items():
                    url = result[key.removesuffix("_path") + "_url"]
                    self.assertEqual(url, "/api/files/tmp/ThreadFiles/" + THREAD + "/aks-waf-reports/" + path.name)
                    self.assertEqual(result[key], str(path))
                    self.assertFalse(url.startswith(("http:", "https:", "sandbox:")))

    def test_fresh_thread_uuid_is_derived_each_call_without_cached_prefix(self):
        for prefix in SRE_ROOTS:
            first = PurePosixPath(prefix) / THREAD
            second = PurePosixPath(prefix) / NEXT_THREAD
            old = self.e.sharing_fields(first, native_paths(first))
            new = self.e.sharing_fields(second, native_paths(second))
            with self.subTest(prefix=prefix):
                self.assertNotEqual(old["report_url"], new["report_url"])
                self.assertNotIn(THREAD, json.dumps(new))
                self.assertIn(NEXT_THREAD, new["report_url"])

    def test_unsupported_roots_never_invent_aliases_or_change_actual_paths(self):
        for root in (
            PureWindowsPath(r"C:\Users\test\aks-reports"),
            PurePosixPath("/tmp/ThreadFiles") / THREAD,
            PurePosixPath("/usr/terminalRoot/tmp/ThreadFiles") / "not-a-thread",
            PurePosixPath(SRE_ROOTS[0]) / THREAD / "extra",
            PurePosixPath("/root/another/terminalRoot/tmp/ThreadFiles") / THREAD,
            PurePosixPath("/usr/terminalRoot/tmp/ThreadFiles") / ("g" * 36),
            PurePosixPath("/usr/terminalRoot/tmp/ThreadFiles") / ("1" * 36),
        ):
            paths = native_paths(root)
            with self.subTest(root=root):
                fields = self.e.sharing_fields(root, paths)
                self.assertEqual(fields, {"sharing_mode": "local_files_only", "http_verified": False})
                result = self.e.report_envelope(self.snapshot, paths, root)
                self.assertFalse(any(key.endswith("_url") for key in result))
                self.assertTrue(all(result[key] == str(path) for key, path in paths.items()))

    def test_native_links_cannot_escape_directory_thread_filename_or_run(self):
        root = PurePosixPath(SRE_ROOTS[0]) / THREAD
        for path in (
            root / "other-directory" / "aks-20261010T120000Z-123456abcdef.html",
            PurePosixPath(SRE_ROOTS[0]) / NEXT_THREAD / "aks-waf-reports" / "aks-20261010T120000Z-123456abcdef.html",
            root / "aks-waf-reports" / "report?token=secret.html",
            root / "aks-waf-reports" / "malicious%2Fescape.html",
            root / "aks-waf-reports" / "aks-20261010T120000Z-000000000000.html",
        ):
            paths = native_paths(root)
            paths["report_path"] = path
            with self.subTest(path=path), self.assertRaises(self.e.EvidenceError) as raised:
                self.e.sharing_fields(root, paths)
            self.assertEqual(raised.exception.code, "unsafe_sharing_path")
        with self.assertRaises(self.e.EvidenceError):
            self.e.sharing_fields(root, {"report_path": native_paths(root)["report_path"]})

    def test_same_run_suffixes_and_simulated_filenames_are_validated(self):
        root = PurePosixPath(SRE_ROOTS[1]) / THREAD
        paths = native_paths(root, "simulated-20261010T120000Z-123456abcdef")
        self.assertEqual(self.e.sharing_fields(root, paths)["sharing_mode"], "native_ui")
        paths["snapshot_path"] = paths["findings_csv_path"]
        with self.assertRaises(self.e.EvidenceError):
            self.e.sharing_fields(root, paths)

    def test_all_actual_paths_and_dynamic_links_fit_default_3500_byte_response(self):
        self.snapshot["inventory"]["workloads"] *= 100
        self.snapshot["sources"].extend(
            self.e.source_receipt("unavailable-" + str(i), REFERENCE, "error") for i in range(19)
        )
        for prefix in SRE_ROOTS:
            root = PurePosixPath(prefix) / THREAD
            paths = native_paths(root)
            result = self.e.report_envelope(self.snapshot, paths, root)
            with self.subTest(prefix=prefix):
                self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["inventory_counts"]["workloads"], 100)
                self.assertEqual(result["collection"]["source_status_counts"]["error"], 19)
                self.assertEqual(len([key for key in result if key.endswith("_path")]), 4)
                self.assertEqual(len([key for key in result if key.endswith("_url")]), 4)

    def test_symlink_cwd_ancestor_is_rejected_before_link_derivation(self):
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            ancestor = Path.cwd().parent
            with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path == ancestor):
                with self.assertRaises(self.e.EvidenceError) as raised:
                    self.e.artifact_directory()
            self.assertEqual(raised.exception.code, "unsafe_artifact_root")

    def test_symlink_or_junction_root_output_and_artifact_are_rejected(self):
        for target in ("root", "directory", "file"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory, cwd(directory):
                nominal = Path.cwd()
                root = nominal.resolve()
                def is_link(path):
                    return path in (nominal, root) if target == "root" else path == root / "aks-waf-reports" if target == "directory" else path.suffix == ".html"
                with patch.object(Path, "is_symlink", autospec=True, side_effect=is_link):
                    with self.assertRaises(self.e.EvidenceError) as raised:
                        self.e.write_report(self.snapshot)
                self.assertEqual(raised.exception.code, {"root": "unsafe_artifact_root", "directory": "unsafe_artifact_directory",
                                                         "file": "artifact_collision"}[target])
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(Path, "is_junction", return_value=True):
            with self.assertRaises(self.e.EvidenceError):
                self.e.artifact_directory()

    def test_writer_passes_current_guarded_root_and_keeps_local_fallback(self):
        original = self.e.report_envelope
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(self.e, "report_envelope", wraps=original) as envelope:
            result = self.e.write_report(self.snapshot)
            self.assertEqual(envelope.call_args.args[2], Path.cwd().resolve())
            self.assertEqual(result["sharing_mode"], "local_files_only")
            self.assertFalse(any(key.endswith("_url") for key in result))
            for key in ("report_path", "snapshot_path", "findings_csv_path", "inventory_csv_path"):
                self.assertTrue(Path(result[key]).is_file())
            self.assertEqual(json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8")), self.snapshot)


if __name__ == "__main__":
    unittest.main()
