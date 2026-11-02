#!/usr/bin/env python3
"""Minimal, read-only G0 inventory. Collection never means compatibility PASS."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

DEFAULT_PACKAGE = "dev.devsigner.z8"
PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")
PROPERTIES = {
    "manufacturer": "ro.product.manufacturer", "model": "ro.product.model",
    "build_id": "ro.build.id", "build_incremental": "ro.build.version.incremental",
    "android_release": "ro.build.version.release", "api_level": "ro.build.version.sdk",
    "abis": "ro.product.cpu.abilist",
}


def remote_command(*args):
    """adb shell joins arguments remotely; quote each argument explicitly."""
    return shlex.join(args)


def positive_int(value):
    return int(value) if re.fullmatch(r"[0-9]+", value.strip()) and int(value) > 0 else None


def parse_devices(raw):
    devices = []
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in ("device", "offline", "unauthorized", "recovery", "sideload"):
            devices.append((fields[0], fields[1]))
    return devices


def parse_package(raw, current_user):
    """Whitelist fields; never retain permission lists, paths, or raw dumps."""
    result = {"notification_permission": "UNKNOWN", "installed_for_user": None}
    user = None
    for line in raw.splitlines():
        found = re.search(r"\bUser (\d+):.*\binstalled=(true|false)\b", line)
        if found:
            user = int(found[1])
            if user == current_user:
                result["installed_for_user"] = found[2] == "true"
        for field, pattern in (
            ("version_code", r"\bversionCode=(\d+)"),
            ("target_sdk", r"\btargetSdk=(\d+)"),
            ("min_sdk", r"\bminSdk=(\d+)"),
            ("app_id", r"\buserId=(\d+)"),
        ):
            match = re.search(pattern, line)
            if match:
                result[field] = int(match[1])
        for field in ("versionName", "primaryCpuAbi", "secondaryCpuAbi"):
            match = re.fullmatch(r"\s*" + field + r"=([^\r\n]{1,160})\s*", line)
            if match:
                result[field] = match[1].strip()
        match = re.search(r"android\.permission\.POST_NOTIFICATIONS: granted=(true|false)\b", line)
        if match and user == current_user:
            result["notification_permission"] = "GRANTED" if match[1] == "true" else "DENIED"
    return result


def parse_appops(raw):
    match = re.search(r"\bPOST_NOTIFICATION:\s*(allow|deny|ignore|default|foreground|errored)\b", raw)
    if match:
        return match[1].upper()
    return "NOT_RECORDED" if "No operations." in raw else "UNKNOWN"


class Probes:
    def __init__(self, adb=None, fixture=None, timeout=10):
        self.adb, self.fixture, self.timeout = adb, fixture, timeout
        self.serial = None
        self.errors = {}

    def call(self, key, args, remote=False, allow_empty=False):
        if self.fixture is not None:
            item = self.fixture.get(key)
            if item is None:
                self.errors[key] = "FIXTURE_MISSING"
                return None
            if not isinstance(item, dict):
                raise ValueError("Fixture probes must be objects")
            code, output = item.get("returncode", 0), item.get("stdout", "")
            if not isinstance(output, str):
                raise ValueError("Fixture stdout must be text")
        else:
            argv = [self.adb]
            if self.serial:
                argv += ["-s", self.serial]
            argv += ["shell", args] if remote else args
            try:
                completed = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, check=False)
                code, output = completed.returncode, completed.stdout
            except subprocess.TimeoutExpired:
                self.errors[key] = "TIMEOUT"
                return None
            except OSError:
                self.errors[key] = "EXECUTION_UNAVAILABLE"
                return None
        if code != 0:
            self.errors[key] = "COMMAND_FAILED"
            return None
        output = output.strip()
        if not output and not allow_empty:
            self.errors[key] = "EMPTY_RESULT"
            return None
        return output

    def shell(self, key, *args, allow_empty=False):
        return self.call(key, remote_command(*args), remote=True, allow_empty=allow_empty)


def collect(probes, package, requested_serial=None):
    if not PACKAGE_RE.fullmatch(package):
        raise ValueError("Invalid Android package name")
    report = {
        "schema_version": 1,
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "FIXTURE" if probes.fixture is not None else "ADB",
        "status": "NOT_TESTED", "gate_status": "NOT_TESTED", "package_name": package,
        "limitations": ["Inventory only; no CLI execution or background survival was tested.",
                        "Process presence does not prove a usable or persistent terminal session.",
                        "ADB shell observations may exceed permissions available to the app."],
    }
    if probes.fixture is None and not probes.adb:
        report["reason"] = "ADB_UNAVAILABLE"
        return report
    raw_devices = probes.call("devices", ["devices"])
    if raw_devices is None:
        report.update(reason="ADB_UNAVAILABLE", probe_errors=probes.errors)
        return report
    devices = parse_devices(raw_devices)
    if requested_serial:
        candidates = [d for d in devices if d[0] == requested_serial]
    else:
        candidates = devices
    if len(candidates) != 1:
        report["reason"] = "NO_DEVICE" if not candidates else "DEVICE_SELECTION_REQUIRED"
        return report
    if candidates[0][1] != "device":
        report["reason"] = "DEVICE_" + candidates[0][1].upper()
        return report
    probes.serial = candidates[0][0]  # Deliberately not written to the report.
    device = {}
    for name, prop in PROPERTIES.items():
        value = probes.shell(name, "getprop", prop)
        device[name] = value[:160] if value else None
    device["api_level"] = positive_int(device["api_level"] or "")
    device["abis"] = device["abis"].split(",") if device["abis"] else []
    memory = probes.shell("mem_total", "awk", "/^MemTotal:/ {print $2}", "/proc/meminfo")
    memory_kib = positive_int(memory or "")
    device["total_ram_bytes"] = memory_kib * 1024 if memory_kib else None
    page_size = probes.shell("page_size", "getconf", "PAGESIZE")
    device["page_size_bytes"] = positive_int(page_size or "")
    if device["page_size_bytes"] is None:
        device["page_size_bytes"] = positive_int(probes.shell("page_size_fallback", "getconf", "PAGE_SIZE") or "")
    user_raw = probes.shell("current_user", "am", "get-current-user")
    current_user = int(user_raw) if user_raw and re.fullmatch(r"\d+", user_raw) else None
    device["android_user_id"] = current_user
    # Filter on the device: full dumpsys output is never transferred or persisted.
    filters = [r"/^[[:space:]]*versionCode=/p", r"/^[[:space:]]*versionName=/p",
               r"/^[[:space:]]*userId=/p", r"/^[[:space:]]*primaryCpuAbi=/p",
               r"/^[[:space:]]*secondaryCpuAbi=/p", r"/^[[:space:]]*User [0-9].*installed=/p",
               r"/^[[:space:]]*android\.permission\.POST_NOTIFICATIONS: granted=/p"]
    sed_args = ["sed", "-n"]
    for expression in filters:
        sed_args += ["-e", expression]
    metadata_command = remote_command("dumpsys", "package", package) + " | " + remote_command(*sed_args)
    metadata = probes.call("package_metadata", metadata_command, remote=True, allow_empty=True)
    app = parse_package(metadata or "", current_user)
    app["installation_status"] = "UNKNOWN"
    if current_user is not None:
        packages = probes.shell("package_list", "pm", "list", "packages", "--user", str(current_user), package, allow_empty=True)
        if packages is not None:
            app["installation_status"] = "INSTALLED" if "package:" + package in packages.splitlines() else "NOT_INSTALLED"
        appops = probes.shell("notification_appop", "cmd", "appops", "get", "--user", str(current_user), package, "POST_NOTIFICATION", allow_empty=True)
        app["notification_appop"] = parse_appops(appops or "")
    else:
        app["notification_appop"] = "UNKNOWN"
    if device["api_level"] is not None and device["api_level"] < 33:
        app["notification_permission"] = "NOT_APPLICABLE_BEFORE_API_33"
    processes = {"main_app_pids": [], "main_app_observed": None,
                 "tmux_process_observed": None, "session_status": "UNKNOWN"}
    app_id = app.get("app_id")
    if app_id is not None and current_user is not None and app["installation_status"] == "INSTALLED":
        # UID is numeric and computed from Android's per-user UID namespace.
        uid = current_user * 100000 + app_id % 100000
        # Preserve ps failure; filter before transfer, including Android user UID.
        ps_prefix = "rows=$(" + remote_command("ps", "-A", "-o", "UID,PID,NAME") + ") || exit 1; printf '%s\\n' \"$rows\" | "
        own_pids_command = ps_prefix + remote_command("awk", '$1 == "' + str(uid) + '" && $3 == "' + package + '" {print $2}')
        pid_output = probes.call("app_pids", own_pids_command, remote=True, allow_empty=True)
        processes["main_app_pids"] = [int(p) for p in (pid_output or "").split() if p.isdigit()]
        processes["main_app_observed"] = bool(processes["main_app_pids"]) if pid_output is not None else None
        tmux_command = ps_prefix + remote_command("awk", '$1 == "' + str(uid) + '" && ($3 == "tmux" || $3 ~ /[/]tmux$/) {print $2}')
        tmux_raw = probes.call("tmux_pids", tmux_command, remote=True, allow_empty=True)
        processes["tmux_process_observed"] = bool(tmux_raw) if tmux_raw is not None else None
    report.update(device=device, application=app, processes=processes, probe_errors=probes.errors)
    required = (device["manufacturer"], device["model"], device["build_id"], device["api_level"],
                device["abis"], device["total_ram_bytes"], device["page_size_bytes"], current_user is not None)
    report["status"] = "DIAGNOSTICS_COLLECTED" if all(required) and app["installation_status"] != "UNKNOWN" else "PARTIAL"
    if probes.fixture is not None:
        report["status"] = "FIXTURE_ONLY"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, help="Write JSON here; otherwise stdout")
    parser.add_argument("--fixture", type=Path, help="Parse JSON probe responses without contacting adb")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    local_adb = root / ".local" / "android-sdk" / "platform-tools" / "adb"
    adb = os.environ.get("Z8_ADB") or (str(local_adb) if local_adb.is_file() else shutil.which("adb"))
    try:
        fixture = json.loads(args.fixture.read_text()) if args.fixture else None
        if fixture is not None and not isinstance(fixture, dict):
            raise ValueError("Fixture must be a JSON object")
        report = collect(Probes(adb=adb, fixture=fixture), args.package, os.environ.get("Z8_DEVICE_SERIAL"))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 2 if report["status"] == "NOT_TESTED" else 0


if __name__ == "__main__":
    sys.exit(main())
