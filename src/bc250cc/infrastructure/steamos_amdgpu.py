"""Typed decisions and safe shell generation for SteamOS AMDGPU support."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MODULE_MARKER = "installed, metrics and compute aware"
INSTALLED_MARKER = "[bc250-amdgpu] state: installed"
# ``patch-driver.sh status`` in the reviewed SteamOS toolkit uses
# ``not-installed`` for an absent override.  Older revisions and a few
# compatibility wrappers used ``missing`` instead.  Both mean that a
# boot-policy-only repair is unsafe: there is no verified module to retain.
ABSENT_MODULE_SUMMARY_STATES = frozenset({"missing", "not-installed"})
POLICY_ACTIVE_MARKER = "scheduler policy: configured and active (amdgpu.sched_policy=2)"
POLICY_REBOOT_MARKER = "scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)"
SUPPORTED_KERNEL_BASES = ("6.16", "6.18")
OC_TELEMETRY_MARKER_NAME = ".bc250-control-center-telemetry-oc-2400"


class AmdgpuDecision(StrEnum):
    READY = "ready"
    REPAIR_POLICY = "repair-policy"
    INSTALL = "install"
    PRIVILEGED_CHECK = "privileged-check"
    REBOOT_PENDING = "reboot-pending"
    KERNEL_STATUS_REQUIRED = "kernel-status-required"
    LIVE_STATUS_REQUIRED = "live-status-required"


@dataclass(frozen=True)
class AmdgpuCompatibilityState:
    decision: AmdgpuDecision
    module_verified: bool
    policy_verified: bool
    policy_active: bool
    runtime_policy_conflict: bool
    privileged: bool
    reboot_required_after_action: bool
    mutating_action: str


@dataclass(frozen=True)
class AmdgpuStatusEvidence:
    """Normalized, non-executable evidence emitted by the SteamOS toolkit.

    The upstream script is intentionally treated as an untrusted text
    producer here: callers first parse its report, then make a separate
    decision.  Keeping the two steps distinct prevents a success-looking
    summary line from promoting an ambiguous kernel or boot-policy state.
    """

    module_states: tuple[str, ...]
    summary_states: tuple[str, ...]
    module_verified: bool
    policy_active_reported: bool
    policy_reboot_reported: bool
    summary_conflict: bool
    policy_conflict: bool


def parse_amdgpu_status(
    output: str, *, running_release: str = ""
) -> AmdgpuStatusEvidence:
    """Parse the reviewed toolkit's status text without making a decision."""
    text = str(output or "")
    # A toolkit report is meaningful only for a named running kernel.  A
    # caller that has not independently read ``uname -r`` must not promote a
    # status line from an arbitrary older kernel to module evidence.
    release = str(running_release or "").strip()
    release_pattern = re.escape(release) if release else r"(?!)"
    module_line = re.compile(
        rf"^\[bc250-amdgpu\]\s+(?P<release>{release_pattern}):\s+(?P<status>[^\n]+)$",
        re.MULTILINE,
    )
    module_states = tuple(
        match.group("status").strip()
        for match in module_line.finditer(text)
        # ``state: installed`` is the upstream summary line, not a kernel
        # module assertion. It must never be treated as module evidence.
        if match.group("release") != "state"
    )
    summary_states = tuple(
        state.strip()
        for state in re.findall(
            r"^\[bc250-amdgpu\]\s+state:\s*([^\n]+)$", text, re.MULTILINE
        )
    )
    module_verified = bool(module_states) and all(
        state == MODULE_MARKER or state.startswith(f"{MODULE_MARKER} (")
        for state in module_states
    ) and not (set(summary_states) & ABSENT_MODULE_SUMMARY_STATES)
    policy_active_reported = bool(re.search(
        rf"^\[bc250-amdgpu\]\s+{re.escape(POLICY_ACTIVE_MARKER)}\s*$",
        text,
        re.MULTILINE,
    ))
    policy_reboot_reported = bool(re.search(
        rf"^\[bc250-amdgpu\]\s+{re.escape(POLICY_REBOOT_MARKER)}\s*$",
        text,
        re.MULTILINE,
    ))
    summary_values = set(summary_states)
    summary_conflict = len(summary_values) > 1
    # The reviewed status producer reports ``state: installed`` whenever the
    # kernel override and persistent policy are valid. That same summary is
    # therefore paired with either an active policy or a persisted policy that
    # needs a reboot. Missing or unknown summary text is not sufficient
    # evidence; a concatenated retry must not combine it with opposite policy
    # markers.
    policy_conflict = (
        (policy_active_reported and policy_reboot_reported)
        or summary_conflict
        or (policy_active_reported and summary_values != {"installed"})
        or (policy_reboot_reported and summary_values != {"installed"})
    )
    return AmdgpuStatusEvidence(
        module_states=module_states,
        summary_states=summary_states,
        module_verified=module_verified,
        policy_active_reported=policy_active_reported,
        policy_reboot_reported=policy_reboot_reported,
        summary_conflict=summary_conflict,
        policy_conflict=policy_conflict,
    )


