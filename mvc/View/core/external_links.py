from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


_DESKTOP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.desktop")


def open_external_url(
    url: str,
    opener: Callable[[QUrl], bool] | None = None,
) -> tuple[bool, str]:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or not parsed.netloc:
        return False, "Only valid HTTPS links can be opened."
    try:
        opened = (opener or QDesktopServices.openUrl)(QUrl(url))
    except Exception as error:
        return False, f"The desktop link handler failed: {error}"
    if not opened:
        return False, "No browser or compatible application accepted the link."
    return True, ""


def open_local_file(
    path: str | Path,
    opener: Callable[[QUrl], bool] | None = None,
    text_editor_fallback: Callable[[Path], tuple[bool, str]] | None = None,
) -> tuple[bool, str]:
    """Open an existing regular file with the desktop MIME association."""

    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        return False, f"The file does not exist or cannot be resolved: {error}"
    if not resolved.is_file():
        return False, "The selected local path is not a regular file."
    try:
        opened = (opener or QDesktopServices.openUrl)(QUrl.fromLocalFile(str(resolved)))
    except Exception as error:
        return False, f"The desktop file handler failed: {error}"
    if opened:
        return True, ""
    fallback = text_editor_fallback or _launch_default_text_editor
    fallback_opened, _fallback_message = fallback(resolved)
    if fallback_opened:
        return True, ""
    return False, "No text editor or compatible application accepted the file."


def _default_text_editor_id() -> tuple[str, str]:
    xdg_mime = shutil.which("xdg-mime")
    if not xdg_mime:
        return "", "xdg-mime is unavailable."
    try:
        result = subprocess.run(
            [xdg_mime, "query", "default", "text/plain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return "", f"The default text editor could not be queried: {error}"
    desktop_id = result.stdout.strip()
    if result.returncode != 0 or not _DESKTOP_ID_RE.fullmatch(desktop_id):
        return "", "No valid text/plain desktop application is configured."
    return desktop_id, ""


def _desktop_file_for_id(desktop_id: str) -> Path | None:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    data_dirs = [
        Path(value)
        for value in os.environ.get(
            "XDG_DATA_DIRS",
            "/usr/local/share:/usr/share",
        ).split(":")
            if value
    ]
    return next(
        (
            root / "applications" / desktop_id
            for root in (data_home, *data_dirs)
            if (root / "applications" / desktop_id).is_file()
        ),
        None,
    )


def _launch_default_text_editor(path: Path) -> tuple[bool, str]:
    """Launch the text/plain desktop default without evaluating shell text."""

    desktop_id, error = _default_text_editor_id()
    if not desktop_id:
        return False, error
    desktop_file = _desktop_file_for_id(desktop_id)
    gio = shutil.which("gio")
    if desktop_file is None or not gio:
        return False, "The configured text editor launcher is unavailable."
    try:
        subprocess.Popen(
            [gio, "launch", str(desktop_file), path.as_uri()],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        return False, f"The default text editor could not be launched: {error}"
    return True, ""
