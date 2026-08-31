"""Pure shell builders for the SteamOS-specific CU/UMR backend."""

from __future__ import annotations

import shlex
from pathlib import Path

from bc250cc.infrastructure.cu_privileged_backend import (
    GENERIC_CU_BACKEND_ROOT,
    STEAMOS_CU_BACKEND_ROOT,
)

# These are hashes of the executable scripts in the immutable revisions named
# in ``external_tools.py``.  A CU manager is later run by a boot service, so a
# mere ``git checkout`` in the user's ResourceTools directory is not a strong
# enough boundary: the root staging operation must verify the exact payload it
# promotes before it becomes executable by root.
STANDARD_CU_MANAGER_SHA256 = "304d0b51838ec4ffc80c56894c4867a04523bf1ba27e51f662cbfc79616e442d"
STEAMOS_CU_UPSTREAM_SHA256 = "bd3d3a192870b500021eb4bb3c843556702de179b1f82ca69c8956a964b7c106"
STEAMOS_CU_COMPAT_SHA256 = "0ad172eaf4b78adc7384f19a9ca6f3938389db96f1e7b7bfa2b26967cf61d308"


def _verified_root_stage_command(
    script: str | Path,
    expected_sha256: str,
    *,
    label: str,
    root: Path = STEAMOS_CU_BACKEND_ROOT,
) -> str:
    """Copy a reviewed script atomically and verify it *after* root reads it.

    The source checkout is deliberately user-owned.  Checking it before a
    later ``sudo install`` leaves a replace-between-check-and-copy window.
    Instead root writes a private temporary file, hashes that exact copy, and
    only then atomically promotes it to the executable path.
    """
    qscript = shlex.quote(str(script))
    qroot = shlex.quote(str(root))
    target = shlex.quote(str(root / "bc250-cu-live-manager"))
    temporary = shlex.quote(str(root / ".bc250-cu-live-manager.new"))
    steamos_normalization = ""
    if root == STEAMOS_CU_BACKEND_ROOT:
        steamos_normalization = (
            # Normalize again after promotion.  This repairs a stale SteamOS
            # runtime from an older Control Center even when the user checkout
            # is already present and no fresh clone is needed.
            f'sudo chown root:root {target}; '
            f'sudo chmod 0755 {target}; '
            f'sudo test ! -L {target}; '
            f'test "$(sudo stat -c %u {target})" = 0; '
            f'test "$(sudo stat -c %a {target})" = 755; '
        )
    return (
        f'echo "== Staging protected {label} CU backend =="; '
        f'sudo install -d -o root -g root -m 0755 {qroot}; '
        f'sudo rm -f -- {temporary}; '
        f'sudo install -o root -g root -m 0755 {qscript} {temporary}; '
        f'sudo sha256sum {temporary} | awk "{{print \\$1}}" | grep -Fx {shlex.quote(expected_sha256)} '
        f'|| {{ sudo rm -f -- {temporary}; echo "ERROR: reviewed CU backend digest mismatch; refusing root staging."; exit 37; }}; '
        f'sudo mv -f -- {temporary} {target}; '
        f'{steamos_normalization}'
        f'echo "[OK] Protected CU backend staged at {root}"'
    )


def umr_database_path(tools_dir: str | Path) -> Path:
    return Path(tools_dir) / "umr-steamos" / "database"


def cu_backend_prepare_command(spec: dict, patcher: str | Path) -> str:
    if not spec.get("is_steamos"):
        return ""
    command = " ".join((
        "python3",
        shlex.quote(str(patcher)),
        shlex.quote(str(spec["upstream_script"])),
        shlex.quote(str(spec["script"])),
    ))
    upstream = shlex.quote(str(spec["upstream_script"]))
    runtime = shlex.quote(str(spec["script"]))
    return (
        f'sha256sum {upstream} | awk "{{print \\$1}}" | grep -Fx {STEAMOS_CU_UPSTREAM_SHA256} '
        '|| { echo "ERROR: reviewed SteamOS CU upstream digest mismatch."; exit 37; }; '
        + command
        + '; '
        + f'sha256sum {runtime} | awk "{{print \\$1}}" | grep -Fx {STEAMOS_CU_COMPAT_SHA256} '
        '|| { echo "ERROR: generated SteamOS CU compatibility backend digest mismatch."; exit 37; }'
    )


