"""Protected staging boundary for the reviewed SteamOS AMDGPU toolkit.

The checkout below ``ResourceTools`` belongs to the desktop user.  It is a
useful immutable *source* reference, but it must never be passed directly to
``sudo bash``: a checked-out commit alone does not make a user-writable path a
safe privileged executable.  This module stages the exact Git tree into the
same root-owned helper directory used by Control Center's other SteamOS
boundaries, then exposes a shell predicate shared by installation and
read-only diagnostics.
"""

from __future__ import annotations

import os
import re
import shlex
import stat
from pathlib import Path

STEAMOS_AMDGPU_BACKEND_ROOT = Path(
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend"
)
# Preserve the reviewed parent layout.  The upstream boot transaction calls
# ``../bc250-update-persistence.sh`` (which calls the storage sibling), and
# the Control Center telemetry overlay targets ``bc250-audio-fix/build.sh``.
STEAMOS_AMDGPU_AUDIO_FIX_ROOT = STEAMOS_AMDGPU_BACKEND_ROOT / "bc250-audio-fix"
STEAMOS_AMDGPU_BACKEND = STEAMOS_AMDGPU_AUDIO_FIX_ROOT / "patch-driver.sh"
STEAMOS_AMDGPU_BOOT_CONFIG = STEAMOS_AMDGPU_AUDIO_FIX_ROOT / "boot-config.sh"
STEAMOS_GRAPHICS_BACKEND = STEAMOS_AMDGPU_BACKEND_ROOT / "bc250-mesh-shader.sh"
STEAMOS_AMDGPU_BACKEND_REVISION = (
    STEAMOS_AMDGPU_BACKEND_ROOT / ".bc250-control-center-reviewed-revision"
)

# ``patch-driver.sh`` delegates the full installation to these siblings.  A
# staged tree containing only the status pair is sufficient for Health's
# read-only check, but it is not sufficient to authorize the explicit install
# workflow.  Validate these exact committed members before replacing an
# existing protected backend so a partial archive cannot fail after the old
# runtime has already been displaced.
BACKEND_REQUIRED_EXECUTABLES = (
    "bc250-mesh-shader.sh",
    "bc250-audio-fix/patch-driver.sh",
    "bc250-audio-fix/boot-config.sh",
    "bc250-audio-fix/ensure-build-prereqs.sh",
    "bc250-audio-fix/fetch-sources.sh",
    "bc250-audio-fix/build.sh",
    "bc250-audio-fix/check-module.sh",
    "bc250-audio-fix/install.sh",
    "bc250-audio-fix/rollback.sh",
    "bc250-audio-fix/cleanup-other-slot.sh",
    "bc250-update-persistence.sh",
    "bc250-storage.sh",
)
BACKEND_REQUIRED_REGULARS = ("bc250-audio-fix/build-env.sh",)
BACKEND_STATUS_EXECUTABLES = (
    "bc250-audio-fix/patch-driver.sh",
    "bc250-audio-fix/boot-config.sh",
)


def _reviewed_revision(value: str) -> str:
    revision = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("SteamOS AMDGPU staging requires an exact 40-character Git revision.")
    return revision


