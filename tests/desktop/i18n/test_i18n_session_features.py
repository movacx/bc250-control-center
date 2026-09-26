from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS

GPU_AUDIT_KEYS = (
    "Governor",
    "runtime range interface",
    "current governor target",
    "passive telemetry",
    "GPU Governor console ready. No hardware command has been executed.",
    "Requested {floor} MHz, while D-Bus currently allows {minimum}–{maximum} MHz.",
    "Oberon reloads two YAML endpoints and restarts its service. Control Center uses the upstream 1000 mV baseline for both endpoints; board stability still varies.",
    "persistent floor {minimum} MHz; maximum remains controlled by the runtime profile",
    "persistent floor {minimum}; runtime profile maximum",
    "unlimited",
    "{governors} is installed, enabled, or running. Two GPU frequency governors can issue conflicting clock commands and cause a crash or green screen at the next boot. Continue only to stop and disable the other service before preparing {selected_governor}.",
    "{governors} conflicts with {selected_governor}. Starting both can crash the GPU or produce a green screen at boot. This action will stop and disable the other service before enabling the selected governor.",
    "{governors} is installed, enabled, or running. Two GPU frequency governors can issue conflicting clock commands and cause a crash or green screen at the next boot. Use Prepare dependencies to stop and disable the other service before changing {selected_governor}.",
)