def classify_amdgpu_status(
    output: str, *, privileged: bool, efi_readable: bool = True,
    running_release: str = "", running_cmdline: str | None = None,
) -> AmdgpuCompatibilityState:
    """Classify upstream status text without executing or interpolating it."""
    release_known = bool(str(running_release or "").strip())
    evidence = parse_amdgpu_status(output, running_release=running_release)
    # A status payload can be concatenated by a wrapper or contain a stale
    # retry. Never treat a single affirmative line as proof when another line
    # for the exact running kernel says something else: policy-only repair
    # must not run on an unverified module.
    module_verified = evidence.module_verified
    active_evidence = evidence.policy_active_reported
    reboot_evidence = evidence.policy_reboot_reported
    # Contradictory status is never promoted to ready.  ``state: installed``
    # is a summary emitted by upstream, not independent proof that persistent
    # policy and this boot agree.
    policy_conflict = evidence.policy_conflict
    cmdline_tokens = tuple(
        token for token in str(running_cmdline or "").split()
        if token.startswith("amdgpu.sched_policy=")
    )
    # A supplied command line is an independent, live observation.  Do not
    # promote an upstream status marker to READY when it disagrees with that
    # observation (for example a stale ``active`` report while the running
    # kernel has ``sched_policy=1``).  Require exactly one policy token so a
    # duplicate GRUB argument cannot be hidden behind a valid-looking ``=2``.
    cmdline_observed = running_cmdline is not None
    cmdline_policy_active = cmdline_tokens == ("amdgpu.sched_policy=2",)
    cmdline_policy_invalid = bool(cmdline_tokens) and not cmdline_policy_active
    runtime_policy_conflict = bool(
        cmdline_observed and (
            cmdline_policy_invalid
            or (active_evidence and not cmdline_policy_active)
            or (reboot_evidence and cmdline_policy_active)
        )
    )
    policy_conflict = policy_conflict or runtime_policy_conflict
    # The running command line can prove activation even when the toolkit has
    # not established persistence.  READY still additionally requires the
    # persistent toolkit marker below; this distinction lets Health report a
    # live `=2` honestly while asking for a privileged persistence check.
    policy_active = (
        cmdline_observed
        and (active_evidence or cmdline_policy_active)
        and not policy_conflict
    )
    policy_reboot_pending = reboot_evidence and not policy_conflict
    persistent_policy_verified = (active_evidence or reboot_evidence) and not policy_conflict
    policy_verified = persistent_policy_verified
    if not release_known:
        decision, action, reboot = (
            AmdgpuDecision.KERNEL_STATUS_REQUIRED,
            "kernel-status",
            False,
        )
    elif module_verified and not cmdline_observed:
        decision, action, reboot = (
            AmdgpuDecision.LIVE_STATUS_REQUIRED,
            "live-cmdline-status",
            False,
        )
    elif module_verified and policy_active and persistent_policy_verified:
        decision, action, reboot = AmdgpuDecision.READY, "none", False
    elif module_verified and policy_reboot_pending:
        decision, action, reboot = AmdgpuDecision.REBOOT_PENDING, "none", True
    elif module_verified and not privileged and not efi_readable:
        decision, action, reboot = (
            AmdgpuDecision.PRIVILEGED_CHECK,
            "privileged-status",
            False,
        )
    elif module_verified:
        decision, action, reboot = (
            AmdgpuDecision.REPAIR_POLICY,
            "boot-policy-only",
            True,
        )
    else:
        decision, action, reboot = (
            AmdgpuDecision.INSTALL,
            "module-and-boot-policy",
            True,
        )
    return AmdgpuCompatibilityState(
        decision,
        module_verified,
        policy_verified,
        policy_active,
        runtime_policy_conflict,
        bool(privileged),
        reboot,
        action,
    )


def _join(commands: list[str]) -> str:
    return "; ".join(command.strip().rstrip(";") for command in commands if command.strip())


