"""Public release metadata. Secrets are never accepted in this file."""
import datetime
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

MIN_SDK = 28
TARGET_SDK = 36
COMPILE_SDK = 36
DEFAULT = {
    "schemaVersion": 1,
    "versionCode": 2,
    "versionName": "0.1.0-rc1",
    "developerName": "",
    "supportEmail": "",
    "privacyUrl": "",
    "sourceUrl": "",
    "policyDate": "2026-11-01",
}
PUBLIC_FIELDS = {
    "developerName": "Z8_DEVELOPER_NAME",
    "supportEmail": "Z8_SUPPORT_EMAIL",
    "privacyUrl": "Z8_PRIVACY_URL",
    "sourceUrl": "Z8_SOURCE_URL",
    "policyDate": "Z8_POLICY_DATE",
}


def public_https_format(value):
    """Check public URL syntax only. Publication, reachability and ownership are separate gates."""
    if any(c.isspace() or ord(c) == 127 for c in value) or "\\" in value or re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port  # Reading port also rejects malformed/out-of-range values.
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or port == 0 or parsed.netloc.endswith(":")):
            return False
        # Scoped IPv6 addresses are interface-local, not public publication addresses.
        if "%" in host:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            return address.is_global and not address.is_multicast
        # Match Android's URI host boundary. Unicode domains must use their ASCII/Punycode form.
        labels = host.split(".")
        if (len(host) > 253 or len(labels) < 2 or labels[-1].isdigit()
                or any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", part) for part in labels)):
            return False
        if host in {"example.com", "example.org", "example.net"} or host.endswith(
                (".example.com", ".example.org", ".example.net", ".invalid", ".test", ".localhost", ".example", ".local", ".internal")):
            return False
        return True
    except ValueError:
        return False


def load(path=None, *, production=False):
    data = dict(DEFAULT) if path is None else json.loads(Path(path).read_text())
    if not isinstance(data, dict) or set(data) != set(DEFAULT):
        raise ValueError("Release config must contain only the documented public fields")
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise ValueError("Unsupported release config schema")
    if type(data["versionCode"]) is not int or not 1 <= data["versionCode"] <= 2100000000:
        raise ValueError("versionCode must be an integer from 1 to 2100000000")
    if not isinstance(data["versionName"], str) or not re.fullmatch(
            r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", data["versionName"]):
        raise ValueError("versionName must be a semantic version")
    for key in PUBLIC_FIELDS:
        value = data[key]
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid public release field: " + key)
        if value != value.strip():
            raise ValueError("Release fields must not have surrounding whitespace: " + key)
    if data["supportEmail"] and not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", data["supportEmail"]):
        raise ValueError("supportEmail must be an email address")
    for key in ("privacyUrl", "sourceUrl"):
        if not data[key]:
            continue
        if not public_https_format(data[key]):
            raise ValueError(key + " must have public HTTPS URL format without credentials or placeholder hosts; availability is checked separately")
    datetime.date.fromisoformat(data["policyDate"])
    if production:
        missing = missing_public_fields(data)
        if missing:
            raise ValueError("Release requires public operator information: " + ", ".join(missing))
    return data


def missing_public_fields(data):
    return [key for key in PUBLIC_FIELDS if not data.get(key)]


def gradle_public_fields(data):
    # A Gradle string containing a Java string literal; both layers must be escaped.
    # Single-quoted Groovy strings preserve dollar signs and ${...} as public text.
    def literal(value):
        java = json.dumps(value, ensure_ascii=False)
        return "'" + java.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return "\n".join('        buildConfigField "String", "' + name + '", '
                     + literal(data[key])
                     for key, name in PUBLIC_FIELDS.items())
