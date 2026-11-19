import os
import tempfile
import unittest

from core.updater import _safe_update_destination


class SafeUpdateDestinationTests(unittest.TestCase):
    def test_valid_member_stays_inside_project(self):
        with tempfile.TemporaryDirectory() as project_dir:
            path = _safe_update_destination(
                project_dir,
                "Floating-Island-main/",
                "Floating-Island-main/core/main.py",
            )
            self.assertEqual(path, os.path.join(project_dir, "core", "main.py"))

    def test_rejects_traversal_and_windows_absolute_paths(self):
        with tempfile.TemporaryDirectory() as project_dir:
            bad_members = (
                "Floating-Island-main/../outside.txt",
                "Floating-Island-main/core/../../outside.txt",
                "Floating-Island-main/C:/outside.txt",
                "Floating-Island-main/core\\outside.py",
            )
            for member in bad_members:
                with self.subTest(member=member):
                    with self.assertRaises(ValueError):
                        _safe_update_destination(
                            project_dir,
                            "Floating-Island-main/",
                            member,
                        )

    def test_rejects_member_outside_archive_root(self):
        with tempfile.TemporaryDirectory() as project_dir:
            with self.assertRaises(ValueError):
                _safe_update_destination(
                    project_dir,
                    "Floating-Island-main/",
                    "Other-project/file.py",
                )


if __name__ == "__main__":
    unittest.main()