def cu_env_shell(database: str | Path, repair: str | Path) -> str:
    database = Path(database)
    selector = (
        f"sudo python3 {shlex.quote(str(repair))} "
        f"--target {shlex.quote(str(database))} "
        '--owner-uid "$(id -u)" --check-only --print-selector'
    )
    return (
        f"export UMR_DATABASE_PATH={shlex.quote(str(database))}; "
        f'export UMR_ASIC="${{UMR_ASIC:-$({selector})}}"; '
        'test -n "$UMR_ASIC" || { echo "ERROR: CU_UMR_SELECTOR_UNKNOWN: could not derive the BC-250 register namespace from cyan_skillfish.asic"; exit 37; }; '
    )


def database_repair_command(database: str | Path, repair: str | Path, *, check_only=False) -> str:
    command = [
        "python3",
        shlex.quote(str(repair)),
        "--target",
        shlex.quote(str(database)),
        "--legacy-root",
        shlex.quote("/var/lib/bc250-cu-live-manager/umr"),
        "--owner-uid",
        '"$(id -u)"',
    ]
    command.extend(["--check-only"] if check_only else ["--cleanup-legacy", "--update-service-config"])
    return "sudo " + " ".join(command)


def service_backend_update_command(script: str | Path) -> str:
    qscript = shlex.quote(str(script))
    service = shlex.quote("/etc/systemd/system/bc250-cu-live-manager.service")
    return (
        f"if sudo test -f {service}; then "
        f"exec_path=\"$(sudo sed -n 's/^ExecStart=\\([^[:space:]]*\\).*/\\1/p' {service} | head -n 1)\"; "
        'case "$exec_path" in '
        "  /var/lib/bc250-cu-live-manager/umr/bc250-cu-live-manager|"
        "  /usr/local/bin/bc250-cu-live-manager|"
        "  /var/usrlocal/bin/bc250-cu-live-manager) "
        f'    sudo install -m 0755 {qscript} "$exec_path"; '
        '    echo "[OK] Updated installed CU service backend: $exec_path" ;; '
        '  *) echo "[WARN] Existing CU service ExecStart is outside the allowed BC250 paths: $exec_path" ;; '
        "esac; sudo systemctl daemon-reload; fi"
    )


def privileged_backend_stage_command(script: str | Path, database: str | Path) -> str:
    """Stage the reviewed runtime and database without executing either one."""
    qdatabase = shlex.quote(str(database))
    qroot = shlex.quote(str(STEAMOS_CU_BACKEND_ROOT))
    return (
        _verified_root_stage_command(
            script, STEAMOS_CU_COMPAT_SHA256, label="SteamOS"
        )
        + '; '
        f'sudo rm -rf -- {qroot}/bc250-cu-umr-database.new; '
        f'sudo cp -a -- {qdatabase} {qroot}/bc250-cu-umr-database.new; '
        f'sudo chown -R root:root {qroot}/bc250-cu-umr-database.new; '
        f'sudo find {qroot}/bc250-cu-umr-database.new -type d -exec chmod 0755 {{}} +; '
        f'sudo find {qroot}/bc250-cu-umr-database.new -type f -exec chmod 0644 {{}} +; '
        f'sudo test -s {qroot}/bc250-cu-umr-database.new/cyan_skillfish.asic; '
        f'if sudo test -e {qroot}/bc250-cu-umr-database; then '
        f'  sudo rm -rf -- {qroot}/bc250-cu-umr-database.previous; '
        f'  sudo mv -- {qroot}/bc250-cu-umr-database {qroot}/bc250-cu-umr-database.previous; '
        'fi; '
        f'sudo mv -- {qroot}/bc250-cu-umr-database.new {qroot}/bc250-cu-umr-database; '
        'if sudo test -f /etc/bc250-cu-live-manager.conf; then '
        '  sudo cp -a -- /etc/bc250-cu-live-manager.conf /etc/bc250-cu-live-manager.conf.bc250-backup; '
        f'  sudo sed -i "s|^UMR_DATABASE_PATH=.*|UMR_DATABASE_PATH={STEAMOS_CU_BACKEND_ROOT}/bc250-cu-umr-database|" /etc/bc250-cu-live-manager.conf; '
        'fi; '
        f'echo "[OK] Protected CU backend staged at {STEAMOS_CU_BACKEND_ROOT}"'
    )


