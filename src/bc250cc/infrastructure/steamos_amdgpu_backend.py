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

import re
import shlex
import stat
from pathlib import Path

STEAMOS_AMDGPU_BACKEND_ROOT = Path(
    "/usr/libexec/bc250-control-center/steamos-amdgpu-backend"
)
# Preserve the reviewed parent layout.  The upstream boot transaction calls
# ``../bc250-update-persistence.sh`` (which calls the storage sibling).
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
    # fetch-sources.sh delegates the channel-matched build dependencies to it
    # (upstream v0.38+).
    "bc250-audio-fix/fetch-build-deps.sh",
    "bc250-audio-fix/build.sh",
    "bc250-audio-fix/check-module.sh",
    "bc250-audio-fix/install.sh",
    "bc250-audio-fix/rollback.sh",
    "bc250-audio-fix/cleanup-other-slot.sh",
    # install.sh and rollback.sh call this for the Valve 7.2 mkinitcpio hook.
    "bc250-audio-fix/mkinitcpio-compat.sh",
    "bc250-update-persistence.sh",
    "bc250-storage.sh",
)
BACKEND_REQUIRED_REGULARS = (
    "bc250-audio-fix/build-env.sh",
    # bc250-mesh-shader.sh setup refuses to build Mesa 26.3 without this
    # patch next to it (upstream v0.40). It is data for ``patch``, not code.
    "bc250-mesa-patches/libdrm-2.4.134-wrap.patch",
)
#: What is copied from the reviewed commit: the kernel subtree, the RADV
#: entrypoint, the two parent siblings the boot transaction calls, and the
#: one Mesa patch file. Upstream's ``scripts/`` directory is deliberately not
#: copied: since v0.37 its entrypoints source ``scripts/feature-tracking.sh``
#: when it is present, which would run upstream's Python event recorder as
#: root. Without it the hook is skipped (upstream checks ``-f``) and the
#: scripts behave exactly as before.
BACKEND_ARCHIVE_PATHS = (
    "bc250-audio-fix",
    "bc250-mesh-shader.sh",
    "bc250-update-persistence.sh",
    "bc250-storage.sh",
    "bc250-mesa-patches/libdrm-2.4.134-wrap.patch",
)
BACKEND_EXCLUDED_PATHS = ("scripts",)
#: Protected copies staged by an earlier Control Center release that are still
#: trusted for the read-only checks (kernel and Mesa / RADV status) and the
#: stock-module rollback, with the members that release required. Control
#: Center 1.22.x (branch ``main``) staged keyboardspecialist v0.30.0. Its
#: ``patch-driver.sh status`` texts, ``rollback.sh``, ``cleanup-other-slot.sh``
#: and ``mkinitcpio-compat.sh`` are byte-identical to v0.40.0, and
#: ``boot-config.sh`` differs only by the tracking hook the staged copy never
#: contains. Every install, update or removal stages the current revision
#: first, so an old copy is replaced on the first such action.
LEGACY_STAGES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "e1563f2051727702a000b6ff6f6c524e2792aa21": (
        "v0.30.0",
        tuple(name for name in BACKEND_REQUIRED_EXECUTABLES
              if name != "bc250-audio-fix/fetch-build-deps.sh"),
        ("bc250-audio-fix/build-env.sh",),
    ),
}
ROLLBACK_COMPATIBLE_REVISIONS = tuple(LEGACY_STAGES)
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


def protected_backend_guard(
    root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT,
    *,
    shell_expression: bool = False,
    reviewed_revision: str = "",
    also_accepted_revisions: tuple[str, ...] = (),
    executables: tuple[str, ...] = BACKEND_REQUIRED_EXECUTABLES,
    regulars: tuple[str, ...] = BACKEND_REQUIRED_REGULARS,
) -> str:
    """Return a fail-closed shell predicate for the staged executable tree.

    Every entry must be a root-owned regular file/directory with no
    group/world write bit; symlinks and special files are refused.  Checking
    the complete tree matters because ``patch-driver.sh`` calls sibling
    scripts during its reviewed build transaction. Upstream's ``scripts/``
    directory must be absent (``BACKEND_EXCLUDED_PATHS``).

    ``also_accepted_revisions`` and a narrower member list exist only for
    :func:`rollback_backend_guard`.
    """
    revision = _reviewed_revision(reviewed_revision) if reviewed_revision else ""
    accepted = tuple(dict.fromkeys(
        (revision, *(_reviewed_revision(item) for item in also_accepted_revisions))
    )) if revision else ()
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
    for name in BACKEND_EXCLUDED_PATHS:
        path = f"{qroot}/{name}" if shell_expression else shlex.quote(str(Path(root) / name))
        checks.append(f"sudo test ! -e {path} && sudo test ! -L {path}")
    for name in executables:
        path = f"{qroot}/{name}" if shell_expression else shlex.quote(str(Path(root) / name))
        checks.extend((
            f"sudo test -f {path}",
            f"sudo test ! -L {path}",
            f"sudo test -x {path}",
        ))
    for name in regulars:
        path = f"{qroot}/{name}" if shell_expression else shlex.quote(str(Path(root) / name))
        checks.extend((
            f"sudo test -f {path}",
            f"sudo test ! -L {path}",
        ))
    if revision:
        checks.extend((
            f"sudo test -f {qrevision_file}",
            f"sudo test ! -L {qrevision_file}",
        ))
        if len(accepted) == 1:
            checks.append(
                f'[ "$(sudo tr -d "\\n" < {qrevision_file})" = {shlex.quote(revision)} ]'
            )
        else:
            patterns = "|".join(accepted)  # validated hexadecimal, nothing to quote
            checks.append(
                f'case "$(sudo tr -d "\\n" < {qrevision_file})" in {patterns}) true ;; *) false ;; esac'
            )
    return " && ".join(checks)


