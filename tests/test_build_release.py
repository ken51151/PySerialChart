from pathlib import Path
import importlib.util
import unittest

# Load by path: packaging/ is a tools directory, not the third-party packaging package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_build_tools", PROJECT_ROOT / "packaging" / "build_release.py")
build_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_tools)
read_version = build_tools.read_version


class BuildVersionTests(unittest.TestCase):
    def test_build_paths_resolve_to_project(self):
        self.assertEqual(build_tools.ROOT, PROJECT_ROOT)
        self.assertEqual(build_tools.PACKAGING_DIR, PROJECT_ROOT / "packaging")
        self.assertTrue((build_tools.ROOT / "requirements.txt").is_file())
        self.assertTrue((build_tools.PACKAGING_DIR / "SerialChart.spec").is_file())
        self.assertTrue((build_tools.PACKAGING_DIR / "release_entry.py").is_file())

    def test_reads_current_version_without_importing_application(self):
        source = (Path(__file__).resolve().parents[1] / "SerialChart.py").read_text(encoding="utf-8-sig")
        self.assertRegex(read_version(source), r"^\d+\.\d+$")

    def test_does_not_execute_application_code(self):
        self.assertEqual(read_version('raise RuntimeError("do not execute")\nVERSION_MAJOR = 2\nVERSION_MINOR = 7'), "2.7")

    def test_rejects_invalid_version_constants(self):
        for value in ("-1", "True", '"1"', "1.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_version(f"VERSION_MAJOR = {value}\nVERSION_MINOR = 0")

    def test_requires_both_constants(self):
        with self.assertRaises(KeyError):
            read_version("VERSION_MAJOR = 1")


if __name__ == "__main__":
    unittest.main()
