"""Turn low-level failures into useful, stable support diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from bc250cc.shared import error_catalog

Translator = Callable[[object], str]


@dataclass(frozen=True)
class ErrorDiagnosis:
    code: str
    summary: str
    cause: str
    action: str


@dataclass(frozen=True)
class _Rule:
    code: str
    patterns: tuple[str, ...]
    summary: str
    cause: str
    action: str

    def matches(self, value: str) -> bool:
        return any(re.search(pattern, value, re.IGNORECASE) for pattern in self.patterns)


_RULES = (
    # First on purpose. Cyan's fix-metrics / fix-freq replace two GPU sensor
    # files with patched copies through a bind mount. When one is left behind
    # the daemon cannot start, and the log carries so many generic words
    # ("failed", "no such file", "D-Bus name is unavailable") that without a
    # rule of its own it lands on whichever broad pattern happens to be first.
    _Rule(
        "BC250-GPU-005",
        (r"patched_(?:gpu|freq)_metrics", r"move_mount\(\) failed",
         r"mount --bind.*failed", r"mount.*failed: exit status: 32",
         r"failed to place its patched", r"left-?over mount", r"stale mount"),
        "The governor could not put its patched sensor files in place.",
        "Cyan replaces two GPU sensor files with patched copies while it runs. One replacement from an earlier run is still in place, so the new one cannot be made and the service stops.",
        "Stop the governor, undo the leftover replacement on the path named in the technical detail, then start it again. If it keeps happening, turn off Fix metrics and Fix frequencies.",
    ),
    _Rule(
        "BC250-GPU-006",
        (r"does not expose the gpu_metrics file", r"cannot provide cyan gpu_metrics",
         r"fix-metrics was requested", r"not to support cyan's gpu_metrics"),
        "This kernel cannot do the Cyan metrics fix.",
        "Fix metrics makes Cyan publish its own gpu_metrics file. The running kernel does not expose the file it needs to replace, so the governor refuses to start while that option is on. Nothing on the hardware was changed.",
        "Turn off Fix metrics in Cyan kernel compatibility and apply again. Leave Fix frequencies off too if the start still fails. A BC-250 patched kernel is the other way out.",
    ),
    _Rule(
        "BC250-AUTH-001",
        (r"textual authentication agent", r"/dev/tty.*no such device", r"controlling terminal"),
        "The authorization window could not be opened.",
        "The application was started from a session that Polkit cannot attach its password prompt to.",
        "Close this copy, start BC250 Control Center from the desktop application menu, and try again. If it continues, reinstall the protected helpers.",
    ),
    _Rule(
        "BC250-AUTH-002",
        (r"not authorized", r"authentication.*(?:cancel|fail|dismiss)", r"authorization.*(?:cancel|fail|dismiss)"),
        "Administrator authorization was not completed.",
        "The password dialog was cancelled, closed, timed out, or rejected the supplied password.",
        "Run the action again and finish the administrator password dialog. No hardware change was applied.",
    ),
    _Rule(
        "BC250-AUTH-003",
        (r"pkexec.*not found", r"polkit.*not found", r"polkit/pkexec"),
        "The system authorization service is missing.",
        "BC250 Control Center needs Polkit for protected changes, but pkexec is not installed or cannot be found.",
        "Install the Polkit package for this distribution, sign out and back in, then retry the action.",
    ),
    _Rule(
        "BC250-PERM-001",
        (r"permission denied", r"operation not permitted", r"access denied", r"read-only file system"),
        "Linux refused access to a required file or device.",
        "A helper, device node, configuration file, or immutable system path has ownership or permission settings that do not allow this operation.",
        "Use System Health to verify permissions and helpers. On Bazzite or SteamOS, finish any pending deployment and restart before retrying.",
    ),
    _Rule(
        "BC250-HELPER-001",
        (r"helper.*(?:missing|not found|unavailable)", r"protected helper", r"unsafe ownership", r"unsafe.*permissions"),
        "A protected BC250 helper is missing or failed its safety check.",
        "The application and its root-owned helper are from different installs, or another toolkit changed the helper's owner, mode, or path.",
        "Reinstall or repair BC250 Control Center, then run System Health. Do not copy a helper manually into /usr/libexec.",
    ),
    _Rule(
        "BC250-PROTOCOL-001",
        (r"protocol.*incompat", r"version mismatch", r"expected protocol", r"stale.*helper"),
        "The interface and protected helper are different versions.",
        "An older Desktop or Decky component is still running after an update, or only part of the application was replaced.",
        "Reinstall the current build and restart the application. Restart Decky Loader too when the Quick Access panel is affected.",
    ),
    _Rule(
        "BC250-BUSY-001",
        (r"already.*(?:running|applying|in progress)", r"operation.*still.*(?:running|progress)", r"resource busy", r"device or resource busy"),
        "Another operation is still using this component.",
        "A previous BC250 action, package manager, service restart, or external toolkit still holds the required lock.",
        "Wait for the current terminal or progress indicator to finish, refresh the page, and retry once. Close other BC250 toolkits if the lock remains.",
    ),
    _Rule(
        "BC250-DBUS-001",
        (r"d-bus.*(?:not ready|unavailable|failed)", r"dbus.*(?:not ready|unavailable|failed)", r"failed to connect to bus", r"busctl.*failed", r"org\.freedesktop\.dbus\.error", r"serviceunknown", r"com\.cyanskillfish", r"no such interface", r"range objects did not become ready", r"could not be restored safely", r"could not be read through d-bus"),
        "The GPU governor did not expose its D-Bus controls.",
        "Cyan is stopped, still starting, using an incompatible configuration, or another governor owns the GPU control path.",
        "Check the governor service status, resolve any Cyan/Oberon conflict, start the selected service, and wait a few seconds before refreshing.",
    ),
    _Rule(
        "BC250-SERVICE-001",
        (r"unit .*masked", r"service.*masked", r"is masked"),
        "The required service is masked.",
        "Linux is explicitly blocking the service from starting. This can remain after a manual rollback or another toolkit installation.",
        "Open the service status, remove the mask only for the named BC250 service, then reinstall its boot persistence from the application.",
    ),
    _Rule(
        "BC250-SERVICE-002",
        (r"unit .*not found", r"service.*not[- ]found", r"service.*does not exist", r"no such.*service", r"unit not found"),
        "The required service definition was not found.",
        "The tool may be present without its systemd or OpenRC service, or a rollback left a service pointing to a removed file.",
        "Prepare that module again from the Dashboard, then install its service. Use System Health if an old service is still detected.",
    ),
    _Rule(
        "BC250-SERVICE-003",
        (r"systemctl.*(?:failed|exited)", r"rc-service.*(?:failed|exited)", r"service.*failed", r"failed to start", r"job for .*(?:failed|exited)", r"control process exited", r"invalid openrc .*action", r"requires an active systemd", r"boot persistence is not supported", r"no service action was run", r"invalid .*service action"),
        "The service manager could not complete the requested change.",
        "The service configuration is invalid, its executable is missing, or the selected init system does not match the installed service files.",
        "Open the service status and read the first reported error. Repair the module from the Dashboard before enabling it again.",
    ),
    _Rule(
        "BC250-PKG-001",
        (r"unable to lock", r"database is locked", r"could not get lock", r"another app is currently holding", r"transaction.*lock", r"lock-?frontend", r"could not lock database", r"dpkg.*lock"),
        "The package manager is busy.",
        "A system update, software center, or another terminal is already changing packages.",
        "Let that update finish, close the other package tool, and retry. Do not delete package-manager lock files by hand.",
    ),
    _Rule(
        "BC250-PKG-002",
        (r"invalid or corrupted package", r"signature.*(?:invalid|unknown|trust)", r"keyring", r"gpg.*(?:error|failed)", r"public key.*unknown", r"gpg check failed", r"unknown trust", r"integrity validation", r"could not fingerprint", r"origin, revision"),
        "The package signature or repository key could not be verified.",
        "The keyring may be outdated, the download may be incomplete, or an external repository has a trust configuration that differs from the selected workflow.",
        "Update the distribution keyring and retry. If this is an external repository, review its configured signature policy before changing pacman, DNF, or APT settings.",
    ),
    _Rule(
        "BC250-PKG-003",
        (r"already configured outside control center", r"repository.*already.*configured", r"duplicate database entry", r"conflicting values set for option", r"repository .* is already configured"),
        "An external repository is already configured differently.",
        "A previous manual installation or another toolkit owns the same repository entry, so the application cannot safely rewrite it.",
        "Review the named repository in the package-manager configuration, remove or reconcile the old entry, then run the BC250 workflow again.",
    ),
    _Rule(
        "BC250-UPSTREAM-404",
        (r"returned error: 404", r"\b404\b.*not found", r"failed retrieving file.*\.db",
         r"failed to synchronize all databases", r"failed retrieving file from repo", r"http 404"),
        "The external package repository is temporarily unavailable at its address.",
        "The upstream project republishes this pacman repository as a GitHub release, and its assets are unavailable while that release is being rebuilt. The address is still the documented one, and nothing is wrong with this system or its network.",
        "Wait for the upstream rebuild to finish and run the workflow again later; the currently installed kernel keeps working meanwhile. Only report the diagnostic code if it still fails after a day.",
    ),
    _Rule(
        "BC250-NET-001",
        (r"could not resolve", r"temporary failure in name resolution", r"network is unreachable", r"connection.*(?:timed out|refused|reset)", r"ssl|certificate verify|tls", r"curl: \(\d+\)"),
        "A required download could not be reached or verified.",
        "The network, DNS, proxy, system clock, certificate store, or upstream server interrupted the download.",
        "Confirm internet access and the system date, then retry. If a proxy or filtered network is in use, test the repository URL in a browser.",
    ),
    _Rule(
        "BC250-STORAGE-001",
        (r"no space left", r"disk quota exceeded", r"not enough free space"),
        "There is not enough writable storage.",
        "The target filesystem, temporary directory, boot partition, or user quota is full.",
        "Free space on the filesystem named in the technical detail, then retry. Kernel installs also require free space in /boot.",
    ),
    _Rule(
        "BC250-IMMUTABLE-001",
        (r"rpm-ostree", r"ostree", r"immutable", r"deployment.*pending", r"transaction in progress"),
        "The immutable system deployment is not ready for this change.",
        "Bazzite or SteamOS may have a pending update, rollback, rebase, or restart, or the selected workflow is intended for a mutable distribution.",
        "Finish the pending deployment and restart. Then use the Bazzite or SteamOS workflow shown by the compatibility filter.",
    ),
    _Rule(
        "BC250-CMD-001",
        (r"command not found", r"no such file or directory", r"executable.*not found", r"returned an empty command", r": command not found", r"needs one boolean", r"does not accept additional arguments", r"not prepared", r"is not installed", r"was not found", r"does not exist at", r"is missing from", r"unavailable in this build", r"terminal integration is required", r"qualification", r"bundle error", r"refusing .*without --", r"evidence error", r"expects a .*path", r"command is required", r"no custom values", r"integration script", r"requires --", r"runner is unavailable", r"executor is invalid", r"path is invalid"),
        "A required program or generated command is missing.",
        "Dependencies were not prepared, a toolkit was removed, or the active distribution provides the program under a different package or path.",
        "Return to the Dashboard and prepare the affected module. If it was already prepared, run System Health to find the missing path.",
    ),
    _Rule(
        "BC250-KERNEL-001",
        (r"kernel headers", r"module.*(?:not found|invalid format|unknown symbol)", r"modprobe.*(?:failed|fatal)", r"dkms.*(?:failed|error)", r"vermagic", r"version magic", r"headers .*(?:not found|were not found)", r"invalid module format", r"-ogc\d"),
        "The running kernel and its driver or headers do not match.",
        "The machine may still be running the old kernel, headers may be missing, Secure Boot may reject the module, or a partial update mixed versions.",
        "Restart into the intended BC250 kernel, verify its matching headers, then repair the affected driver. Review Secure Boot only if the module log names it.",
    ),
    _Rule(
        "BC250-HW-001",
        (r"1002:13fe.*not", r"bc-?250.*not detected", r"unsupported.*hardware", r"amdgpu.*not.*(?:found|detected)", r"1002:13fe", r"\b13fe\b", r"no device with pci", r"pci id .*not", r"only run this on bc-?250"),
        "Compatible BC-250 hardware was not detected.",
        "The AMDGPU device is unavailable, the application is running in a container or remote session, or the active kernel did not bind the BC-250 GPU.",
        "Verify that lspci shows 1002:13fe and that AMDGPU is loaded. Restart into the BC250 kernel if the device is present without a driver.",
    ),
    _Rule(
        "BC250-GPU-001",
        (r"gpu_busy_percent", r"gpu busy", r"busy-flag", r"gpu-usage", r"frequency.*(?:unavailable|not detected)", r"sensor unavailable"),
        "The selected GPU telemetry source is unavailable.",
        "The active kernel or BIOS does not expose that sensor, or Cyan is using a telemetry method that this kernel does not support.",
        "For an unpatched kernel, select busy-flag or process. Use kernel only when gpu_busy_percent is readable, then apply Fix metrics or Fix frequencies only when needed.",
    ),
    _Rule(
        "BC250-GPU-002",
        (r"cyan.*oberon", r"governor.*conflict", r"incompatible gpu governor", r"multiple.*governor"),
        "More than one GPU governor is installed or active.",
        "Cyan, Oberon, or a community toolkit is trying to manage the same GPU controls.",
        "Keep only the governor selected in Control Center active. Disable the other service, refresh, and verify the active governor before applying clocks.",
    ),
    # Before BC250-CONFIG-001 on purpose: its "invalid ... value" pattern
    # matches argparse's "invalid int_freq value" and used to report a broken
    # configuration file for a value the interface itself had offered.
    _Rule(
        "BC250-CPUTOOL-001",
        (
            r"cannot overclock below stock frequency",
            r"target frequency is too high",
            r"invalid int_(?:freq|vid|temp) value",
            r"it is not allowed to go (?:below|above) \d+ ?mv vid",
            r"temperature limit cannot be above",
            r"specify positive integers for temperature limit",
        ),
        'The audited CPU payload refused the requested value.',
        'The R64 detector shipped inside this build enforces its own limits, and they are narrower than what this screen offers: it accepts the stock CPU frequency and above, never below it, and it caps VID and temperature on its own terms.',
        'Ask for a value the payload accepts, or install a build whose audited payload carries the wider range. Nothing is missing and nothing needs reinstalling.',
    ),
    _Rule(
        "BC250-CONFIG-001",
        (r"toml.*(?:invalid|parse|validation|error)", r"governor toml", r"\[gpu\]", r"\[frequency-range\]", r"\[[a-z-]+\] section", r"duplicate \[", r"safe-?point.*not present", r"missing mhz", r"voltage decreases", r"conflicting voltage", r"section is invalid", r"exactly one \[", r"changed during", r"yaml.*(?:invalid|parse|validation|error)", r"json.*(?:invalid|parse|decode)", r"configuration.*(?:invalid|malformed)", r"invalid .*(?:toml|action|value|entry|table|key)", r"must be boolean", r"must be smu or kernel", r"must use frequency=", r"needs set-method", r"compatibility values are invalid", r"must be unchanged, default, or one of"),
        "A configuration file is invalid or incomplete.",
        "A manual edit, older toolkit, interrupted write, or unsupported option left syntax or values the current component cannot read.",
        "Open the named file from the application, correct the first reported line or restore the module defaults, then apply the settings again.",
    ),
    _Rule(
        "BC250-RANGE-001",
        (r"out of range", r"unsupported.*(?:profile|safe-point|mode|voltage level)", r"cannot exceed maximum", r"cannot be negative", r"requires positive", r"outside cyan's active", r"minimum cannot exceed", r"invalid lab level", r"must be (?:between|an? )", r"exceeds.*(?:limit|ceiling|ram)", r"invalid.*(?:frequency|voltage|target|mask)", r"the ui limits", r"outside the safe editor range", r"limits .* to \d", r"must not exceed", r"outside the supported", r"outside the reviewed"),
        "The requested value is outside the supported range.",
        "The value does not match the active hardware table, available RAM, safe points, or the limits enforced by the selected backend.",
        "Choose a value currently offered by the application. Refresh first if another toolkit or a restart may have changed the live limits.",
    ),
    _Rule(
        "BC250-CU-001",
        (r"\bumr\b", r"wgp", r"compute unit", r"cu_(?:table|backend|verify|service|mode)", r"0x77", r"0xff\b", r"shader_array_config", r"wgp mask", r"topolog", r"core presence mask", r"bc250_cc_write_mode", r"disable_cu"),
        "The Compute Units operation could not be verified.",
        "UMR, the GPU database, the live manager, the saved WGP map, or the AMDGPU topology may not match the running kernel and Mesa stack.",
        "Run Unlock/Sync again, check the displayed live map, prepare UMR if missing, and apply only after the requested and driver maps agree.",
    ),
    _Rule(
        "BC250-COLLISION-001",
        (r"\blimine\b", r"already owns", r"owned by another", r"another toolkit",
         r"bc250-toolkit", r"nct668[36]\b", r"ssdt-cst", r"duplicate.*(?:table|ssdt)",
         r"conflicting.*(?:driver|table|bootloader|ownership)"),
        "Another BC-250 toolkit already owns this setting.",
        "A different tool installed its own driver, boot entry, or system table for the same job. Two owners for one setting is what breaks it.",
        "Remove or disable the other tool's copy of this piece, then run this step again. System Health lists what else was found.",
    ),
    _Rule(
        "BC250-FAN-001",
        (r"\bpwm\b", r"nct668", r"hwmon.*(?:fan|pwm)", r"(?:fan|pwm).*hwmon", r"fan.*(?:failed|unavailable|not found)", r"fan channel", r"fan request", r"no nct", r"hwmon sensor", r"acpi.*resource conflict", r"acpi support missing from driver", r"ec base i/o port", r"failed to insert module 'nct", r"nct668\d", r"acpi_enforce_resources", r"\bpwm\d?_enable\b"),
        "The fan control path is unavailable or rejected the write.",
        "The NCT driver may be read-only, the hwmon number may have changed, the selected PWM channel may not exist, or another fan service is controlling it.",
        "Refresh fan detection, confirm the physical channel, prepare NCT6687 PWM support, and stop other fan-control tools before retrying.",
    ),
    _Rule(
        "BC250-CPU-001",
        (r"bc250-detect", r"stress(?:-ng)?", r"cpu.*(?:scale|vid|frequency|profile|tuning)", r"smu.*(?:failed|error|unavailable)", r"\bvid\b", r"core unlock", r"smu[_-]oc", r"1\.325", r"mprime", r"per-core telemetry"),
        "The CPU tuning result could not be applied or verified.",
        "The stress dependency, SMU helper, same-boot detector evidence, temperature limit, or selected frequency and VID do not satisfy the validated workflow.",
        "Run automatic detection for this exact frequency first. Keep the terminal open, monitor temperature, and save the service only after the live result is verified.",
    ),
    _Rule(
        "BC250-GPU-004",
        (r"did not publish", r"accepted set(?:range|fixedfrequency)",
         r"did not expose the requested", r"allowed \(\d+, \d+\)",
         r"backend active .*allows", r"od_range"),
        "The governor took the request, but the hardware did not apply it.",
        "The driver publishes its own allowed range and refuses anything outside it. With the governor method set to Kernel that ceiling is usually 2000 MHz on a stock BC-250 driver.",
        "Switch the governor method to SMU under Cyan kernel compatibility, or use a patched kernel. The TOML was saved; only the live range was refused.",
    ),
    _Rule(
        "BC250-GPU-003",
        (r"cs_legacy_8core_metrics", r"per-core telemetry", r"8[- ]core.*(?:telemetry|metrics)",
         r"telemetry.*(?:scrambled|nonsense)", r"freq1_input", r"pp_dpm_sclk"),
        "The GPU readings cannot be trusted right now.",
        "With the two extra CPU cores unlocked on a stock BIOS, the board reports a GPU clock and temperature that are wrong. This is a known BC-250 firmware limit, not a fault in this machine.",
        "Add amdgpu.cs_legacy_8core_metrics=1 to the kernel command line and restart, or use a BIOS that carries the SMU telemetry patch. Hardware control keeps working meanwhile.",
    ),
    _Rule(
        "BC250-PLATFORM-001",
        (r"only on steamos", r"only available on", r"available only on", r"does not meet the .*requirement", r"by upstream policy", r"no reviewed distribution", r"must be selected", r"only on plain arch", r"not supported on", r"is unavailable on",
         r"requires a headless host", r"unsupported .*(?:bazzite|steamos|cachyos|fedora|distribution|platform)",
         r"(?:bazzite|steamos|cachyos) .*(?:requires|refus|not)"),
        "This step is not available on this system.",
        "The workflow is written for a different distribution, system image, or init system than the one now running.",
        "Use the option the Dashboard offers for this system. The compatibility filter shows which workflow applies here.",
    ),
    _Rule(
        "BC250-RECOVERY-001",
        (r"snapshot", r"\brecovery\b.*(?:requires|invalid|does not exist|failed)",
         r"rollback.*(?:failed|unavailable)"),
        "The saved snapshot could not be used.",
        "The snapshot is missing, was named incorrectly, or belongs to a different installation of the application.",
        "Open the recovery list, choose a snapshot that appears there, and run the action again.",
    ),
    _Rule(
        "BC250-TIMEOUT-001",
        (r"timed out", r"timeout", r"exit (?:code|status) 124"),
        "The operation did not finish within its safety limit.",
        "A service, hardware read-back, package download, or external toolkit stopped responding or needed longer than expected.",
        "Check whether the terminal or service is still active, then review its log. Retry only after the previous process has ended.",
    ),
    _Rule(
        "BC250-TERMINAL-001",
        (r"no supported graphical terminal", r"terminal.*could not.*open", r"exit (?:code|status) 126", r"exit (?:code|status) 127"),
        "The required terminal workflow could not be started.",
        "No supported graphical terminal was found, its launcher rejected the command, or a required executable is absent.",
        "Install a supported terminal or run the private script path shown in the technical detail from your existing terminal.",
    ),
    _Rule(
        "BC250-DATA-001",
        (r"exit (?:code|status) 65", r"exited with code 65", r"already exists", r"will not be overwritten", r"duplicates will fail to load"),
        "The workflow rejected an existing or inconsistent configuration.",
        "A repository, toolkit file, package source, or saved value already exists in a form the workflow will not overwrite automatically.",
        "Read the ERROR line immediately above the exit code, correct the named configuration, and run the workflow again.",
    ),
    _Rule(
        "BC250-INTERNAL-001",
        (r"cannot be empty", r"must be (?:integers|strings|numbers|a mapping|a sequence)",
         r"non-finite", r"unsupported .*action\b", r"unknown .*(?:integration|action|backend)\b",
         r"invalid .*identifier", r"requires platformcapabilities", r"unexpectedly large",
         r"must be a valid", r"contains an invalid", r"invalid .*count", r"unsupported .*component", r"must not end with", r"unknown .*component"),
        "A check inside the application failed.",
        "One part of BC250 Control Center passed a value that another part refuses. This is a defect in the application, not a problem with this machine or its hardware.",
        "Nothing on the hardware was changed. Copy this complete diagnostic and report it so the check can be fixed.",
    ),
)


_CONTEXT_FALLBACKS = (
    ("BC250-GPU-900", ("gpu", "governor", "cyan", "oberon"), "The GPU operation could not be completed.", "The active governor, its service, configuration, or live hardware state did not accept the request.", "Refresh GPU status, verify the selected governor, and retry with a profile offered by the current page."),
    ("BC250-CPU-900", ("cpu", "smu"), "The CPU operation could not be completed.", "The CPU helper, detector, stress test, or live profile did not return a verified result.", "Refresh CPU status and repeat the guided detect, test, and save sequence."),
    ("BC250-CU-900", ("compute", "40cu", "wgp", "cu "), "The Compute Units operation could not be completed.", "The live topology, UMR backend, or persistence service did not return a verified result.", "Refresh the live CU map and repeat the guided sync, apply, test, and save sequence."),
    ("BC250-FAN-900", ("fan", "pwm"), "The fan operation could not be completed.", "The detected sensor, PWM channel, driver mode, or read-back did not accept the request.", "Refresh sensor detection and return the channel to Automatic before trying another manual value."),
    ("BC250-DECKY-900", ("decky", "quick access"), "The Quick Access operation could not be completed.", "The Decky plugin, protected helper, or live Desktop configuration did not return a verified result.", "Open BC250 Control Center in Desktop Mode, repair Quick Access, then restart Decky Loader."),
)

# Wording generated into the terminal script. It is produced in ``src`` but
# translated here, so it has to be part of the locale inventory too.
TERMINAL_SOURCES = (
    "The workflow did not finish successfully.",
    "Reported error",
    "Last lines from the workflow output:",
    "Full log saved to",
    "You can share that .log file if something failed.",
    "Enter to close...",
)

DIAGNOSTIC_SOURCES = tuple(dict.fromkeys((
    "What happened",
    "Likely cause",
    "How to fix it",
    "Technical detail",
    "Diagnostic code",
    "No additional technical detail was returned.",
    *error_catalog.translatable_strings(),
    *TERMINAL_SOURCES,
    *(value for rule in _RULES for value in (rule.summary, rule.cause, rule.action)),
    *(value for _code, _markers, summary, cause, action in _CONTEXT_FALLBACKS for value in (summary, cause, action)),
    "The operation could not be completed.",
    "The component returned a failure that does not yet match a more specific diagnostic rule.",
    "Read the technical detail below, refresh the affected page, and retry once. If it repeats, copy this complete diagnostic for support.",
)))


def _clean_detail(value: object) -> str:
    detail = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value or "")).strip()
    detail = re.sub(r"^ERR\s+", "", detail, flags=re.IGNORECASE)
    detail = re.sub(r"\n{3,}", "\n\n", detail)
    if len(detail) > 1800:
        detail = detail[:1797].rstrip() + "..."
    return detail or "No additional technical detail was returned."


def diagnose_error(message: object, *, context: object = "") -> ErrorDiagnosis:
    """Classify a failure, letting the message outrank where it came from.

    The context is the operation the user was running. It used to be appended
    to the message and matched as one string, which meant a rule whose pattern
    only appeared in the *context* could beat every rule that actually read the
    *message*: a GPU governor that failed to start was once reported as a
    Compute Units problem because the surrounding workflow said "compute
    units". So the message is matched on its own first, and the context is only
    consulted when the message alone says nothing.
    """
    detail = _clean_detail(message)
    message_only = detail.casefold()
    for rule in _RULES:
        if rule.matches(message_only):
            return ErrorDiagnosis(rule.code, rule.summary, rule.cause, rule.action)

    combined = f"{detail}\n{context}".casefold()
    for rule in _RULES:
        if rule.matches(combined):
            return ErrorDiagnosis(rule.code, rule.summary, rule.cause, rule.action)
    for code, markers, summary, cause, action in _CONTEXT_FALLBACKS:
        if any(marker in combined for marker in markers):
            return ErrorDiagnosis(code, summary, cause, action)
    return ErrorDiagnosis(
        "BC250-GENERAL-001",
        "The operation could not be completed.",
        "The component returned a failure that does not yet match a more specific diagnostic rule.",
        "Read the technical detail below, refresh the affected page, and retry once. If it repeats, copy this complete diagnostic for support.",
    )


def format_error_for_user(
    message: object,
    *,
    context: object = "",
    translate: Translator = str,
) -> str:
    """Return a human explanation while preserving bounded technical evidence."""
    detail = _clean_detail(message)
    if "Diagnostic code:" in detail or "Código de diagnóstico:" in detail:
        return detail
    diagnosis = diagnose_error(detail, context=context)
    sections = (
        (translate("What happened"), translate(diagnosis.summary)),
        (translate("Likely cause"), translate(diagnosis.cause)),
        (translate("How to fix it"), translate(diagnosis.action)),
        (translate("Technical detail"), translate(detail)),
    )
    rendered = "\n\n".join(f"{heading}\n{body}" for heading, body in sections)
    return f"{rendered}\n\n{translate('Diagnostic code')}: {diagnosis.code}"
