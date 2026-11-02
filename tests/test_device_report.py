"""Synthetic fixtures validate parsing, privacy, and absence handling; not G0."""
import importlib.util
import json
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("device_report", Path(__file__).resolve().parents[1] / "tools/collect-device-report.py")
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def fixture(**overrides):
    values = {
        "devices": "List of devices attached\nprivate-serial\tdevice\n",
        "manufacturer": "Example", "model": "Synthetic foldable", "build_id": "TEST.1",
        "build_incremental": "123", "android_release": "17", "api_level": "37",
        "abis": "arm64-v8a", "mem_total": "12000000", "page_size": "16384", "current_user": "10",
        "package_metadata": "userId=10234\nversionCode=7 minSdk=28 targetSdk=28\nversionName=0.1\n"
                            "User 0: installed=true\nandroid.permission.POST_NOTIFICATIONS: granted=false\n"
                            "User 10: installed=true\nandroid.permission.POST_NOTIFICATIONS: granted=true\n"
                            "secret=DO_NOT_RETAIN\n",
        "package_list": "package:dev.devsigner.z8", "notification_appop": "POST_NOTIFICATION: allow; time=+2s ago",
        "app_pids": "321 654", "tmux_pids": "789",
    }
    values.update(overrides)
    return {key: value if isinstance(value, dict) else {"stdout": value} for key, value in values.items()}


class DeviceReportTests(unittest.TestCase):
    def test_fixture_is_never_hardware_pass_and_does_not_invoke_adb(self):
        with patch.object(reporter.subprocess, "run", side_effect=AssertionError("No device access")):
            report = reporter.collect(reporter.Probes(fixture=fixture()), reporter.DEFAULT_PACKAGE)
        self.assertEqual(report["status"], "FIXTURE_ONLY")
        self.assertEqual(report["gate_status"], "NOT_TESTED")
        self.assertEqual(report["device"]["total_ram_bytes"], 12000000 * 1024)
        self.assertEqual(report["device"]["page_size_bytes"], 16384)
        self.assertEqual(report["application"]["notification_permission"], "GRANTED")
        self.assertEqual(report["application"]["target_sdk"], 28)
        self.assertNotIn("DO_NOT_RETAIN", json.dumps(report))
        self.assertNotIn("private-serial", json.dumps(report))

    def test_missing_adb(self):
        report = reporter.collect(reporter.Probes(), reporter.DEFAULT_PACKAGE)
        self.assertEqual((report["status"], report["reason"]), ("NOT_TESTED", "ADB_UNAVAILABLE"))

    def test_no_device_and_unauthorized_and_multiple_devices(self):
        for raw, expected in [("List of devices attached\n", "NO_DEVICE"),
                              ("one\tunauthorized", "DEVICE_UNAUTHORIZED"),
                              ("one\tdevice\ntwo\tdevice", "DEVICE_SELECTION_REQUIRED")]:
            report = reporter.collect(reporter.Probes(fixture=fixture(devices=raw)), reporter.DEFAULT_PACKAGE)
            self.assertEqual(report["status"], "NOT_TESTED")
            self.assertEqual(report["reason"], expected)

    def test_explicit_serial_selection_and_unknown_serial(self):
        probes = reporter.Probes(fixture=fixture(devices="one\tdevice\ntwo\tdevice"))
        self.assertEqual(reporter.collect(probes, reporter.DEFAULT_PACKAGE, "two")["status"], "FIXTURE_ONLY")
        self.assertEqual(probes.serial, "two")
        self.assertEqual(reporter.collect(probes, reporter.DEFAULT_PACKAGE, "missing")["reason"], "NO_DEVICE")

    def test_missing_package_is_explicit(self):
        report = reporter.collect(reporter.Probes(fixture=fixture(package_list="", package_metadata="")), reporter.DEFAULT_PACKAGE)
        self.assertEqual(report["application"]["installation_status"], "NOT_INSTALLED")
        self.assertIsNone(report["processes"]["tmux_process_observed"])

    def test_unavailable_values_do_not_become_zero_or_denied(self):
        report = reporter.collect(reporter.Probes(fixture=fixture(mem_total="not readable", page_size="bad",
            page_size_fallback={"returncode": 1}, notification_appop="No operations.",
            app_pids={"returncode": 1}, tmux_pids={"returncode": 1})), reporter.DEFAULT_PACKAGE)
        self.assertIsNone(report["device"]["total_ram_bytes"])
        self.assertIsNone(report["device"]["page_size_bytes"])
        self.assertEqual(report["application"]["notification_appop"], "NOT_RECORDED")
        self.assertIsNone(report["processes"]["main_app_observed"])
        self.assertIsNone(report["processes"]["tmux_process_observed"])

    def test_package_filter_does_not_accept_substring(self):
        report = reporter.collect(reporter.Probes(fixture=fixture(package_list="package:dev.devsigner.z8.example")), reporter.DEFAULT_PACKAGE)
        self.assertEqual(report["application"]["installation_status"], "NOT_INSTALLED")

    def test_user_permission_is_not_borrowed_from_owner(self):
        parsed = reporter.parse_package("User 0: installed=true\nandroid.permission.POST_NOTIFICATIONS: granted=true", 10)
        self.assertEqual(parsed["notification_permission"], "UNKNOWN")

    def test_package_injection_is_rejected(self):
        for package in ("dev.z8;id", "dev.z8$(id)", "-dev.z8", "dev.z8\n"):
            with self.assertRaises(ValueError):
                reporter.collect(reporter.Probes(), package)

    def test_remote_argument_quoting(self):
        args = ("awk", '/^MemTotal:/ {print $2}', "/proc/meminfo")
        self.assertEqual(shlex.split(reporter.remote_command(*args)), list(args))


if __name__ == "__main__":
    unittest.main()