def _module_verified_guard(status_file: str) -> str:
    """Shell predicate matching the conservative Python module contract.

    It deliberately evaluates every matching line for the running kernel, so
    a mixed status report cannot select a boot-policy-only repair.
    """
    marker = shlex.quote(MODULE_MARKER)
    return (
        "awk -v release=\"$running_release\" -v marker=" + marker + " "
        "'BEGIN { prefix=\"[bc250-amdgpu] \" release \": \"; state_prefix=\"[bc250-amdgpu] state: \"; seen=0; bad=0 } "
        'index($0, prefix) == 1 { seen=1; value=substr($0, length(prefix)+1); '
        'if (value != marker && index(value, marker " (") != 1) bad=1 } '
        'index($0, state_prefix) == 1 { value=substr($0, length(state_prefix)+1); '
        'if (value == "missing" || value == "not-installed") bad=1 } '
        "END { exit !(seen && !bad) }' " + status_file
    )


def _policy_active_guard(status_file: str) -> str:
    """Match active-policy evidence and reject conflicting summary lines."""
    marker = shlex.quote(POLICY_ACTIVE_MARKER.removeprefix("scheduler policy: "))
    reboot = shlex.quote(POLICY_REBOOT_MARKER.removeprefix("scheduler policy: "))
    return (
        "awk -v active=" + marker + " -v reboot=" + reboot + " "
        "'BEGIN { prefix=\"[bc250-amdgpu] scheduler policy: \"; state_prefix=\"[bc250-amdgpu] state: \"; "
        "seen_active=0; seen_reboot=0; summary_bad=0; summary_seen=\"\"; conflict=0 } "
        'index($0, prefix) == 1 { value=substr($0, length(prefix)+1); if (value == active) seen_active=1; if (value == reboot) seen_reboot=1 } '
        'index($0, state_prefix) == 1 { value=substr($0, length(state_prefix)+1); if (summary_seen != "" && summary_seen != value) conflict=1; summary_seen=value; if (value != "installed") summary_bad=1 } '
        "END { exit !(seen_active && !seen_reboot && summary_seen == \"installed\" && !summary_bad && !conflict) }' " + status_file
    )


def _policy_reboot_guard(status_file: str) -> str:
    """Match persisted-but-not-active policy evidence without mixed summaries."""
    marker = shlex.quote(POLICY_ACTIVE_MARKER.removeprefix("scheduler policy: "))
    reboot = shlex.quote(POLICY_REBOOT_MARKER.removeprefix("scheduler policy: "))
    return (
        "awk -v active=" + marker + " -v reboot=" + reboot + " "
        "'BEGIN { prefix=\"[bc250-amdgpu] scheduler policy: \"; state_prefix=\"[bc250-amdgpu] state: \"; "
        "seen_active=0; seen_reboot=0; summary_bad=0; summary_seen=\"\"; conflict=0 } "
        'index($0, prefix) == 1 { value=substr($0, length(prefix)+1); if (value == active) seen_active=1; if (value == reboot) seen_reboot=1 } '
        'index($0, state_prefix) == 1 { value=substr($0, length(state_prefix)+1); if (summary_seen != "" && summary_seen != value) conflict=1; summary_seen=value; if (value != "installed") summary_bad=1 } '
        "END { exit !(seen_reboot && !seen_active && summary_seen == \"installed\" && !summary_bad && !conflict) }' " + status_file
    )


def _runtime_policy_active_guard(cmdline_file: str) -> str:
    """Require the live kernel to have exactly one scheduler-policy token.

    The toolkit's status report is persistent-policy evidence.  A fresh
    `/proc/cmdline` read is separate evidence for *this boot*, and should not
    be silently overridden by a stale or concatenated status payload.
    """
    return (
        "awk 'BEGIN { seen=0; bad=0 } "
        "{ for (i=1; i<=NF; i++) if (index($i, \"amdgpu.sched_policy=\") == 1) "
        "{ seen++; if ($i != \"amdgpu.sched_policy=2\") bad=1 } } "
        "END { exit !(seen == 1 && !bad) }' " + cmdline_file
    )


def _runtime_policy_not_active_guard(cmdline_file: str) -> str:
    """Accept reboot-pending evidence only when this boot is not exactly `=2`."""
    return "! " + _runtime_policy_active_guard(cmdline_file)


