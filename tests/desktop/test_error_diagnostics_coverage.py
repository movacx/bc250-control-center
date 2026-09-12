"""Diagnostic coverage, measured instead of assumed.

Two independent checks:

* **The corpus.** Every ``raise SomeError("...")`` in the source tree is read on
  each run — not from a fixture — and pushed through ``diagnose_error``. A new
  failure with no matching rule shows up here instead of reaching a user as
  ``BC250-GENERAL-001``. ``MINIMUM_COVERAGE`` is a ratchet: raise it when rules
  are added, never lower it to make a red run green.

* **The evidence.** Many rules exist for text this repository never raises —
  systemd, the package manager, the kernel, or one of the upstream BC-250
  projects. Those rules are proven against the literal strings their upstream
  emits, recorded in ``EVIDENCE`` with the source they came from. A rule whose
  evidence resolves to a different code is shadowed, which the same test
  catches.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from frontends.desktop.core.error_diagnostics import _RULES, diagnose_error

ROOTS = ("src", "frontends")
MINIMUM_MESSAGE_LENGTH = 15
GENERIC_CODES = frozenset({"BC250-GENERAL-001"})

# Ratchet. Current specific coverage of the raise corpus.
MINIMUM_COVERAGE = 0.72


# Literal text each rule must recognise, with where it comes from. Strings taken
# from an upstream project are quoted as that project emits or documents them.
EVIDENCE: dict[str, tuple[str, ...]] = {
    # -- kernel module / fan stack (upstream: Fred78290/nct6687d) -------------
    "BC250-FAN-001": (
        "ACPI: OSL: Resource conflict; ACPI support missing from driver?",
        "Failed to insert module 'nct6687': No such device",
        "EC base I/O port unconfigured",
    ),
    # -- authorization (upstream: polkit) ------------------------------------
    "BC250-AUTH-001": (
        "polkit-agent-helper-1: no textual authentication agent available",
    ),
    "BC250-AUTH-002": (
        "Error executing command as another user: Not authorized",
        "Authentication failed",
    ),
    "BC250-AUTH-003": (
        "pkexec: command not found",
    ),
    # -- filesystem and privilege (upstream: the kernel) ---------------------
    "BC250-PERM-001": (
        "Permission denied",
        "Read-only file system",
    ),
    # -- service manager (upstream: systemd) ---------------------------------
    "BC250-SERVICE-001": (
        "Unit cyan-skillfish-governor-smu.service is masked.",
    ),
    "BC250-SERVICE-002": (
        "Failed to restart cyan-skillfish-governor-smu.service: Unit not found.",
    ),
    "BC250-SERVICE-003": (
        "Job for cyan-skillfish-governor-smu.service failed because the control process exited",
    ),
    # -- package managers (upstream: pacman, dnf, apt, rpm-ostree) -----------
    "BC250-PKG-001": (
        "could not lock database: File exists",
        "Could not get lock /var/lib/dpkg/lock-frontend",
    ),
    "BC250-PKG-002": (
        "signature from ... is unknown trust",
        "GPG check FAILED",
    ),
    "BC250-PKG-003": (
        "repository bc250-cachyos is already configured",
    ),
    "BC250-UPSTREAM-404": (
        "error: failed retrieving file from repo: HTTP 404",
    ),
    "BC250-NET-001": (
        "Could not resolve host: github.com",
        "curl: (28) Operation timed out",
    ),
    "BC250-STORAGE-001": (
        "No space left on device",
    ),
    "BC250-IMMUTABLE-001": (
        "rpm-ostree: A pending deployment is already staged",
    ),
    # -- kernel / driver ABI (upstream: bc250-steamos, bc250-gfx1013-fix) ----
    "BC250-KERNEL-001": (
        "amdgpu: version magic does not match this kernel",
        "kernel headers for 7.2.0-ogc4.1 were not found",
    ),
    # -- hardware gating (upstream: bc250-cu-live-manager, bc250-fsr4) -------
    "BC250-HW-001": (
        "No device with PCI ID 1002:13FE was detected",
    ),
    # -- governor collisions (upstream: bc250-toolkit ownership overlap) -----
    "BC250-GPU-002": (
        "both cyan-skillfish-governor-smu and oberon-governor are active",
    ),
    # -- generated shell workflows -------------------------------------------
    "BC250-CMD-001": (
        "umr: command not found",
    ),
    "BC250-DATA-001": (
        "the configuration already exists and will not be overwritten automatically",
    ),
    "BC250-TERMINAL-001": (
        "no supported graphical terminal was found",
    ),
    "BC250-TIMEOUT-001": (
        "Timed out waiting for the governor to publish its allowed range",
        "exit status 124",
    ),
    "BC250-BUSY-001": (
        "Device or resource busy",
    ),
    "BC250-HELPER-001": (
        "the protected helper is missing",
    ),
    "BC250-PROTOCOL-001": (
        "helper protocol version mismatch",
    ),
    "BC250-DBUS-001": (
        "org.freedesktop.DBus.Error.ServiceUnknown: com.cyanskillfish.Governor",
        # "Cyan rejected the requested compatibility settings" is only the
        # wrapper the repository puts around the real cause, which is this.
        "The governor restarted, but its previous runtime range could not be "
        "restored safely. D-Bus range objects did not become ready.",
    ),
    # -- telemetry after the core unlock (upstream: bc250-core-unlock,
    #    bc250-steamos-real-toolkit, linux-cachyos-bc250 all describe it) -----
    "BC250-GPU-003": (
        "pp_dpm_sclk and hwmon freq1_input report nonsense",
        "add amdgpu.cs_legacy_8core_metrics=1 to the kernel command line",
    ),
    # -- distribution gating --------------------------------------------------
    "BC250-PLATFORM-001": (
        "SteamOS toolkit diagnostics are available only on SteamOS.",
        "Runtime integration inventory requires a headless host",
    ),
    # -- recovery snapshots ---------------------------------------------------
    "BC250-RECOVERY-001": (
        "Recovery snapshot does not exist",
    ),
    # -- the driver refused what the governor accepted (upstream: cyan
    #    D-Bus /Range/Allowed, amdgpu OD_RANGE) -------------------------------
    "BC250-GPU-004": (
        "Cyan restarted but D-Bus did not expose the requested 1850-2150 MHz high safe-point range",
    ),
    # -- two BC-250 toolkits owning the same piece (upstream: bc250-toolkit
    #    uses Limine and the mendesrr ACPI lineage; BC250-Telemetry binds nct6683)
    "BC250-COLLISION-001": (
        "Must be using Limine boot loader for all functions in the script to work",
        "nct6683 was bound instead of the expected driver",
    ),
    # -- Cyan's patched-sensor bind mount, from a real failing service start.
    #    The log is full of generic words, so without its own rule it lands on
    #    whatever broad pattern comes first — it once reported Compute Units.
    "BC250-GPU-005": (
        'mount --bind /dev/shm/patched_gpu_metrics /sys/bus/pci/devices/0000:01:00.0/gpu_metrics failed: exit status: 32',
        "mount: /sys/devices/pci0000:00/0000:00:08.1/0000:01:00.0/gpu_metrics: move_mount() failed: No such file or directory.",
        'mount --bind /dev/shm/patched_freq_metrics /sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon1/freq1_input failed: signal: 15 (SIGTERM)',
        "ERROR: fix-metrics is enabled, and an earlier run of this boot already "
        "failed to place its patched gpu_metrics file. A left-over mount on that "
        "path blocks the next start.",
    ),
    # -- this kernel cannot host Cyan's metrics fix, straight from the
    #    startup guard in gpu_repository and from Cyan's own rejection ---------
    # Two situations that used to share one message, and must not again: a
    # kernel that never exposes gpu_metrics, versus a mount a previous run
    # left behind. The remedy is different, so the diagnosis has to be too.
    "BC250-GPU-006": (
        "ERROR: fix-metrics is enabled, but this kernel does not expose the gpu_metrics file Cyan needs.",
        "fix-metrics was requested, but the active BC-250 kernel/runtime is known not to support Cyan's gpu_metrics overlay.",
    ),
    # -- the application's own invariants ------------------------------------
    "BC250-INTERNAL-001": (
        "GPU profile key cannot be empty",
        "Unsupported governor service action:",
    ),
}


def _raised_messages() -> tuple[tuple[str, str], ...]:
    """Every ``raise SomeError("...")`` message literal in the source tree."""
    found: list[tuple[str, str]] = []
    for root in ROOTS:
        for path in sorted(pathlib.Path(root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                if not node.exc.args:
                    continue
                argument = node.exc.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    parts = [argument.value]
                elif isinstance(argument, ast.JoinedStr):
                    parts = [
                        value.value
                        for value in argument.values
                        if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    ]
                else:
                    continue
                text = " ".join(parts).strip()
                if len(text) >= MINIMUM_MESSAGE_LENGTH:
                    found.append((str(path), text))
    return tuple(found)


CORPUS = _raised_messages()


def test_the_corpus_is_actually_being_collected():
    """Guards against a silent zero-message corpus making everything below pass."""
    assert len(CORPUS) > 400, len(CORPUS)


def test_specific_diagnostic_coverage_meets_the_ratchet():
    specific = sum(
        1
        for path, text in CORPUS
        if (code := diagnose_error(text, context=path).code) not in GENERIC_CODES
        and not code.endswith("-900")
    )
    coverage = specific / len(CORPUS)
    assert coverage >= MINIMUM_COVERAGE, (
        f"specific diagnostic coverage fell to {coverage:.1%} "
        f"({specific}/{len(CORPUS)}); the ratchet is {MINIMUM_COVERAGE:.0%}"
    )


def test_no_message_is_left_without_a_usable_diagnosis():
    for path, text in CORPUS:
        diagnosis = diagnose_error(text, context=path)
        assert re.fullmatch(r"BC250-[A-Z]+-\d{3}", diagnosis.code), (path, text, diagnosis.code)
        assert diagnosis.summary and diagnosis.cause and diagnosis.action, (path, text)


@pytest.mark.parametrize("code, samples", sorted(EVIDENCE.items()))
def test_recorded_evidence_resolves_to_its_own_rule(code, samples):
    """Each sample must reach exactly the rule it documents, not an earlier one."""
    for sample in samples:
        assert diagnose_error(sample).code == code, (code, sample, diagnose_error(sample).code)


def test_evidence_exists_for_every_rule_that_has_it_recorded():
    """The map may lag the rule list, but it must never name a rule that is gone."""
    known = {rule.code for rule in _RULES}
    assert set(EVIDENCE) <= known, set(EVIDENCE) - known


def test_the_message_outranks_the_context_it_arrived_with():
    """A GPU failure must never be reported as a Compute Units problem.

    The context is the workflow the user was running. It used to be appended to
    the message and matched as one string, so a rule whose pattern only
    appeared in the context could beat every rule reading the message.
    """
    gpu_failures = (
        "ERROR: fix-metrics is enabled, but this kernel/runtime cannot provide "
        "Cyan gpu_metrics safely. Nothing was changed.",
        'Error: Io(Custom { kind: Other, error: "mount --bind '
        "/dev/shm/patched_gpu_metrics /sys/bus/pci/devices/0000:01:00.0/gpu_metrics "
        'failed: exit status: 32" })',
    )
    for message in gpu_failures:
        for context in ("", "gpu", "compute units", "compute unit topology"):
            code = diagnose_error(message, context=context).code
            assert code.startswith("BC250-GPU-"), (message[:40], context, code)


def test_context_still_decides_when_the_message_says_nothing():
    """It is only outranked, not ignored."""
    vague = "the operation returned a non-zero status"
    # The context routes it to the right module — to a specific rule when one
    # matches, otherwise to that module's fallback. Either is correct; landing
    # in the wrong module is not.
    assert diagnose_error(vague, context="fan pwm").code.startswith("BC250-FAN-")
    assert diagnose_error(vague, context="compute units").code.startswith("BC250-CU-")
    assert diagnose_error(vague).code == "BC250-GENERAL-001"
