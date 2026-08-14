# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private, atomic storage helpers for user-controlled application data."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    """Creates an application directory and restricts it to the current user."""

    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        # Some sandboxed or unusual filesystems do not expose POSIX modes.
        pass


def atomic_write_text(path: Path, value: str, encoding: str = "utf-8") -> None:
    """Writes text without following a predictable temporary-file symlink."""

    ensure_private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding=encoding) as stream:
            descriptor = -1
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