def _policy_runtime_coherent_guard(status_file: str, cmdline_file: str) -> str:
    """Pair persistent status with the independently observed live boot."""
    active = _policy_active_guard(status_file)
    reboot = _policy_reboot_guard(status_file)
    runtime_active = _runtime_policy_active_guard(cmdline_file)
    runtime_not_active = _runtime_policy_not_active_guard(cmdline_file)
    return f'{{ {{ {active} && {runtime_active}; }} || {{ {reboot} && {runtime_not_active}; }}; }}'


def build_steamos_amdgpu_diagnostic_command(
    *, script: Path, cmdline_path: Path = Path("/proc/cmdline"), backend_guard: str = ""
) -> str:
    """Build a read-only privileged status probe with explicit reboot semantics."""
    qscript = shlex.quote(str(script))
    qcmdline = shlex.quote(str(cmdline_path))
    backend_ready = str(backend_guard or f"test -f {qscript}").strip()
    module_verified_only = _module_verified_guard('"$amdgpu_status_file"')
    policy_active_only = _policy_active_guard('"$amdgpu_status_file"')
    policy_reboot_only = _policy_reboot_guard('"$amdgpu_status_file"')
    runtime_active_only = _runtime_policy_active_guard(qcmdline)
    runtime_not_active = _runtime_policy_not_active_guard(qcmdline)
    return _join([
        'echo "== AMDGPU backend validation =="',
        'running_release="$(uname -r)"',
        f'{backend_ready} || {{ echo "ERROR: protected SteamOS AMDGPU backend is unavailable or untrusted; use Prepare SteamOS compatibility from Desktop Mode."; exit 39; }}',
        f'test -r {qcmdline} || {{ echo "ERROR: the live kernel command line is not readable"; exit 39; }}',
        'amdgpu_status_file="$(mktemp "${XDG_RUNTIME_DIR:-/tmp}/bc250-amdgpu-diagnostic.XXXXXX")"',
        'chmod 0600 "$amdgpu_status_file"',
        "trap 'rm -f -- \"$amdgpu_status_file\"' EXIT",
        f'sudo /usr/bin/bash {qscript} status >"$amdgpu_status_file" 2>&1 || true',
        'cat "$amdgpu_status_file"',
        f'{module_verified_only} || '
        '{ echo "ERROR: the reviewed AMDGPU override is not verified for the running kernel"; exit 39; }',
        f'if {policy_active_only} && {runtime_active_only}; then '
        'echo "[OK] AMDGPU module and scheduler policy are active for this boot."; '
        f'elif {policy_reboot_only} && {runtime_not_active}; then '
        'echo "[WARN] AMDGPU module and persistent scheduler policy are verified; reboot is pending to activate amdgpu.sched_policy=2."; '
        'else echo "ERROR: the AMDGPU module is verified, but scheduler policy persistence is incomplete"; exit 39; fi',
        'rm -f -- "$amdgpu_status_file"',
        'trap - EXIT',
    ])