REQUIRED_SESSION_KEYS = (
    "Report a problem / Contact",
    "Contact link could not be opened",
    "Buy me a coffee",
    "Voluntary support — no features are locked.",
    "Support page could not be opened",
    "Start with automatic detection. Manual scale becomes available only after a verified live result.",
    "Run a verified automatic live configuration first. Manual scale unlocks only for that detection session.",
    "Apply an automatic live configuration first to unlock manual scale.",
    "Automatic live configuration verified. You can now test an exact manual scale for this session.",
    "Automatic live configuration verified. Manual scale is now available.",
    "The manual slider is temporary and does not survive reboot by itself. Apply a named preset or enable and save the automatic curve, then enable the optional daemon in Settings to restore it after login.",
    "Enable +2000 MHz TOML points",
    "Disable +2000 MHz TOML points",
    "TOML safe-point laboratory",
    "TOML configuration",
    "Inspect every active safe-point, including +2000 MHz entries, with conservative voltage validation.",
    "TOML safe-point controls, voltage validation, hardware details, and operation output. Hidden by default.",
    "High OC laboratory mode",
    "Lab mode",
    "Active safe-points above 2000 MHz are visible by default. Voltage is compared with the packaged upstream curve, but these points can still be unstable. Stop all 3D load before every change.",
    "Every active TOML safe-point is visible. Points above 2000 MHz will appear automatically when they are enabled in the TOML.",
    "The governor is currently offline; these points will take effect after the service is activated.",
    "Open config.toml",
    "Open the governor TOML in the system's default text or code editor. Saving may require administrator privileges.",
    "Active range floor: 1000 MHz · ceiling: selected safe-point.",
    "Apply active range · select a ceiling",
    "Apply active range · 1000–{maximum} MHz",
    "Cyan will restart once to load the enabled high safe-points, then the requested D-Bus range will be verified.",
    "Governor configuration could not be opened",
    "Opened {path} with the system default editor.",
    "No text editor or compatible application accepted the file.",
    "Incompatible GPU governor detected",
    "GPU crash / green screen at boot",
    "Disable conflict and continue",
    "{governors} is installed, enabled, or running. Two GPU frequency governors can issue conflicting clock commands and cause a crash or green screen at the next boot. Continue only to stop and disable the incompatible service before preparing cyan-skillfish-governor-smu.",
    "{governors} is installed, enabled, or running. Two GPU frequency governors can issue conflicting clock commands and cause a crash or green screen at the next boot. Use Prepare dependencies to stop and disable the incompatible service before changing cyan-skillfish-governor-smu.",
    "Unlock hidden CPU cores",
    "Unlock cores and restart",
    "Unlock CPU cores and restart",
    "CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes. For compatibility, cyan-skillfish-governor-smu will be stopped and disabled before that restart.",
    "GPU → Activate service",
    "Already unlocked",
    "CPU core unlock support is not installed",
    "Upstream tool",
    "Official CPU core unlock tool is not prepared",
    "Use Prepare dependencies to clone and validate the official rw-r-r-0644/bc250-core-unlock repository, then refresh this page.",
    "CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes.",
    "Processor overview",
    "Overview and live monitoring",
    "Processor overview, live cores, and hidden-core unlock.",
    "Profiles, temporary tuning, persistence, and advanced details.",
    "Platform / process",
    "CPU-X-compatible hardware identity",
    "Total CPU load",
    "average across logical threads",
    "Live core monitor",
    "Core {index}",
    "Logical CPUs: {threads}",
    "Active now",
    "It will be stopped before any future upstream unlock action.",
    "Reload active service",
    "Keep disabled; apply on next activation",
    "Comments or uncomments only safe-point blocks above 2000 MHz and validates the complete TOML. The governor is reloaded only when it is already active.",
    "BC250 Control Center does not own these tools. They are installed, cloned, or used as credited reference implementations according to each integration.",
    "The optional user daemon records JSONL metrics and restores the saved fan mode after login: an enabled automatic curve, a named preset or the last manual speed. It never applies CPU or GPU overclock automatically.",
    "Last PWM: {value}. The curve, a named preset or the last manual speed comes back after login while the optional daemon is on, and from boot while control from boot is on.",
    "Enhanced gamepad input backend",
    "All active TOML safe-points with current, original, added voltage, and custom values.",
    "Check original voltage and exact added amount",
    "Level {level}: packaged defaults +{added} mV on every point from {start} MHz; all {count} original points are restored first. Detected curve: Level {detected}.",
    "This restores the complete packaged governor curve, then adds +{added} mV to every safe-point from {start} MHz. A backup is created before the governor restarts.",
    "{maximum} MHz is configured at {voltage} mV; the packaged original voltage is {original} mV. This is an undervolt laboratory condition.",
    "High OC voltage profile required",
    "A range above 2000 MHz requires the complete Level 3 or Level 6 curve. Apply a voltage level first; the range was not changed.",
    "Save only a persistent minimum floor. It leaves the current maximum and selected runtime profile unchanged; restart the governor or reboot to load the saved floor.",
    "Save persistent floor",
    "Save persistent GPU frequency floor",
    "This updates the persistent frequency floor only. An existing active custom maximum is preserved; profile mode uses upstream's unlimited maximum (0). It does not send a D-Bus command, change the active runtime maximum, or replace the selected runtime profile.",
    "Persistent floor",
    "Advanced safe-points",
    "Service action",
    "Read status",
    "D-Bus allowed: {allowed_min}–{allowed_max} MHz · active runtime: {minimum}–{maximum} MHz · persistent TOML: {persistent}.",
    "custom floor {minimum} MHz, maximum {maximum}",
    "disabled for runtime profile mode",
    "unknown TOML state",
    "GPU governor backend",
    "Automatic detection",
    "Cyan Skillfish Governor (SMU)",
    "Oberon Governor",
    "Automatic follows the uniquely active or installed supported governor. Only one governor may run at a time; changing this selection does not silently start or stop a system service.",
    "Selected governor",
    "Oberon YAML + service restart",
    "Oberon endpoint OPPs",
    "Oberon telemetry limitation",
    "Open BC-250 telemetry compatibility guide",
    "Oberon allowed: {allowed_min}–{allowed_max} MHz · configured endpoints: {minimum}–{maximum} MHz · persistent YAML: {persistent}.",
    "Persistent scale override",
    "Override the detected scale when enabling boot persistence",
    "Confirm multi-step scale change",
    "Detected estimated VID",
    "Requested estimated VID",
    "PWM channel",
    "Select a detected PWM channel for BC250 cooling control.",
    "Select one detected channel, stage a duty, then apply it explicitly.",
    "This value is staged only. Hardware changes only after confirmation.",
    "Manual PWM is temporary. Use the automatic curve when you want a saved cooling response.",
    "Use current duty",
    "Apply staged PWM",
    "Last refresh failed",
    "Sensor data is stale; refresh before a PWM write.",
    "Cyan on OpenRC requires the system D-Bus to be running. Install the D-Bus OpenRC integration when your distribution provides it, then explicitly enable/start its dbus service and refresh dependencies. Control Center will not enable an unrelated system service automatically.",
    "System health",
    "Run health check",
    "Repair installation",
    "Generate diagnostic report",
    "CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes. For compatibility, the selected GPU frequency governor will be stopped and disabled before that restart.",
    "Restart is required and the active GPU frequency governor will be disabled.",
    "CU write actions are locked until a verified root-owned backend is installed.",
)


def test_new_session_copy_has_every_supported_language():
    for key in REQUIRED_SESSION_KEYS:
        assert key in INTERFACE_TRANSLATIONS, key
        assert all(tr(key, language).strip() for language in SUPPORTED_LANGUAGES)


def test_gpu_persistent_floor_copy_never_falls_back_to_english_in_spanish():
    for key in REQUIRED_SESSION_KEYS:
        if key.startswith("Oberon") or key in {
            "GPU governor backend", "Automatic detection", "Selected governor",
            "Open BC-250 telemetry compatibility guide",
        }:
            assert tr(key, "es") != key


def test_new_cpu_fan_health_and_governor_copy_is_translated_in_polish():
    for key in REQUIRED_SESSION_KEYS[-22:]:
        if key not in {"Cyan Skillfish Governor (SMU)", "Oberon Governor"}:
            assert tr(key, "pl") != key
        assert tr(key, "es") != key


def test_gpu_frame_audit_has_no_spanish_or_polish_fallbacks():
    for key in GPU_AUDIT_KEYS:
        assert key in INTERFACE_TRANSLATIONS, key
        assert tr(key, "es") != key
        if key != "Governor":
            assert tr(key, "pl") != key