def generic_privileged_backend_stage_command(script: str | Path) -> str:
    """Stage the reviewed generic manager in its writable persistent root."""
    return _verified_root_stage_command(
        script,
        STANDARD_CU_MANAGER_SHA256,
        label="generic",
        root=GENERIC_CU_BACKEND_ROOT,
    )


def status_probe_command(
    script: str | Path,
    *,
    environment_shell: str,
    check_database_command: str,
) -> str:
    qscript = shlex.quote(str(script))
    return (
        'echo "== Verifying SteamOS 40CU UMR selector =="; '
        + environment_shell
        + 'echo "UMR_DATABASE_PATH=$UMR_DATABASE_PATH"; '
        + check_database_command
        + ' || { echo "ERROR: CU_UMR_DATABASE_INVALID: the SteamOS user database is missing or malformed."; exit 37; }; '
        + 'instance="${UMR_INSTANCE:-}"; '
        + "bc250_bdf=\"$(lspci -Dnn 2>/dev/null | awk 'tolower($0) ~ /\\[1002:13fe\\]/ { print $1; exit }' || true)\"; "
        + 'if [ -z "$instance" ] && [ -d /sys/kernel/debug/dri ]; then '
        + '  for d in /sys/kernel/debug/dri/[0-9]*; do '
        + '    n="${d##*/}"; [ "$n" -lt 128 ] 2>/dev/null || continue; '
        + '    dri_name="$(sudo cat "$d/name" 2>/dev/null || true)"; '
        + '    if [ -n "$bc250_bdf" ] && printf "%s" "$dri_name" | grep -Fqi "$bc250_bdf"; then instance="$n"; break; fi; '
        + '    [ -z "$instance" ] && [ "$n" = "0" ] && instance=0; '
        + "  done; "
        + "fi; "
        + 'instance="${instance:-0}"; '
        + 'echo "Trying UMR_ASIC=$UMR_ASIC UMR_INSTANCE=$instance"; '
        + 'bc250_cu_status_file="$(mktemp "${XDG_RUNTIME_DIR:-/tmp}/bc250-cu-status.XXXXXX")"; '
        + 'chmod 0600 "$bc250_cu_status_file"; '
        + f'if sudo env UMR_DATABASE_PATH="$UMR_DATABASE_PATH" UMR_ASIC="$UMR_ASIC" UMR_INSTANCE="$instance" {qscript} status >"$bc250_cu_status_file" 2>&1; then '
        + '  echo "Selected UMR_ASIC=$UMR_ASIC UMR_INSTANCE=$instance"; '
        + '  sed -n "1,120p" "$bc250_cu_status_file"; rm -f "$bc250_cu_status_file"; '
        + "else "
        + '  cat "$bc250_cu_status_file"; rm -f "$bc250_cu_status_file"; '
        + '  echo "ERROR: CU_UMR_REGISTER_ACCESS: UMR could not read the BC-250 banked WGP register through $UMR_ASIC."; '
        + "  exit 36; "
        + "fi"
    )
