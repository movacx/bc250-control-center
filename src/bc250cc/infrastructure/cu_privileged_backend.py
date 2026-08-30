"""Trust checks for the staged Compute Units backend.

The live manager prepared in ResourceTools is intentionally user writable.  It
must never be executed as root.  SteamOS preparation therefore stages a copy,
including its UMR database, below a root-owned directory.  These helpers are
read-only and are shared by inventory and execution code.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

# SteamOS' persistent /var tree may be backed by the user offload volume and
# report uid nobody.  Privileged executable code and its static UMR model must
# live beside the installed root-owned helpers instead.
# SteamOS' immutable root exposes the helper directory itself reliably, while
# creating a new child directory can fail on some offload/overlay revisions.
# Keep the staged files beside the already-installed root-owned helpers.
STEAMOS_CU_BACKEND_ROOT = Path("/usr/libexec/bc250-control-center")
STEAMOS_CU_BACKEND = STEAMOS_CU_BACKEND_ROOT / "bc250-cu-live-manager"
STEAMOS_CU_DATABASE = STEAMOS_CU_BACKEND_ROOT / "bc250-cu-umr-database"

# Bazzite and other generic immutable desktops keep /usr read-only at runtime.
# Unlike SteamOS, their root-owned /var/lib tree is a supported persistent
# location for application state.  Keep the mutable source checkout in the
# user's ResourceTools directory, but promote the reviewed executable into
# this root-owned directory before a privileged CU action can use it.
GENERIC_CU_BACKEND_ROOT = Path("/var/lib/bc250-control-center")
GENERIC_CU_BACKEND = GENERIC_CU_BACKEND_ROOT / "bc250-cu-live-manager"

# On Bazzite deployments whose persistent tree is root-squashed, a file made
# by ``sudo`` is presented to the desktop namespace as the anonymous NFS UID.
# It remains non-writable to the logged-in user (mode 0755); rejecting it only
# because the namespace cannot represent UID 0 leaves CU permanently locked.
# Accept that one mapped privileged owner, never a user-selected UID, and keep
# the no-symlink/non-group-or-world-writable checks below.
PRIVILEGED_OWNER_UIDS = frozenset({0, 65534})


def _trusted_root_path(path: Path, *, executable: bool = False) -> bool:
    """Require a regular, non-symlink, root-owned and non-writable object."""
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return False
    if metadata.st_uid not in PRIVILEGED_OWNER_UIDS or metadata.st_mode & 0o022:
        return False
    return not executable or bool(metadata.st_mode & 0o111)


def steamos_cu_backend_status(
    backend: Path = STEAMOS_CU_BACKEND,
    database: Path = STEAMOS_CU_DATABASE,
) -> tuple[bool, str]:
    """Return whether the complete privileged runtime has a safe filesystem boundary."""
    root = backend.parent
    try:
        root_metadata = root.lstat()
    except OSError:
        return False, f"The staged CU backend is missing at {backend}. Run Prepare dependencies."
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid not in PRIVILEGED_OWNER_UIDS
        or root_metadata.st_mode & 0o022
    ):
        return False, f"The staged CU backend directory is not protected: {root}."
    if not _trusted_root_path(backend, executable=True):
        return False, f"The staged CU executable is missing or not root-owned mode 0755: {backend}."
    model = database / "cyan_skillfish.asic"
    if not _trusted_root_path(model):
        return False, f"The staged UMR database is missing or untrusted: {model}."
    try:
        header = model.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return False, f"The staged UMR ASIC model is empty: {model}."
    if not header.startswith("cyan_skillfish "):
        return False, f"The staged UMR ASIC model has an invalid header: {model}."
    return True, f"Verified root-owned CU backend: {backend}"


def generic_cu_backend_status(backend: Path = GENERIC_CU_BACKEND) -> tuple[bool, str]:
    """Verify the executable boundary used outside SteamOS.

    Generic distributions use their package UMR database; unlike SteamOS they
    must not be forced through the Cyan static-database compatibility copy.
    """
    root = backend.parent
    try:
        root_metadata = root.lstat()
    except OSError:
        return False, f"The staged CU backend is missing at {backend}. Run Prepare dependencies."
    if (stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid not in PRIVILEGED_OWNER_UIDS or root_metadata.st_mode & 0o022):
        return False, f"The staged CU backend directory is not protected: {root}."
    if not _trusted_root_path(backend, executable=True):
        return False, f"The staged CU executable is missing or unsafe: {backend}."
    return True, f"Verified root-owned CU backend: {backend}"


def trusted_cu_environment(database: Path = STEAMOS_CU_DATABASE) -> dict[str, str]:
    """Environment accepted by the staged SteamOS backend.

    The selector remains database-defined inside the compatibility backend; no
    caller-controlled UMR path or ASIC selector is forwarded across privilege.
    """
    return {"UMR_DATABASE_PATH": os.fspath(database)}