def _safe_subtree(value: str) -> str:
    subtree = str(value or "").strip().strip("/")
    parts = tuple(part for part in subtree.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("SteamOS AMDGPU staging requires a relative toolkit subtree.")
    return "/".join(parts)


def _protected_path(path: Path, *, directory: bool = False, executable: bool = False) -> bool:
    """Check one installed backend path without following a symlink.

    This is deliberately narrower than the shell staging guard: Health only
    needs to decide whether it may invoke the fixed read-only ``status``
    entrypoint, not recursively attest a potentially large build workspace.
    The root directory plus both entry scripts and immutable revision marker
    must be root-owned and non-writable by group/other.
    """
    try:
        metadata = path.lstat()
    except OSError:
        return False
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (
        expected_kind(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == 0
        and not metadata.st_mode & 0o022
        and (not executable or bool(metadata.st_mode & stat.S_IXUSR))
    )


def protected_backend_status_ready(
    root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT,
    *,
    reviewed_revision: str,
) -> tuple[bool, str]:
    """Return whether Health may safely run the staged read-only status tool.

    No command is executed and no path is modified.  A revision mismatch is
    treated as untrusted rather than falling back to a mutable checkout.
    """
    revision = _reviewed_revision(reviewed_revision)
    backend_root = Path(root)
    if not _protected_path(backend_root, directory=True):
        return False, "backend directory is missing, symbolic or not root-owned"
    for relative in BACKEND_STATUS_EXECUTABLES:
        # Checking a regular root-owned script alone is insufficient: a
        # group-writable intermediate directory could unlink and replace it.
        # Validate every directory between the protected stage root and the
        # final executable without following symlinks.
        parent = backend_root
        for component in Path(relative).parent.parts:
            parent /= component
            if not _protected_path(parent, directory=True):
                return False, f"{component} directory is missing, symbolic or not protected"
        path = backend_root / relative
        if not _protected_path(path, executable=True):
            return False, f"{relative} is missing, symbolic or not protected"
    marker = backend_root / ".bc250-control-center-reviewed-revision"
    if not _protected_path(marker):
        return False, "revision marker is missing, symbolic or not protected"
    descriptor = -1
    try:
        descriptor = os.open(
            marker,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        content = os.read(descriptor, 128)
        if os.read(descriptor, 1):
            return False, "revision marker exceeds its bounded format"
    except OSError:
        return False, "revision marker could not be read safely"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        observed = content.decode("ascii", errors="strict").strip().lower()
    except UnicodeDecodeError:
        return False, "revision marker is not ASCII"
    if observed != revision:
        return False, "revision marker does not match this Control Center build"
    return True, "protected staged backend matches the reviewed revision"


def protected_backend_guard(
    root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT,
    *,
    shell_expression: bool = False,
    reviewed_revision: str = "",
) -> str:
    """Return a fail-closed shell predicate for the staged executable tree.

    Every entry must be a root-owned regular file/directory with no
    group/world write bit; symlinks and special files are refused.  Checking
    the complete tree matters because ``patch-driver.sh`` calls sibling
    scripts during its reviewed build transaction.
    """
    revision = _reviewed_revision(reviewed_revision) if reviewed_revision else ""
    if shell_expression:
        qroot = str(root)
        qrevision_file = f"{qroot}/.bc250-control-center-reviewed-revision"
    else:
        qroot = shlex.quote(str(Path(root)))
        qrevision_file = shlex.quote(
            str(Path(root) / ".bc250-control-center-reviewed-revision")
        )
    checks = [
        f"sudo test -d {qroot}",
        f"sudo test ! -L {qroot}",
        f'[ "$(sudo stat -c %u {qroot})" = "0" ]',
        f'! sudo find {qroot} -xdev '
        r"\( -type l -o \( ! -type f -a ! -type d \) -o ! -uid 0 -o -perm /022 \) "
        "-print -quit | grep -q .",
    ]
    for name in BACKEND_REQUIRED_EXECUTABLES:
        path = f"{qroot}/{name}" if shell_expression else shlex.quote(str(Path(root) / name))
        checks.extend((
            f"sudo test -f {path}",
            f"sudo test ! -L {path}",
            f"sudo test -x {path}",
        ))
    for name in BACKEND_REQUIRED_REGULARS:
        path = f"{qroot}/{name}" if shell_expression else shlex.quote(str(Path(root) / name))
        checks.extend((
            f"sudo test -f {path}",
            f"sudo test ! -L {path}",
        ))
    if revision:
        checks.extend((
            f"sudo test -f {qrevision_file}",
            f"sudo test ! -L {qrevision_file}",
            f'[ "$(sudo tr -d "\\n" < {qrevision_file})" = {shlex.quote(revision)} ]',
        ))
    return " && ".join(checks)


def stage_backend_command(
    source_checkout: str | Path,
    reviewed_revision: str,
    *,
    subtree: str = "bc250-audio-fix",
    root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT,
) -> str:
    """Stage the exact reviewed toolkit subset without executing checkout files.

    The archive preserves the parent relationship between ``bc250-audio-fix``
    and its update-persistence/storage siblings.  A temporary root-owned tree
    is verified before it replaces the previous staged tree; if final
    verification fails, the previous protected runtime is restored.  The
    caller must place this command inside SteamOS' short writable-root wrapper.
    """
    revision = _reviewed_revision(reviewed_revision)
    subtree = _safe_subtree(subtree)
    if subtree != "bc250-audio-fix":
        raise ValueError(
            "SteamOS AMDGPU staging requires the reviewed bc250-audio-fix subtree."
        )
    source = Path(source_checkout)
    stage_root = Path(root)
    parent = stage_root.parent
    qsource = shlex.quote(str(source))
    qroot = shlex.quote(str(stage_root))
    qparent = shlex.quote(str(parent))
    qrevision = shlex.quote(revision)
    qsubtree = shlex.quote(subtree)
    required_members = BACKEND_REQUIRED_EXECUTABLES + BACKEND_REQUIRED_REGULARS
    staged_guard = protected_backend_guard(
        '"$stage_tmp"', shell_expression=True, reviewed_revision=revision
    )
    final_guard = protected_backend_guard(stage_root, reviewed_revision=revision)
    return "; ".join((
        'echo "== Staging protected SteamOS AMDGPU backend =="',
        f"test -d {qsource}/.git || {{ echo \"ERROR: reviewed SteamOS toolkit checkout is missing\"; exit 38; }}",
        f'actual_revision="$(/usr/bin/git -C {qsource} rev-parse --verify {qrevision}^{{commit}} 2>/dev/null || true)"',
        f'[ "$actual_revision" = {qrevision} ] || {{ echo "ERROR: reviewed SteamOS toolkit commit is unavailable"; exit 38; }}',
        *(
            f"/usr/bin/git -C {qsource} cat-file -e "
            f"{shlex.quote(f'{revision}:{name}')} || "
            f"{{ echo \"ERROR: reviewed {name} is absent from the pinned commit\"; exit 38; }}"
            for name in required_members
        ),
        f"sudo install -d -o root -g root -m 0755 {qparent}",
        f'stage_tmp="$(sudo mktemp -d {qparent}/.steamos-amdgpu-stage.XXXXXX)"',
        f"if ! /usr/bin/git -C {qsource} archive --format=tar {qrevision} -- {qsubtree} bc250-mesh-shader.sh bc250-update-persistence.sh bc250-storage.sh | sudo /usr/bin/tar --no-same-owner --no-same-permissions -xf - -C \"$stage_tmp\"; then sudo rm -rf -- \"$stage_tmp\"; echo \"ERROR: unable to archive the reviewed SteamOS toolkit\"; exit 38; fi",
        'sudo chown -R root:root "$stage_tmp"',
        'sudo find "$stage_tmp" -type d -exec chmod 0755 {} +',
        'sudo find "$stage_tmp" -type f -exec chmod go-w {} +',
        'sudo chmod 0755 ' + ' '.join(
            f'"$stage_tmp/{name}"' for name in BACKEND_REQUIRED_EXECUTABLES
        ),
        f'printf "%s\\n" {qrevision} | sudo tee "$stage_tmp/.bc250-control-center-reviewed-revision" >/dev/null',
        'sudo chmod 0644 "$stage_tmp/.bc250-control-center-reviewed-revision"',
        f"{staged_guard} || {{ sudo rm -rf -- \"$stage_tmp\"; echo \"ERROR: staged SteamOS AMDGPU backend did not pass protection checks\"; exit 38; }}",
        f"stage_previous={qparent}/.steamos-amdgpu-backend.previous",
        'sudo rm -rf -- "$stage_previous"',
        f'had_previous=0; if sudo test -e {qroot}; then sudo mv -- {qroot} "$stage_previous"; had_previous=1; fi',
        f'if ! sudo mv -- "$stage_tmp" {qroot} || ! {{ {final_guard}; }}; then sudo rm -rf -- {qroot}; if [ "$had_previous" = 1 ]; then sudo mv -- "$stage_previous" {qroot}; fi; echo "ERROR: protected SteamOS AMDGPU backend staging did not validate"; exit 38; fi',
        'sudo rm -rf -- "$stage_previous"',
        f'echo "[OK] Protected SteamOS AMDGPU backend staged at {stage_root}"',
    ))
