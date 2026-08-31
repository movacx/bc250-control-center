"""Pinned Bazzite 44 lifecycle for the BC-250 async-compute RADV driver."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

BAZZITE_ASYNC_COMPUTE_REPOSITORY = (
    "https://github.com/tri3gubki-ops/bc250-async-compute-bazzite"
)
BAZZITE_ASYNC_COMPUTE_VERSION = "0.2.4"
BAZZITE_ASYNC_COMPUTE_TAG = f"v{BAZZITE_ASYNC_COMPUTE_VERSION}"
BAZZITE_ASYNC_COMPUTE_COMMIT = "aca67e88542d81334fb0161803039d8a0f2945f6"
BAZZITE_ASYNC_COMPUTE_TESTED_KERNEL = "7.2.0-ogc4.1"
BAZZITE_ASYNC_COMPUTE_ARCHIVE_SHA256 = (
    "fabece2f0735fd4f096bb253894f53d342e1eb4ec18c761eaca1ac9d20330711"
)
BAZZITE_ASYNC_COMPUTE_MINIMUM_KERNEL = (7, 2, 0, 4, 1)
BAZZITE_ASYNC_COMPUTE_PREFIX = Path("/usr/local/lib/bc250-radv")
BAZZITE_ASYNC_COMPUTE_SHARE = Path("/usr/local/share/bc250-async-compute")
BAZZITE_ASYNC_COMPUTE_ENV = Path(
    "/etc/environment.d/95-bc250-async-compute.conf"
)
BAZZITE_ASYNC_COMPUTE_ICD = (
    BAZZITE_ASYNC_COMPUTE_PREFIX
    / "share/vulkan/icd.d/radeon_icd.x86_64.json"
)

_ACTIONS = frozenset({"install", "status", "uninstall"})
_KERNEL_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)-ogc"
    r"(?P<ogc_major>\d+)\.(?P<ogc_minor>\d+)(?:[.-]|$)",
    re.IGNORECASE,
)


def bazzite_async_kernel_supported(kernel: str) -> bool:
    """Return whether *kernel* meets the exact OGC baseline documented by v0.2.4."""

    match = _KERNEL_RE.match(str(kernel or "").strip())
    if not match:
        return False
    version = tuple(int(match.group(name)) for name in (
        "major", "minor", "patch", "ogc_major", "ogc_minor"
    ))
    return version >= BAZZITE_ASYNC_COMPUTE_MINIMUM_KERNEL


def probe_bazzite_async_compute() -> dict:
    """Inspect the upstream installation without executing its helper."""

    library = BAZZITE_ASYNC_COMPUTE_PREFIX / "lib64/libvulkan_radeon.so"
    helper = Path("/usr/local/bin/bc250-async-compute")
    version_file = BAZZITE_ASYNC_COMPUTE_SHARE / "VERSION"
    installed_version = ""
    try:
        installed_version = version_file.read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except OSError:
        pass

    manifest_valid = False
    try:
        manifest = json.loads(BAZZITE_ASYNC_COMPUTE_ICD.read_text(encoding="utf-8"))
        icd = manifest.get("ICD", {})
        manifest_valid = (
            manifest.get("file_format_version") == "1.0.1"
            and icd.get("library_path") == str(library)
            and icd.get("library_arch") == "64"
        )
    except (OSError, TypeError, ValueError):
        pass

    artifacts = any(path.exists() for path in (
        library, helper, version_file, BAZZITE_ASYNC_COMPUTE_ICD,
    ))
    current = bool(
        library.is_file()
        and not library.is_symlink()
        and helper.is_file()
        and not helper.is_symlink()
        and manifest_valid
        and installed_version == BAZZITE_ASYNC_COMPUTE_VERSION
    )
    enabled = BAZZITE_ASYNC_COMPUTE_ENV.is_file()
    expected_icd = str(BAZZITE_ASYNC_COMPUTE_ICD)
    session_driver_files = str(os.environ.get("VK_DRIVER_FILES") or "")
    session_active = expected_icd in session_driver_files.split(":")
    return {
        "bazzite_async_installed": artifacts,
        "bazzite_async_current": current,
        "bazzite_async_enabled": enabled,
        "bazzite_async_session_active": session_active,
        "bazzite_async_installed_version": installed_version,
        "bazzite_async_expected_version": BAZZITE_ASYNC_COMPUTE_VERSION,
        "bazzite_async_state": (
            "active" if current and session_active
            else "relogin-required" if current and enabled
            else "ready" if current
            else "invalid" if artifacts
            else "not-installed"
        ),
    }


def build_bazzite_async_compute_command(action: str) -> str:
    """Build a closed command around the reviewed, checksum-pinned v0.2.4 release."""

    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        raise ValueError(f"Unsupported Bazzite async-compute action: {action or '--'}")

    archive_name = f"bc250-async-compute-{BAZZITE_ASYNC_COMPUTE_VERSION}.tar.zst"
    archive_url = (
        f"{BAZZITE_ASYNC_COMPUTE_REPOSITORY}/releases/download/"
        f"{BAZZITE_ASYNC_COMPUTE_TAG}/{archive_name}"
    )
    source_dir = f"bc250-async-compute-{BAZZITE_ASYNC_COMPUTE_VERSION}"
    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        'echo "== BC-250 async compute v0.2.4 for Bazzite 44 =="',
        'test -r /etc/os-release || { echo "ERROR: /etc/os-release is unavailable."; exit 64; }',
        ". /etc/os-release",
        'test "${ID:-}" = bazzite || { echo "ERROR: This workflow is available only on Bazzite."; exit 64; }',
        'test "${VERSION_ID:-}" = 44 || { echo "ERROR: Release v0.2.4 supports Bazzite 44 only."; exit 64; }',
        'test "$(uname -m)" = x86_64 || { echo "ERROR: The reviewed payload is x86_64-only."; exit 64; }',
    ]
    if action == "status":
        commands.extend((
            'command -v bc250-async-compute >/dev/null 2>&1 || { echo "Not installed: bc250-async-compute was not found."; exit 3; }',
            "bc250-async-compute status",
        ))
        return "\n".join(commands)

    required_commands = (
        "curl sha256sum tar lspci sort sudo"
        if action == "install"
        else "curl sha256sum tar sudo"
    )
    commands.extend((
        f"for bc250_command in {required_commands}; do",
        '  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }',
        "done",
    ))
    if action == "install":
        commands.extend((
            "bc250_found=0",
            "for bc250_device in /sys/bus/pci/devices/*; do",
            '  test -r "$bc250_device/vendor" && test -r "$bc250_device/device" || continue',
            '  test "$(cat "$bc250_device/vendor")" = 0x1002 && test "$(cat "$bc250_device/device")" = 0x13fe && bc250_found=1 && break',
            "done",
            'test "$bc250_found" = 1 || { echo "ERROR: AMD BC-250 PCI device 1002:13fe was not found."; exit 64; }',
            'bc250_kernel="$(uname -r)"',
            'case "$bc250_kernel" in *-ogc*) ;; *) echo "ERROR: v0.2.4 was tested only with the Bazzite OGC kernel."; exit 64 ;; esac',
            'bc250_kernel_base="${bc250_kernel%%-*}"',
            'test "$(printf \'%s\\n\' 7.2.0 "$bc250_kernel_base" | sort -V | head -n 1)" = 7.2.0 || { echo "ERROR: v0.2.4 requires kernel 7.2.0-ogc4.1 or newer; running $bc250_kernel."; exit 64; }',
            'if test "$bc250_kernel_base" = 7.2.0; then',
            '  bc250_ogc="${bc250_kernel#*-ogc}"; bc250_ogc="${bc250_ogc%%.*}.${bc250_ogc#*.}"',
            '  bc250_ogc_major="${bc250_ogc%%.*}"; bc250_ogc_rest="${bc250_kernel#*-ogc${bc250_ogc_major}.}"; bc250_ogc_minor="${bc250_ogc_rest%%.*}"',
            '  test "$bc250_ogc_major" -gt 4 || { test "$bc250_ogc_major" -eq 4 && test "$bc250_ogc_minor" -ge 1; } || { echo "ERROR: v0.2.4 requires kernel 7.2.0-ogc4.1 or newer; running $bc250_kernel."; exit 64; }',
            "fi",
        ))
    commands.extend((
        'bc250_stage="$(mktemp -d /tmp/bc250-async-compute.XXXXXX)"',
        'trap \'rm -rf -- "$bc250_stage"\' EXIT',
        f'bc250_archive="$bc250_stage/{archive_name}"',
        f'curl --fail --location --retry 2 --output "$bc250_archive" {archive_url}',
        f"printf '%s  %s\\n' {BAZZITE_ASYNC_COMPUTE_ARCHIVE_SHA256} \"$bc250_archive\" | sha256sum --check --status || {{ echo \"ERROR: release archive checksum mismatch.\"; exit 29; }}",
        'tar --zstd -xf "$bc250_archive" -C "$bc250_stage"',
        f'bc250_source="$bc250_stage/{source_dir}"',
        'test -d "$bc250_source" && test ! -L "$bc250_source" || { echo "ERROR: invalid release archive root."; exit 29; }',
        f'test "$(cat "$bc250_source/VERSION" 2>/dev/null)" = {BAZZITE_ASYNC_COMPUTE_VERSION} || {{ echo "ERROR: unexpected release version."; exit 29; }}',
        'test -x "$bc250_source/install.sh" && test -x "$bc250_source/uninstall.sh" || { echo "ERROR: release lifecycle scripts are missing."; exit 29; }',
    ))
    if action == "install":
        commands.extend((
            'test -s "$bc250_source/payload/lib64/libvulkan_radeon.so" || { echo "ERROR: reviewed RADV payload is missing."; exit 29; }',
            'sudo "$bc250_source/install.sh" --yes',
            f'test "$(cat {BAZZITE_ASYNC_COMPUTE_SHARE}/VERSION 2>/dev/null)" = {BAZZITE_ASYNC_COMPUTE_VERSION} || {{ echo "ERROR: installed version validation failed."; exit 29; }}',
            'echo "OK: async compute v0.2.4 installed. Log out and back in to activate the patched RADV driver."',
            'echo "RECOVERY: Ctrl+Alt+F3, then sudo rm /etc/environment.d/95-bc250-async-compute.conf and reboot."',
        ))
    else:
        commands.extend((
            'sudo "$bc250_source/uninstall.sh"',
            'echo "OK: the Bazzite async-compute runtime was removed. Log out and back in to return to stock RADV."',
        ))
    return "\n".join(commands)
