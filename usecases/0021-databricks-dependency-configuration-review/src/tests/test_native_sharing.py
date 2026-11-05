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


def native_paths(root, stem="dbx-20261016T120000Z-123456abcdef"):
    return {
        key: root / "databricks-dependency-reports" / (stem + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("findings_csv_path", "-findings.csv"),
            ("dependencies_csv_path", "-dependencies.csv"),
        )
    }


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
                    self.assertEqual(url, "/api/files/tmp/ThreadFiles/" + THREAD + "/databricks-dependency-reports/" + path.name)
                    self.assertEqual(result[key], str(path))
                    self.assertFalse(url.startswith(("http:", "https:", "sandbox:")))
                self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)

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
            PureWindowsPath(r"C:\Users\test\dbx-reports"),
            PurePosixPath("/tmp/ThreadFiles") / THREAD,
            PurePosixPath("/usr/terminalRoot/tmp/ThreadFiles") / "not-a-thread",
            PurePosixPath(SRE_ROOTS[0]) / THREAD / "extra",
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
            root / "other-directory" / "dbx-20261016T120000Z-123456abcdef.html",
            PurePosixPath(SRE_ROOTS[0]) / NEXT_THREAD / "databricks-dependency-reports" / "dbx-20261016T120000Z-123456abcdef.html",
            root / "databricks-dependency-reports" / "report?token=secret.html",
            root / "databricks-dependency-reports" / "dbx-20261016T120000Z-000000000000.html",
        ):
            paths = native_paths(root)
            paths["report_path"] = path
            with self.subTest(path=path), self.assertRaises(self.e.EvidenceError) as raised:
                self.e.sharing_fields(root, paths)
            self.assertEqual(raised.exception.code, "unsafe_sharing_path")

    def test_symlink_or_junction_root_output_and_artifact_are_rejected(self):
        for target in ("root", "directory", "file"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory, cwd(directory):
                nominal = Path.cwd()
                root = nominal.resolve()

                def is_link(path):
                    return (
                        path in (nominal, root)
                        if target == "root"
                        else path == root / "databricks-dependency-reports"
                        if target == "directory"
                        else path.suffix == ".html"
                    )

                with patch.object(Path, "is_symlink", autospec=True, side_effect=is_link):
                    with self.assertRaises(self.e.EvidenceError) as raised:
                        self.e.write_report(self.snapshot)
                self.assertEqual(
                    raised.exception.code,
                    {"root": "unsafe_artifact_root", "directory": "unsafe_artifact_directory", "file": "artifact_collision"}[target],
                )


if __name__ == "__main__":
    unittest.main()
