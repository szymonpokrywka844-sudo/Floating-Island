import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QSettings

from core.secret_store import load_github_token, save_github_token


class GitHubTokenStoreTests(unittest.TestCase):
    def test_blank_token_clears_saved_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = QSettings(
                str(Path(temp_dir) / "settings.ini"), QSettings.Format.IniFormat
            )
            settings.setValue("github_update_token_dpapi", "stale")
            save_github_token("", settings)
            self.assertEqual(load_github_token(settings), "")

    @unittest.skipUnless(hasattr(__import__("ctypes"), "windll"), "Windows DPAPI only")
    def test_token_round_trip_is_encrypted_in_settings(self):
        token = "github_pat_test_read_only_token"
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = QSettings(
                str(Path(temp_dir) / "settings.ini"), QSettings.Format.IniFormat
            )
            save_github_token(token, settings)
            saved = settings.value("github_update_token_dpapi")
            self.assertNotIn(token, str(saved))
            self.assertEqual(load_github_token(settings), token)


if __name__ == "__main__":
    unittest.main()
