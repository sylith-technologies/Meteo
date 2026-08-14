# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode


SAFE_ENVIRONMENT_KEYS = ("XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "LANG")


def _os_release() -> str:
    try:
        values = {}
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        return values.get("PRETTY_NAME", platform.platform())
    except OSError:
        return platform.platform()


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()[:120]
    except OSError:
        pass
    return platform.processor()[:120]


def _memory_gib() -> str:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kib = int(line.split()[1])
                return f"{kib / 1024 / 1024:.1f} GiB"
    except (OSError, ValueError, IndexError):
        pass
    return "Unknown"


def collect_diagnostics(app_version: str, include_hardware: bool = False) -> Dict[str, str]:
    report = {
        "Meteo version": app_version,
        "Date (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Operating system": _os_release(),
        "Architecture": platform.machine(),
        "Python": platform.python_version(),
    }
    for key in SAFE_ENVIRONMENT_KEYS:
        if os.environ.get(key):
            report[key] = os.environ[key][:120]
    if include_hardware:
        report["CPU"] = _cpu_model()
        report["Memory"] = _memory_gib()
    return report


def build_issue_body(description: str, diagnostics: Dict[str, str]) -> str:
    description = description.strip()[:4000]
    lines = [
        "## What happened",
        description or "(Please describe the problem.)",
        "",
        "## Diagnostics approved by the user",
    ]
    lines.extend(f"- **{key}:** {value}" for key, value in diagnostics.items())
    lines.extend(
        [
            "",
            "Meteo did not automatically collect an IP address, precise location, username, hostname, serial number or MAC address.",
        ]
    )
    return "\n".join(lines)


def github_issue_url(repository_url: str, description: str, diagnostics: Dict[str, str]) -> str:
    return f"{repository_url.rstrip('/')}/issues/new?{urlencode({'title': '[Bug] ', 'body': build_issue_body(description, diagnostics)})}"
