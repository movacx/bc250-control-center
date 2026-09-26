"""Single source of truth for user-facing failure identity.

Every surface (Desktop, CLI, Quick Access and the privileged helpers) resolves
failures through this module so one underlying fault always reports the same
stable ``BC250-<AREA>-<NNN>`` identifier, cause and next step.

Three vocabularies existed before this module and disagreed with each other:
the regex rules in the desktop layer, a ``BC250-TERM-<status>`` string built
inside the generated shell script, and a separate TypeScript reimplementation
in the Quick Access panel. A fourth problem was mechanical: helpers exit with
codes 10-57 that no table explained, so the interface printed the bare number.

Text lives here as English source strings because ``tr()`` keys are the English
strings themselves. Keep the wording bounded and reusable; every new sentence
costs 30 translations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorCode:
    """One diagnosable failure with a stable identifier and a next step."""

    code: str
    summary: str
    cause: str
    action: str
    # Process exit statuses that mean exactly this failure. Used to translate a
    # helper's numeric status instead of printing it raw.
    exit_statuses: tuple[int, ...] = ()
    # ``PREFIX:`` markers helpers already print on stderr.
    markers: tuple[str, ...] = ()
    retryable: bool = False


# Reserved: the terminal wrapper previously emitted BC250-TERM-<status> for any
# status, including ones no table explained. Statuses now resolve through
# ``for_exit_status`` and fall back to BC250-GENERAL-001 rather than minting an
# identifier that nothing can look up.

# Every entry reuses wording that already exists in the desktop diagnostic
# rules, so all 30 locales already translate it. Adding a status or marker
# here costs no new translation work; inventing new sentences would.
_CODES: tuple[ErrorCode, ...] = (
    ErrorCode(
        "BC250-CMD-001",
        "A required program or generated command is missing.",
        "Dependencies were not prepared, a toolkit was removed, or the active distribution provides the program under a different package or path.",
        "Return to the Dashboard and prepare the affected module. If it was already prepared, run System Health to find the missing path.",
        exit_statuses=(31, 47, 48, 127),
        markers=(),
    ),
    ErrorCode(
        "BC250-TERMINAL-001",
        "The required terminal workflow could not be started.",
        "No supported graphical terminal was found, its launcher rejected the command, or a required executable is absent.",
        "Install a supported terminal or run the private script path shown in the technical detail from your existing terminal.",
        exit_statuses=(126,),
        markers=(),
    ),
    ErrorCode(
        "BC250-TIMEOUT-001",
        "The operation did not finish within its safety limit.",
        "A service, hardware read-back, package download, or external toolkit stopped responding or needed longer than expected.",
        "Check whether the terminal or service is still active, then review its log. Retry only after the previous process has ended.",
        exit_statuses=(124, 125),
        markers=('QUICK_ACCESS_TIMEOUT',),
    ),
    ErrorCode(
        "BC250-DATA-001",
        "The workflow rejected an existing or inconsistent configuration.",
        "A repository, toolkit file, package source, or saved value already exists in a form the workflow will not overwrite automatically.",
        "Read the ERROR line immediately above the exit code, correct the named configuration, and run the workflow again.",
        exit_statuses=(65,),
        markers=(),
    ),
    ErrorCode(
        "BC250-PERM-001",
        "Linux refused access to a required file or device.",
        "A helper, device node, configuration file, or immutable system path has ownership or permission settings that do not allow this operation.",
        "Use System Health to verify permissions and helpers. On Bazzite or SteamOS, finish any pending deployment and restart before retrying.",
        exit_statuses=(11, 13, 14, 15, 16, 17, 71, 77),
        markers=("QUICK_ACCESS_PRIVILEGE",),
    ),
    ErrorCode(
        "BC250-SERVICE-003",
        "The service manager could not complete the requested change.",
        "The service configuration is invalid, its executable is missing, or the selected init system does not match the installed service files.",
        "Open the service status and read the first reported error. Repair the module from the Dashboard before enabling it again.",
        exit_statuses=(69,),
        markers=('QUICK_ACCESS_GPU_SERVICE', 'QUICK_ACCESS_GPU_CONFLICT'),
    ),
    ErrorCode(
        "BC250-VRAM-001",
        "The VRAM size could not be changed.",
        "The size is not one of the offered presets, the firmware memory layout was not recognised, or the CMOS ports could not be reached.",
        "Choose one of the offered sizes. If it repeats, apply it from BC250 Control Center Desktop, which checks the firmware layout first.",
        markers=('QUICK_ACCESS_VRAM',),
    ),
    ErrorCode(
        "BC250-STORAGE-001",
        "There is not enough writable storage.",
        "The target filesystem, temporary directory, boot partition, or user quota is full.",
        "Free space on the filesystem named in the technical detail, then retry. Kernel installs also require free space in /boot.",
        exit_statuses=(73, 74),
        markers=(),
    ),
    ErrorCode(
        "BC250-BUSY-001",
        "Another operation is still using this component.",
        "A previous BC250 action, package manager, service restart, or external toolkit still holds the required lock.",
        "Wait for the current terminal or progress indicator to finish, refresh the page, and retry once. Close other BC250 toolkits if the lock remains.",
        exit_statuses=(75,),
        markers=(),
    ),
    ErrorCode(
        "BC250-CONFIG-001",
        "A configuration file is invalid or incomplete.",
        "A manual edit, older toolkit, interrupted write, or unsupported option left syntax or values the current component cannot read.",
        "Open the named file from the application, correct the first reported line or restore the module defaults, then apply the settings again.",
        exit_statuses=(78,),
        markers=('QUICK_ACCESS_GPU_CONFIG',),
    ),
    ErrorCode(
        "BC250-PROTOCOL-001",
        "The interface and protected helper are different versions.",
        "An older Desktop or Decky component is still running after an update, or only part of the application was replaced.",
        "Reinstall the current build and restart the application. Restart Decky Loader too when the Quick Access panel is affected.",
        exit_statuses=(2, 3, 28, 29, 32, 33, 36, 49, 70, 90),
        markers=(
            'Missing action.', 'Unknown action.', 'expects:',
            'does not accept arguments', 'accepts only', 'HELPER_USAGE',
            'QUICK_ACCESS_CU_SERVICE:', 'QUICK_ACCESS_CPU_SERVICE:',
            # A fresh Decky build talking to a stale installed helper (or the
            # reverse) after only one side of an update was applied. This is
            # a routine, expected state right after replacing the helper --
            # not a hardware fault -- so it must resolve to this calm,
            # actionable code instead of the generic unknown-failure one.
            'are different versions.', 'disagrees with this system about',
            'was built for contract revision', 'protocol is incompatible',
            'shared contract is not installed',
            'shared contract is not a protected root-owned file',
            'shared contract could not be read',
        ),
    ),
    ErrorCode(
        "BC250-DBUS-001",
        "The GPU governor did not expose its D-Bus controls.",
        "Cyan is stopped, still starting, using an incompatible configuration, or another governor owns the GPU control path.",
        "Check the governor service status, resolve any Cyan/Oberon conflict, start the selected service, and wait a few seconds before refreshing.",
        exit_statuses=(22,),
        markers=('QUICK_ACCESS_GPU_DBUS', 'QUICK_ACCESS_GPU_ALLOWED'),
    ),
    ErrorCode(
        "BC250-RANGE-001",
        "The requested value is outside the supported range.",
        "The value does not match the active hardware table, available RAM, safe points, or the limits enforced by the selected backend.",
        "Choose a value currently offered by the application. Refresh first if another toolkit or a restart may have changed the live limits.",
        exit_statuses=(20, 21, 23, 24, 34, 35, 37, 38, 39, 41, 42, 43, 44, 45, 56, 92),
        markers=('QUICK_ACCESS_GPU_PROFILE', 'QUICK_ACCESS_GPU_SAFE_POINT',
                 'QUICK_ACCESS_GPU_HIGH_POINTS', 'QUICK_ACCESS_GPU_VOLTAGE', 'QUICK_ACCESS_GPU_VERIFY', 'QUICK_ACCESS_CPU_SCALE', 'Frequency must be between', 'VID must be between', 'Temperature must be between', 'QAM CPU frequency must be', 'QAM CPU VID must be', 'QAM CPU detection uses a fixed', 'HELPER_RANGE'),
    ),
    ErrorCode(
        "BC250-CU-001",
        "The Compute Units operation could not be verified.",
        "UMR, the GPU database, the live manager, the saved WGP map, or the AMDGPU topology may not match the running kernel and Mesa stack.",
        "Run Unlock/Sync again, check the displayed live map, prepare UMR if missing, and apply only after the requested and driver maps agree.",
        exit_statuses=(30, 62, 63),
        markers=(
            'QUICK_ACCESS_CU_TABLE', 'QUICK_ACCESS_CU_MODE', 'QUICK_ACCESS_CU_BACKEND',
            'QUICK_ACCESS_CU_SERVICE_REMOVE', 'QUICK_ACCESS_CU_STATE',
            'QUICK_ACCESS_CU_VERIFY', 'QUICK_ACCESS_CU_SERVICE_PROFILE',
            'QUICK_ACCESS_CU_SERVICE_VERIFY',
        ),
    ),
    ErrorCode(
        "BC250-FAN-001",
        "The fan control path is unavailable or rejected the write.",
        "The NCT driver may be read-only, the hwmon number may have changed, the selected PWM channel may not exist, or another fan service is controlling it.",
        "Refresh fan detection, confirm the physical channel, prepare NCT6687 PWM support, and stop other fan-control tools before retrying.",
        exit_statuses=(25, 26, 27, 40, 46),
        markers=('QUICK_ACCESS_FAN',),
    ),
    ErrorCode(
        "BC250-CPU-001",
        "The CPU tuning result could not be applied or verified.",
        "The stress dependency, SMU helper, same-boot detector evidence, temperature limit, or selected frequency and VID do not satisfy the validated workflow.",
        "Run automatic detection for this exact frequency first. Keep the terminal open, monitor temperature, and save the service only after the live result is verified.",
        exit_statuses=(50, 51, 52, 53, 54, 55, 57, 60, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 93, 94),
        markers=('QUICK_ACCESS_CPU', 'QUICK_ACCESS_CPU_VERIFY', 'QUICK_ACCESS_CPU_SERVICE', 'QUICK_ACCESS_CPU_SCALE_VERIFY', 'stress is required by bc250-detect', 'Run automatic detection at this exact frequency', 'Manual scale must reuse the detected thermal limit', 'bc250-detect returned values outside the requested', 'bc250-detect did not produce a valid configuration'),
    ),
    ErrorCode(
        "BC250-AUTH-002",
        "Administrator authorization was not completed.",
        "The password dialog was cancelled, closed, timed out, or rejected the supplied password.",
        "Run the action again and finish the administrator password dialog. No hardware change was applied.",
        exit_statuses=(),
        markers=('QUICK_ACCESS_AUTH',),
    ),
    # Quick Access refuses to run at all: not root, no systemd host, or no
    # BC-250 present. All three exit 10, so the marker decides which applies.
    ErrorCode(
        "BC250-HW-001",
        "Compatible BC-250 hardware was not detected.",
        "The AMDGPU device is unavailable, the application is running in a container or remote session, or the active kernel did not bind the BC-250 GPU.",
        "Verify that lspci shows 1002:13fe and that AMDGPU is loaded. Restart into the BC250 kernel if the device is present without a driver.",
        exit_statuses=(10, 12, 18, 19),
        markers=("HARDWARE_CONTEXT", "QUICK_ACCESS_CONTEXT"),
    ),
    ErrorCode(
        "BC250-GPU-001",
        "The selected GPU telemetry source is unavailable.",
        "The active kernel or BIOS does not expose that sensor, or Cyan is using a telemetry method that this kernel does not support.",
        "For an unpatched kernel, select busy-flag or process. Use kernel only when gpu_busy_percent is readable, then apply Fix metrics or Fix frequencies only when needed.",
        markers=('QUICK_ACCESS_GPU_BUSY', 'gpu_busy_percent'),
    ),
    # Wording is shared verbatim with the desktop rule of the same identifier,
    # so the thirty locales translate both from one set of strings.
    ErrorCode(
        "BC250-CPUTOOL-001",
        'The audited CPU payload refused the requested value.',
        'The R64 detector shipped inside this build enforces its own limits, and they are narrower than what this screen offers: it accepts the stock CPU frequency and above, never below it, and it caps VID and temperature on its own terms.',
        'Ask for a value the payload accepts, or install a build whose audited payload carries the wider range. Nothing is missing and nothing needs reinstalling.',
        markers=('CPU_PAYLOAD_REFUSED',),
    ),
    ErrorCode(
        "BC250-HELPER-001",
        "A protected BC250 helper is missing or failed its safety check.",
        "The application and its root-owned helper are from different installs, or another toolkit changed the helper's owner, mode, or path.",
        "Reinstall or repair BC250 Control Center, then run System Health. Do not copy a helper manually into /usr/libexec.",
        markers=(
            'CU_HELPER_MISSING', 'CU_BACKEND_UNTRUSTED', 'CPU_BACKEND_MISSING',
            'HELPER_PRIVILEGE', 'CPU_BACKEND_UNTRUSTED', 'QUICK_ACCESS_GPU_HELPER',
            'HELPER_UNTRUSTED',
        ),
    ),
    # An upstream release that hosts a pacman repository can be removed or
    # renamed; pacman then reports 404 and the run aborts. Nothing is wrong
    # locally, so this must not read as a machine problem.
    ErrorCode(
        "BC250-UPSTREAM-404",
        "The external package repository is temporarily unavailable at its address.",
        "The upstream project republishes this pacman repository as a GitHub release, and its assets are unavailable while that release is being rebuilt. The address is still the documented one, and nothing is wrong with this system or its network.",
        "Wait for the upstream rebuild to finish and run the workflow again later; the currently installed kernel keeps working meanwhile. Only report the diagnostic code if it still fails after a day.",
        markers=(
            "returned error: 404",
            "failed to synchronize all databases",
            "failed retrieving file",
        ),
    ),
    # The workflow printed its own [ERROR] lines, so its wording is shown
    # instead of a rule. This entry exists so the identifier is a registered
    # one that support can look up, not an invented string.
    ErrorCode(
        "BC250-WORKFLOW-001",
        "The workflow reported the failure itself.",
        "The workflow stopped on a condition it detected and described in its own output.",
        "Follow the steps the workflow printed above; they name the exact package, kernel or path involved.",
    ),
    # Fallback: wording reused from the desktop diagnostic rules so it is
    # already translated in all 30 locales.
    ErrorCode(
        "BC250-GENERAL-001",
        "The operation could not be completed.",
        "The component returned a failure that does not yet match a more specific diagnostic rule.",
        "Read the technical detail below, refresh the affected page, and retry once. If it repeats, copy this complete diagnostic for support.",
    ),
)

GENERAL_FAILURE = _CODES[-1]

BY_CODE: dict[str, ErrorCode] = {entry.code: entry for entry in _CODES}


def _index_exit_statuses() -> dict[int, ErrorCode]:
    index: dict[int, ErrorCode] = {}
    for entry in _CODES:
        for status in entry.exit_statuses:
            # First declaration wins so the table stays deterministic; a repeat
            # means two entries claim one status and the manifest test fails.
            index.setdefault(status, entry)
    return index


_BY_EXIT_STATUS = _index_exit_statuses()
_BY_MARKER: dict[str, ErrorCode] = {}
for _entry in _CODES:
    for _marker in _entry.markers:
        _BY_MARKER.setdefault(_marker, _entry)


def for_exit_status(status: object) -> ErrorCode | None:
    """Return the code a process exit status means, or None when unmapped.

    Signals are reported as ``128 + n`` by the shell; they are not workflow
    failures with a fix, so they stay unmapped and render as the generic entry
    with the signal number preserved in the technical detail.
    """
    try:
        value = int(status)
    except (TypeError, ValueError):
        return None
    return _BY_EXIT_STATUS.get(value)


# Longest marker first: QUICK_ACCESS_CPU is a prefix of QUICK_ACCESS_CPU_VERIFY,
# so the more specific marker has to win.
_MARKERS_BY_LENGTH: tuple[tuple[str, ErrorCode], ...] = tuple(
    sorted(_BY_MARKER.items(), key=lambda item: len(item[0]), reverse=True)
)


def for_marker(text: object) -> ErrorCode | None:
    """Return the code a helper's ``PREFIX:`` stderr marker means."""
    detail = str(text or "")
    for marker, entry in _MARKERS_BY_LENGTH:
        if marker in detail:
            return entry
    return None


def known_exit_statuses() -> frozenset[int]:
    """Every process exit status this catalog can explain."""
    return frozenset(_BY_EXIT_STATUS)


def all_codes() -> tuple[ErrorCode, ...]:
    return _CODES


def translatable_strings() -> tuple[str, ...]:
    """Every English source string here, for the i18n catalogs to collect."""
    seen: dict[str, None] = {}
    for entry in _CODES:
        for value in (entry.summary, entry.cause, entry.action):
            seen.setdefault(value, None)
    return tuple(seen)
