import sys
import types
import unittest
from unittest.mock import patch

from core.privacy_monitor import _active_apps_for_capability, _friendly_app_name


class FakeKey:
    def __init__(self, values=None, children=None):
        self.values = values or {}
        self.children = children or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def fake_query_value(key, name):
    if name not in key.values:
        raise OSError(name)
    return key.values[name], 0


class PrivacyMonitorTests(unittest.TestCase):
    def test_active_timestamp_is_reported_and_stopped_usage_is_ignored(self):
        root = FakeKey(children={
            "NonPackaged": FakeKey(children={
                r"C:#Program Files#Discord#Discord.exe": FakeKey({
                    "LastUsedTimeStart": 200,
                    "LastUsedTimeStop": 0,
                }),
                r"C:#Tools#Recorder.exe": FakeKey({
                    "LastUsedTimeStart": 100,
                    "LastUsedTimeStop": 200,
                }),
            }),
        })
        registry = types.SimpleNamespace(
            HKEY_CURRENT_USER="HKCU",
            KEY_READ=1,
            OpenKey=lambda parent, path, *_args: (
                root if parent == "HKCU" else parent.children[path]
            ),
            EnumKey=lambda key, index: list(key.children)[index],
            QueryInfoKey=lambda key: (len(key.children), 0, 0),
            QueryValueEx=fake_query_value,
        )

        with patch.dict(sys.modules, {"winreg": registry}):
            self.assertEqual(_active_apps_for_capability("microphone"), ["Discord"])

    def test_known_process_names_are_normalized(self):
        self.assertEqual(
            _friendly_app_name(r"C:#Program Files#Discord#Discord.exe"),
            "Discord",
        )


if __name__ == "__main__":
    unittest.main()