def build_steamos_compatibility_command(
    *,
    script: Path,
    boot_config: Path,
    checkout_command: str,
    install: bool,
    telemetry_oc_overlay_command: str = "",
    module_install_command: str = "",
    cmdline_path: Path = Path("/proc/cmdline"),
    module_root: Path = Path("/usr/lib/modules"),
    backend_guard: str = "",
) -> str:
    """Build the audited decision workflow; generated code performs no action here."""
    qscript = shlex.quote(str(script))
    qboot = shlex.quote(str(boot_config))
    qcmdline = shlex.quote(str(cmdline_path))
    qmodule_root = shlex.quote(str(module_root))
    backend_ready = str(backend_guard or f"test -f {qscript} && test -f {qboot}").strip()
    overlay = str(telemetry_oc_overlay_command or "").strip().rstrip(";")
    install_module_command = str(module_install_command or "").strip().rstrip(";")
    if not install_module_command:
        install_module_command = "; ".join(part for part in (
            overlay,
            "export BC250_CONTROL_CENTER_OC_TELEMETRY=1",
            f"/usr/bin/bash {qscript}",
        ) if part)
    module_verified_only = _module_verified_guard('"$status_file"')
    policy_active_only = _policy_active_guard('"$status_file"')
    policy_reboot_only = _policy_reboot_guard('"$status_file"')
    runtime_active_only = _runtime_policy_active_guard(qcmdline)
    runtime_not_active = _runtime_policy_not_active_guard(qcmdline)
    policy_runtime_coherent = _policy_runtime_coherent_guard('"$status_file"', qcmdline)
    oc_marker = f'{qmodule_root}/$running_release/updates/{OC_TELEMETRY_MARKER_NAME}'
    # The marker contains the SHA-256 of the exact override installed by this
    # application. A stale marker after rollback cannot validate another module.
    oc_telemetry_guard = (
        f'oc_marker={oc_marker}; '
        'oc_module="$(modinfo -k "$running_release" -F filename amdgpu 2>/dev/null || true)"; '
        '[ -f "$oc_marker" ] && [ ! -L "$oc_marker" ] && '
        '[ -f "$oc_module" ] && [ ! -L "$oc_module" ] && '
        'oc_expected="$(tr -d "\\n" < "$oc_marker")" && '
        'oc_actual="$(sha256sum "$oc_module" | awk \'{print $1}\')" && '
        '[ "$oc_expected" = "$oc_actual" ]'
    )
    oc_marker_write_command = (
        f'oc_marker={oc_marker}; '
        'oc_module="$(modinfo -k "$running_release" -F filename amdgpu 2>/dev/null || true)"; '
        '[ -f "$oc_module" ] && [ ! -L "$oc_module" ] || '
        '{ echo "ERROR: patched AMDGPU module is not a safe regular file for telemetry attestation."; exit 38; }; '
        'sudo install -d -m 0755 "$(dirname "$oc_marker")"; '
        'sha256sum "$oc_module" | awk \'{print $1}\' | sudo tee "$oc_marker" >/dev/null; '
        'sudo chmod 0644 "$oc_marker"; '
        'echo "[OK] BC250 high-OC telemetry attestation installed."'
    )
    # Unit-level callers that do not request the Control Center overlay retain
    # the generic upstream decision contract. The application always supplies
    # the overlay for the explicit SteamOS compatibility action.
    oc_telemetry_verified = oc_telemetry_guard if overlay else 'true'
    oc_marker_write = oc_marker_write_command if overlay else ':'
    commands = [
        'echo "== SteamOS compatibility: source validation =="',
        'echo "[INFO] Scope: patched AMDGPU telemetry/compute support and scheduler boot policy."',
        'echo "[INFO] This workflow does not install the optional Mesa/RADV performance patch."',
        checkout_command,
        f'{backend_ready} || {{ echo "ERROR: protected SteamOS AMDGPU backend is unavailable or untrusted; use Prepare SteamOS compatibility from Desktop Mode."; exit 38; }}',
        f'test -r {qcmdline} || {{ echo "ERROR: the live kernel command line is not readable"; exit 38; }}',
        'status_file="$(mktemp "${XDG_RUNTIME_DIR:-/tmp}/bc250-amdgpu-status.XXXXXX")"',
        'chmod 0600 "$status_file"',
        "trap 'rm -f -- \"$status_file\"' EXIT",
    ]
    if not install:
        commands.append(
            'echo "== SteamOS compatibility: read-only preflight =="; '
            'echo "[INFO] No system setting will be changed by this check."; '
            'running_release="$(uname -r)"; printf "Kernel: %s\\n" "$running_release"; '
            f'/usr/bin/bash {qscript} status >"$status_file" 2>&1 || true; '
            f'if {module_verified_only} && {policy_active_only} && {runtime_active_only} && {{ {oc_telemetry_verified}; }}; then '
            'cat "$status_file"; echo "== Decision =="; echo "READY: module and scheduler policy are installed for the running kernel."; '
            f'elif {module_verified_only} && {policy_reboot_only} && {runtime_not_active} && {{ {oc_telemetry_verified}; }}; then '
            'cat "$status_file"; echo "== Decision =="; echo "REBOOT PENDING: module and persistent scheduler policy are verified; reboot to activate amdgpu.sched_policy=2."; '
            f'elif {module_verified_only} && {{ {oc_telemetry_verified}; }}; then cat "$status_file"; '
            'if [ ! -r /efi/EFI/steamos/grub.cfg ]; then echo "== Decision =="; echo "PRIVILEGED CHECK REQUIRED: the AMDGPU module is verified, but EFI policy is root-readable."; '
            'echo "[INFO] Use Prepare SteamOS compatibility to validate or repair it without rebuilding amdgpu."; '
            'else echo "== Decision =="; echo "REPAIR AVAILABLE: the AMDGPU module is verified, but the scheduler boot policy is incomplete."; '
            'echo "[INFO] Use Prepare SteamOS compatibility; Control Center will repair the boot policy without rebuilding amdgpu."; fi; '
            'else cat "$status_file" 2>/dev/null || true; echo "== Decision =="; echo "INSTALL AVAILABLE: compatibility is not installed for this running kernel."; '
            'echo "[INFO] Use the explicit Prepare SteamOS compatibility action when you are ready to modify amdgpu/initramfs and reboot."; fi'
        )
    else:
        kernel_patterns = "|".join(f"{base}.*" for base in SUPPORTED_KERNEL_BASES)
        commands.extend(
            [
                'echo "== SteamOS compatibility: privileged preflight =="',
                'running_release="$(uname -r)"',
                'printf "Kernel: %s\\n" "$running_release"',
                f'case "$running_release" in {kernel_patterns}) ;; *) echo "ERROR: the reviewed SteamOS kernel backend supports SteamOS 3.8/3.9 kernel bases 6.16 or 6.18; running: $running_release"; exit 38 ;; esac',
                'lspci -Dnnd 1002:13fe 2>/dev/null | grep -q . || { echo "ERROR: AMD BC-250 PCI device 1002:13fe was not detected"; exit 38; }',
                'echo "Hardware: AMD BC-250 [1002:13fe] detected"',
                (
                'running_release="$(uname -r)"; '
                f'sudo /usr/bin/bash {qscript} status >"$status_file" 2>&1 || true; '
                f'if {module_verified_only} && {policy_active_only} && {runtime_active_only} && {{ {oc_telemetry_verified}; }}; then '
                'cat "$status_file"; echo "== Decision =="; echo "READY: no changes are necessary."; '
                'echo "== Result =="; echo "[OK] SteamOS compatibility is active for the running kernel."; '
                f'elif {module_verified_only} && {policy_reboot_only} && {runtime_not_active} && {{ {oc_telemetry_verified}; }}; then '
                'cat "$status_file"; echo "== Decision =="; echo "REBOOT PENDING: no additional changes are necessary."; '
                'BC250_REBOOT_REQUIRED=1; echo "== Result =="; echo "[OK] Module and persistent boot policy are verified. REBOOT REQUIRED to activate amdgpu.sched_policy=2."; '
                f'elif {module_verified_only} && {{ {oc_telemetry_verified}; }}; then cat "$status_file"; '
                'echo "== Decision =="; echo "REPAIR POLICY ONLY: repairing only the SteamOS scheduler boot policy; the kernel module will not be rebuilt."; '
                'echo "== Action =="; echo "Installing and validating amdgpu.sched_policy=2..."; '
                f'sudo /usr/bin/bash {qboot} install; sudo /usr/bin/bash {qboot} configured || '
                '{ echo "ERROR: SteamOS scheduler boot-policy repair did not validate."; exit 38; }; '
                f'sudo /usr/bin/bash {qscript} status >"$status_file" 2>&1 || true; cat "$status_file"; '
                f'{module_verified_only} && {policy_runtime_coherent} || '
                '{ echo "ERROR: SteamOS scheduler boot-policy repair did not produce verified final toolkit evidence."; exit 38; }; '
                'BC250_REBOOT_REQUIRED=1; echo "== Result =="; echo "[OK] SteamOS scheduler boot policy repaired. REBOOT REQUIRED to activate amdgpu.sched_policy=2."; '
                'else cat "$status_file" 2>/dev/null || true; echo "== Decision =="; echo "INSTALL MODULE AND POLICY: compatibility is absent for this kernel."; '
                'echo "== Action =="; echo "Building and installing the validated SteamOS fixes..."; '
                'echo "[INFO] This changes amdgpu/initramfs and requires a reboot. If exact headers are unavailable, upstream may need a long build and about 40 GiB of temporary space."; '
                f'{install_module_command}; {oc_marker_write}; sudo /usr/bin/bash {qboot} install; sudo /usr/bin/bash {qboot} configured || '
                '{ echo "ERROR: SteamOS scheduler boot policy was not persisted after installation."; exit 38; }; '
                f'sudo /usr/bin/bash {qscript} status >"$status_file" 2>&1 || true; cat "$status_file"; '
                f'{module_verified_only} && {policy_runtime_coherent} && {{ {oc_telemetry_verified}; }} || '
                '{ echo "ERROR: SteamOS fixes did not validate after installation."; exit 38; }; '
                'BC250_REBOOT_REQUIRED=1; echo "== Result =="; echo "[OK] Module and boot policy verified. REBOOT REQUIRED to load the patched AMDGPU module."; fi'
                ),
            ]
        )
    commands.extend(['rm -f -- "$status_file"', "trap - EXIT"])
    return _join(commands)