#: The members ``rollback.sh`` reaches: itself, the boot options and initramfs
#: helpers it calls, and the parent persistence/storage siblings boot-config.sh
#: calls. A backend staged from an older reviewed revision has all of them.
ROLLBACK_REQUIRED_EXECUTABLES = (
    "bc250-audio-fix/rollback.sh",
    "bc250-audio-fix/boot-config.sh",
    "bc250-audio-fix/mkinitcpio-compat.sh",
    "bc250-update-persistence.sh",
    "bc250-storage.sh",
)


def rollback_backend_guard(
    reviewed_revision: str, root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT
) -> str:
    """Guard for the stock-module rollback: the current or a compatible older stage."""
    return protected_backend_guard(
        root,
        reviewed_revision=reviewed_revision,
        also_accepted_revisions=ROLLBACK_COMPATIBLE_REVISIONS,
        executables=ROLLBACK_REQUIRED_EXECUTABLES,
        regulars=(),
    )


def existing_backend_guard(
    reviewed_revision: str, root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT
) -> str:
    """Guard for read-only status: the complete current stage or a complete legacy one.

    Each legacy copy must hold every member its own release required and pass
    the same ownership, permission and no-link checks. Actions that change the
    system never use this: they stage the current revision and check that.
    """
    guards = [protected_backend_guard(root, reviewed_revision=reviewed_revision)]
    for revision, (_version, executables, regulars) in LEGACY_STAGES.items():
        guards.append(protected_backend_guard(
            root, reviewed_revision=revision, executables=executables, regulars=regulars,
        ))
    return " || ".join(f"{{ {guard}; }}" for guard in guards)


def legacy_stage_note(root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT) -> str:
    """Say when the checked copy comes from an earlier Control Center release.

    Reads only the root-owned, world-readable revision marker; prints nothing
    for the current stage or an unreadable marker.
    """
    marker = shlex.quote(str(Path(root) / ".bc250-control-center-reviewed-revision"))
    branches = " ".join(
        f'{revision}) echo "[INFO] The protected keyboardspecialist copy was prepared by an '
        f'earlier Control Center release (toolkit {version}). Checks and restoring the stock '
        'module still use it; Install / update and Remove first replace it with the reviewed '
        'toolkit release, which needs a network connection.";;'
        for revision, (version, _executables, _regulars) in LEGACY_STAGES.items()
    )
    return f'case "$(tr -d "\\n" < {marker} 2>/dev/null || true)" in {branches} *) :;; esac'


def stage_backend_command(
    source_checkout: str | Path,
    reviewed_revision: str,
    *,
    subtree: str = "bc250-audio-fix",
    root: str | Path = STEAMOS_AMDGPU_BACKEND_ROOT,
) -> str:
    """Stage the exact reviewed toolkit subset without executing checkout files.

    The archive preserves the parent relationship between ``bc250-audio-fix``
    and its update-persistence/storage siblings and carries only the members of
    ``BACKEND_ARCHIVE_PATHS``.  A temporary root-owned tree
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
    qsiblings = " ".join(shlex.quote(path) for path in BACKEND_ARCHIVE_PATHS if path != subtree)
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
        f"if ! /usr/bin/git -C {qsource} archive --format=tar {qrevision} -- {qsubtree} {qsiblings} | sudo /usr/bin/tar --no-same-owner --no-same-permissions -xf - -C \"$stage_tmp\"; then sudo rm -rf -- \"$stage_tmp\"; echo \"ERROR: unable to archive the reviewed SteamOS toolkit\"; exit 38; fi",
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
