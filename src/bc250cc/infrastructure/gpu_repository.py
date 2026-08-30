import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from bc250cc.domain.gpu.oberon import (
    OBERON_IDLE_MAX_BUSY_PERCENT,
    OBERON_IDLE_MAX_CLOCK_MHZ,
    oberon_reference_endpoints,
    require_oberon_safe_profile,
)
from bc250cc.infrastructure.cyan_governor_runtime import (
    detect_cyan_frequency_fix_runtime,
    detect_cyan_metrics_fix_runtime,
    detect_cyan_runtime_identity,
)
from bc250cc.infrastructure.governor_config_request import (
    GOVERNOR_CONFIG_HELPER_PROTOCOL,
    governor_config_helper_protocol,
    plan_governor_config_request,
)
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    GOVERNOR_SPECS,
    OBERON_GOVERNOR,
    ensure_no_incompatible_governors,
    normalize_governor_preference,
    resolve_gpu_governor,
)
from bc250cc.infrastructure.gpu.cyan_gpu_engine import CyanGpuEngine
from bc250cc.infrastructure.gpu.governor_toml import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    OBERON_SAFE_VOLTAGE_MIN_MV,
    SUPPORTED_VOLTAGE_LEVELS,
    GovernorTomlEditor,
    GovernorTomlError,
    OberonYamlEditor,
    OberonYamlError,
)
from bc250cc.infrastructure.gpu_live_clock import read_hwmon_clock_mhz
from bc250cc.infrastructure.gpu_state import (
    GpuDeviceEvidence,
    GpuGovernorEvidence,
    build_gpu_state_snapshot,
)
from bc250cc.infrastructure.telemetry_policy import (
    daemon_governor_probe_budget,
    run_daemon_governor_probe,
)
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_status,
    service_key,
)


class GPURepository:
    _GOVERNOR_CONFIG = Path("/etc/cyan-skillfish-governor-smu/config.toml")
    _GOVERNOR_SERVICE = "cyan-skillfish-governor-smu.service"
    _GOVERNOR_RANGE_INTERFACE = "com.cyanskillfish.Governor.Range"

    @staticmethod
    def _openrc_service_helper_path():
        return Path("/usr/libexec/bc250-control-center/bc250-openrc-service-helper")

    def _service_is_active(self, service):
        init_manager = detect_init_manager()
        if init_manager.kind == "openrc":
            code, out, err = self._ejecutar(
                ["rc-service", service_key(service), "status"], timeout=5
            )
            return parse_openrc_status(code, out or err) == "active"
        if init_manager.kind != "systemd":
            return False
        code, _out, _err = self._ejecutar(
            ["systemctl", "is-active", "--quiet", service], timeout=5
        )
        return code == 0

    def _gpu_governor_preference(self):
        try:
            return self.configuracion.leer_config().get("gpu_governor", "auto")
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return "auto"

    def _gpu_governor_context(self):
        if not callable(getattr(self, "_ejecutar", None)):
            return {
                "preference": "auto",
                "selected": CYAN_GOVERNOR,
                "reason": "default",
                "detected": {},
                "conflicts": (),
            }
        return resolve_gpu_governor(self, self._gpu_governor_preference())

    def _selected_gpu_governor(self):
        return str(self._gpu_governor_context()["selected"])

    def _require_openrc_governor_preflight(self, selected: str) -> None:
        """Block an OpenRC Cyan action before it creates a half-working setup.

        CU/CPU/PWM can work on a minimal OpenRC host without a system D-Bus,
        whereas Cyan cannot: this application uses its D-Bus range interface
        to verify every GPU action. The dependency inventory already probes
        that distinction, so reuse it at the authoritative backend boundary
        instead of letting a terminal command fail late and ambiguously.
        """
        if selected != CYAN_GOVERNOR or detect_init_manager().kind != "openrc":
            return
        tools = self.estado_herramientas_bc250()
        preflight = tools.get("openrc_preflight")
        if not isinstance(preflight, dict):
            raise TypeError(
                "OpenRC capability check is unavailable. Refresh dependencies before configuring Cyan."
            )
        missing = [str(item) for item in preflight.get("missing", ())]
        missing.extend(str(item) for item in preflight.get("missing_for_cyan", ()))
        if missing:
            required = ", ".join(dict.fromkeys(missing))
            if required == "system D-Bus":
                raise RuntimeError(
                    "Cyan on OpenRC requires the system D-Bus to be running. "
                    "Install the D-Bus OpenRC integration when your distribution provides it, "
                    "then explicitly enable/start its dbus service and refresh dependencies. "
                    "Control Center will not enable an unrelated system service automatically."
                )
            raise RuntimeError(
                "Cyan on OpenRC requires a ready privileged service environment: "
                f"{required}. Install the missing capability, then refresh dependencies."
            )

    def estado_bc250_daemon(self):
        """Small bounded snapshot for the background daemon's slow lane.

        The full UI state performs source/config/tool inspection and multiple
        service queries. The daemon needs only the active service, current
        Cyan range and sysfs clock; keeping this path explicit prevents future
        UI integrations from silently entering the periodic loop.
        """
        preference = normalize_governor_preference(self._gpu_governor_preference())
        if preference not in GOVERNOR_SPECS:
            cyan = GOVERNOR_SPECS[CYAN_GOVERNOR]
            oberon = GOVERNOR_SPECS[OBERON_GOVERNOR]
            preference = (
                OBERON_GOVERNOR
                if self._command_path(str(oberon["binary"]))
                and not self._command_path(str(cyan["binary"]))
                else CYAN_GOVERNOR
            )
        spec = GOVERNOR_SPECS[preference]
        gpu = self._gpu_device_path()
        sclk = self._parse_dpm_actual(
            self._leer_texto(gpu / "pp_dpm_sclk") if gpu else None
        )
        result = {
            "service_active": "",
            "service_sub": "",
            "dbus_ok": False,
            "current_min": None,
            "current_max": None,
            "sclk_actual": sclk,
            "governor_backend": preference,
        }
        init_manager = detect_init_manager()
        with daemon_governor_probe_budget(3):
            try:
                service_command = None
                if init_manager.kind == "openrc":
                    service_command = [
                        "rc-service",
                        service_key(str(spec["service"])),
                        "status",
                    ]
                elif init_manager.kind == "systemd":
                    service_command = [
                        "systemctl",
                        "show",
                        str(spec["service"]),
                        "--property=ActiveState,SubState",
                    ]
                if service_command is not None:
                    service = run_daemon_governor_probe(service_command)
                    if service.returncode == 0:
                        if init_manager.kind == "openrc":
                            result["service_active"] = parse_openrc_status(
                                service.returncode, service.stdout
                            )
                            result["service_sub"] = result["service_active"]
                        else:
                            properties = dict(
                                line.split("=", 1)
                                for line in service.stdout.splitlines()
                                if "=" in line
                            )
                            result["service_active"] = properties.get("ActiveState", "")
                            result["service_sub"] = properties.get("SubState", "")
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                pass
            # D-Bus is live runtime evidence. A process launched manually or
            # by an unimplemented supervisor remains observable even when its
            # boot-persistence state is unavailable.
            if preference == CYAN_GOVERNOR and (
                result["service_active"] == "active"
                or not init_manager.persistence_supported
            ):
                for property_name, key in (
                    ("Min", "current_min"),
                    ("Max", "current_max"),
                ):
                    try:
                        probe = run_daemon_governor_probe(
                            [
                                "busctl",
                                "get-property",
                                "com.cyanskillfish.Governor",
                                "/com/cyanskillfish/Governor/Range/Current",
                                self._GOVERNOR_RANGE_INTERFACE,
                                property_name,
                            ]
                        )
                        match = re.fullmatch(r"\s*(?:u|t|q)\s+(\d+)\s*", probe.stdout)
                        if probe.returncode == 0 and match:
                            value = int(match.group(1))
                            if 0 <= value <= 10_000:
                                result[key] = value
                    except (
                        OSError,
                        RuntimeError,
                        ValueError,
                        subprocess.SubprocessError,
                    ):
                        pass
        result["dbus_ok"] = (
            result["current_min"] is not None and result["current_max"] is not None
        )
        return result

    @staticmethod
    def _oberon_profile_voltages(minimum, maximum):
        """Use Oberon's documented two-endpoint baseline, never Cyan's curve."""
        return oberon_reference_endpoints(int(minimum), int(maximum))

    def _require_oberon_idle_transition(self, *, samples=3, interval=0.15):
        """Prove the GPU is idle before Oberon's service restart resets OPP 0.

        Oberon reloads both YAML endpoints by restarting its service.  Unlike a
        Cyan D-Bus range update, that restart immediately programs the minimum
        OPP, so doing it during 3D load can freeze the display.
        """
        gpu = self._gpu_device_path()
        if gpu is None:
            raise RuntimeError(
                "The AMD GPU sysfs device is unavailable. The Oberon profile was not changed."
            )
        required_samples = max(1, int(samples))
        observed = []
        attempts = 0
        # ``fdinfo`` is a delta counter: its first read establishes the
        # baseline and legitimately has no percentage yet. Permit exactly one
        # warm-up read while still requiring every accepted sample below to be
        # complete and idle.
        max_attempts = required_samples + 1
        while len(observed) < required_samples and attempts < max_attempts:
            attempts += 1
            busy = self._leer_entero(gpu / "gpu_busy_percent")
            if busy is None or not 0 <= int(busy) <= 100:
                busy = self._gpu_busy_fdinfo()
            live_clock, _voltage = self._gpu_hwmon_live_metrics(gpu)
            if live_clock is None:
                live_clock = self._parse_dpm_actual(
                    self._leer_texto(gpu / "pp_dpm_sclk")
                )
            if busy is None or live_clock is None:
                if busy is None and attempts < max_attempts:
                    time.sleep(max(0.0, float(interval)))
                    continue
                raise RuntimeError(
                    "GPU load or live clock telemetry is unavailable. The Oberon profile "
                    "was not changed; close 3D applications and refresh before retrying."
                )
            busy, live_clock = int(busy), int(live_clock)
            observed.append((busy, live_clock))
            if (
                busy > OBERON_IDLE_MAX_BUSY_PERCENT
                or live_clock > OBERON_IDLE_MAX_CLOCK_MHZ
            ):
                raise RuntimeError(
                    f"Oberon profile changes require an idle GPU (observed {busy}% load, "
                    f"{live_clock} MHz). Wait for the GPU to return to 1000 MHz, then retry."
                )
            if len(observed) < required_samples:
                time.sleep(max(0.0, float(interval)))
        return tuple(observed)

    def _restart_governor(self, service):
        """Restart one selected governor, including recovery from a failed start."""
        game_helper = getattr(self, "_usar_steamos_game_helper", lambda: False)
        if game_helper():
            self._ejecutar_steamos_game_helper("governor-restart", service, timeout=45)
            return
        command = (
            ["pkexec", "rc-service", service_key(service), "restart"]
            if detect_init_manager().kind == "openrc"
            else ["pkexec", "systemctl", "restart", service]
        )
        rc, out, err = self._ejecutar(command, timeout=30)
        if rc != 0:
            raise RuntimeError(err or out or f"{service} could not be restarted.")

    def _restart_governor_if_active(self, service):
        if not self._service_is_active(service):
            return False
        self._restart_governor(service)
        return True

    def asegurar_telemetria_gpu_cyan(self):
        """Validate Cyan telemetry without overriding either explicit switch."""
        telemetry = self._cyan_configuration_state()[-1]
        result = self._editar_governor_toml(
            "ensure-cyan-telemetry", bool(telemetry.get("fix_frequency"))
        )
        restarted = self._restart_governor_if_active(
            str(GOVERNOR_SPECS[CYAN_GOVERNOR]["service"])
        )
        self.estado_bc250_cache = None
        return result + (" Active Cyan service restarted." if restarted else "")

    def desactivar_fix_metricas_gpu_cyan(self):
        """Disable Cyan's optional metrics overlay without changing live clocks.

        Editing ``fix-metrics`` is configuration-only, but an active Cyan
        service must restart before the overlay disappears.  A restart can
        otherwise reset an operator's selected min/max clock range, so this
        follows the same read-before-write / restore-after-restart contract as
        the voltage and high-point operations.  If the current range cannot
        be read, leave both the file and service untouched.
        """
        service = str(GOVERNOR_SPECS[CYAN_GOVERNOR]["service"])
        was_active = self._service_is_active(service)
        previous_range = None
        if was_active:
            previous_range = self._leer_rango_governor("Current")
            if previous_range is None:
                raise RuntimeError(
                    "The active Cyan range could not be read through D-Bus. "
                    "The optional metrics overlay was not changed because "
                    "restarting now could reset the current GPU range."
                )
        result = self._editar_governor_toml("set-cyan-metrics-fix", False)
        if not was_active:
            self.estado_bc250_cache = None
            return (
                result + " Cyan is inactive; fix-metrics will remain disabled "
                "when the service is next started."
            )
        if not self._restart_governor_if_active(service):
            raise RuntimeError("The active Cyan governor could not be restarted.")
        restored = self._restaurar_rango_governor(previous_range)
        self.estado_bc250_cache = None
        return (
            f"{result} Runtime range preserved at "
            f"{restored[0]}-{restored[1]} MHz after the Cyan restart."
        )

    def _cyan_metrics_overlay_available(self):
        """Return whether this kernel exposes Cyan's bind-mount destination.

        ``fix-metrics`` is optional.  Enabling it when ``gpu_metrics`` is not
        exported makes upstream Cyan exit during startup, which turns a
        harmless telemetry option into a governor restart loop.  An unknown
        GPU path deliberately fails open: we only reject an explicit user choice when
        the running BC-250 device was positively observed without the file.
        """
        # A visible sysfs node is insufficient proof: some kernels expose the
        # path but reject Cyan's bind/move-mount operation.  A recent observed
        # runtime failure is authoritative and must win over the path probe.
        runtime = detect_cyan_metrics_fix_runtime(self, lookback_seconds=60)
        if runtime.get("metrics_fix_runtime_error"):
            return False
        gpu = self._gpu_device_path()
        if gpu is None:
            return None
        try:
            return (Path(gpu) / "gpu_metrics").is_file()
        except (OSError, TypeError, ValueError):
            return None

    def _cyan_kernel_usage_available(self):
        """Return whether Cyan's kernel load source has its required sysfs node."""
        gpu = self._gpu_device_path()
        if gpu is None:
            return None
        try:
            path = Path(gpu) / "gpu_busy_percent"
            if not path.is_file():
                return False
            value = int(path.read_text(encoding="ascii", errors="strict").strip())
            return 0 <= value <= 100
        except (OSError, TypeError, UnicodeError, ValueError):
            return False

    def _cyan_kernel_set_method_available(self):
        """Return whether Cyan's kernel backend covers its default 500-2000 range."""
        gpu = self._gpu_device_path()
        if gpu is None:
            return None
        try:
            voltage = Path(gpu) / "pp_od_clk_voltage"
            clocks = Path(gpu) / "pp_dpm_sclk"
            if not voltage.is_file() or not clocks.is_file():
                return False
            voltage_text = voltage.read_text(
                encoding="ascii", errors="strict"
            )
            clock_text = clocks.read_text(encoding="ascii", errors="strict")
            limits = re.search(
                r"(?m)^\s*SCLK:\s*(\d+)Mhz\s+(\d+)Mhz\s*$",
                voltage_text,
            )
            if limits is None or "*" not in clock_text:
                return False
            minimum, maximum = (int(value) for value in limits.groups())
            return minimum <= 500 and maximum >= 2000
        except (OSError, TypeError, UnicodeError, ValueError):
            return False

    def _current_cyan_compatibility(self):
        state = GovernorTomlEditor(
            self._cyan_runtime_config_path(require_managed=True)
        ).gpu_telemetry_state()
        if not state.get("valid"):
            raise RuntimeError(
                "The current Cyan compatibility values are invalid. Nothing was "
                "changed; repair config.toml before applying a new compatibility profile."
            )
        return (
            str(state["set_method"]),
            str(state["method"]),
            bool(state["fix_metrics"]),
            bool(state["fix_frequency"]),
        )

    def configurar_compatibilidad_gpu_cyan(
        self, set_method, usage_method, fix_metrics, fix_frequency
    ):
        """Apply Cyan's four compatibility switches without overriding user intent.

        ``set-method``, GPU usage ``method``, ``fix-metrics`` and ``fix-freq``
        are independent upstream controls. Control Center may reject a combination
        that is known to make the active runtime fail, but it must never silently
        rewrite one of the four switches to a different value.
        """
        service = str(GOVERNOR_SPECS[CYAN_GOVERNOR]["service"])
        previous_settings = self._current_cyan_compatibility()
        if bool(fix_metrics) and self._cyan_metrics_overlay_available() is False:
            raise RuntimeError(
                "fix-metrics was requested, but the active BC-250 kernel/runtime "
                "is known not to support Cyan's gpu_metrics overlay. Nothing was "
                "changed. Disable fix-metrics explicitly, or use a kernel that "
                "provides the required metrics target."
            )
        if (
            str(usage_method).strip().lower() == "kernel"
            and self._cyan_kernel_usage_available() is False
        ):
            raise RuntimeError(
                "gpu-usage.method=kernel was requested, but the active BC-250 "
                "kernel does not expose a readable gpu_busy_percent interface. "
                "Nothing was changed. Select busy-flag/process or boot a compatible "
                "patched kernel."
            )
        if (
            str(set_method).strip().lower() == "kernel"
            and self._cyan_kernel_set_method_available() is False
        ):
            raise RuntimeError(
                "gpu.set-method=kernel was requested, but the active BC-250 "
                "kernel does not expose readable pp_od_clk_voltage and "
                "pp_dpm_sclk interfaces covering Cyan's default 500-2000 MHz "
                "range. Nothing was changed. Select smu or boot a compatible "
                "patched kernel."
            )

        was_active = self._service_is_active(service)
        previous_range = None
        if was_active:
            previous_range = self._leer_rango_governor("Current")
            if previous_range is None:
                raise RuntimeError(
                    "The active Cyan range could not be read through D-Bus. "
                    "Compatibility settings were not changed because restarting "
                    "could reset the current GPU range."
                )
        result = self._editar_governor_toml(
            "set-cyan-compatibility",
            set_method,
            usage_method,
            bool(fix_metrics),
            bool(fix_frequency),
        )
        if not was_active:
            self.estado_bc250_cache = None
            return result + " Cyan is inactive; settings apply on its next start."
        try:
            if not self._restart_governor_if_active(service):
                raise RuntimeError("The active Cyan governor could not be restarted.")
            restored = self._restaurar_rango_governor(previous_range)
        except Exception as apply_error:
            try:
                self._editar_governor_toml(
                    "set-cyan-compatibility", *previous_settings
                )
                self._restart_governor(service)
                self._restaurar_rango_governor(previous_range)
            except Exception as rollback_error:
                raise RuntimeError(
                    "Cyan rejected the requested compatibility settings and the "
                    f"automatic rollback also failed: {rollback_error}"
                ) from apply_error
            raise RuntimeError(
                "Cyan rejected the requested compatibility settings. The previous "
                f"configuration and runtime range were restored: {apply_error}"
            ) from apply_error
        self.estado_bc250_cache = None
        return (
            f"{result} Runtime range preserved at "
            f"{restored[0]}-{restored[1]} MHz after the Cyan restart."
        )

    def _cyan_activation_dbus_repair_command(self):
        """Repair/reload the system-bus policy before starting Cyan.

        Cyan can run its SMU control loop while its optional D-Bus interface
        fails with AccessDenied if a freshly installed policy has not been
        reloaded yet. Activation is the user-facing boundary where Control
        Center must guarantee the complete governor contract, not merely that
        the systemd process is alive.
        """
        policy = Path("/etc/dbus-1/system.d/com.cyanskillfish.Governor.conf")
        source = None
        tool_dir = getattr(self, "_tool_dir", None)
        if callable(tool_dir):
            try:
                source = (
                    Path(tool_dir())
                    / "cyan-skillfish-governor-smu"
                    / "com.cyanskillfish.Governor.conf"
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                source = None
        qpolicy = shlex.quote(str(policy))
        policy_marker = shlex.quote('<allow own="com.cyanskillfish.Governor"/>')
        commands = [
            (
                "command -v busctl >/dev/null 2>&1 || "
                '{ echo "ERROR: busctl is required for Cyan D-Bus integration"; exit 62; }'
            ),
        ]
        if source is not None:
            qsource = shlex.quote(str(source))
            commands.append(
                f"if ! grep -Fq {policy_marker} {qpolicy} 2>/dev/null; then "
                f"test -f {qsource} || "
                '{ echo "ERROR: reviewed Cyan D-Bus policy source is missing; run Prepare dependencies"; exit 62; }; '
                f"sudo install -D -m 0644 {qsource} {qpolicy}; fi"
            )
        else:
            commands.append(
                f"grep -Fq {policy_marker} {qpolicy} 2>/dev/null || "
                '{ echo "ERROR: Cyan D-Bus policy is missing; run Prepare dependencies"; exit 62; }'
            )
        commands.append(
            "sudo busctl --system call org.freedesktop.DBus /org/freedesktop/DBus "
            "org.freedesktop.DBus ReloadConfig >/dev/null"
        )
        return "; ".join(commands)

    def _cyan_metrics_overlay_preflight_command(self):
        """Fail closed when an explicitly enabled metrics overlay cannot run.

        ``fix-metrics`` is a user-controlled compatibility switch.  Service
        activation must never rewrite it behind the user's back.  When the
        selected kernel is known to lack the required ``gpu_metrics`` target,
        or the current boot already recorded Cyan's stable overlay failure, the
        startup transaction stops before restarting Cyan and tells the user to
        disable the switch explicitly or choose a compatible kernel.
        """
        config = "/etc/cyan-skillfish-governor-smu/config.toml"
        return (
            'echo "[INFO] BC250 Cyan startup guard: validating explicit fix-metrics choice."; '
            'bc250_cyan_fix_metrics=0; '
            f'if grep -Eq "^[[:space:]]*fix-metrics[[:space:]]*=[[:space:]]*true([[:space:]]*(#.*)?)?$" {config}; then '
            'bc250_cyan_fix_metrics=1; fi; '
            'if [ "$bc250_cyan_fix_metrics" -eq 1 ]; then '
            'bc250_cyan_metrics_target=0; '
            'bc250_cyan_metrics_runtime_failed=0; '
            'for bc250_cyan_device in /sys/bus/pci/devices/*; do '
            '[ -r "$bc250_cyan_device/device" ] || continue; '
            'grep -qi "^0x13fe$" "$bc250_cyan_device/device" 2>/dev/null || continue; '
            '[ -f "$bc250_cyan_device/gpu_metrics" ] && bc250_cyan_metrics_target=1; '
            'done; '
            'if command -v journalctl >/dev/null 2>&1 && '
            'journalctl -b -u cyan-skillfish-governor-smu.service -n 120 --no-pager -o cat 2>/dev/null | '
            'grep -Eq "patched_gpu_metrics.*failed|GPU usage metrics fix write failed"; then '
            'bc250_cyan_metrics_runtime_failed=1; '
            'fi; '
            'if [ "$bc250_cyan_metrics_target" -eq 0 ] || [ "$bc250_cyan_metrics_runtime_failed" -eq 1 ]; then '
            'echo "ERROR: fix-metrics is enabled, but this kernel/runtime cannot provide Cyan gpu_metrics safely. Nothing was changed. Disable fix-metrics explicitly in GPU compatibility settings or use a compatible kernel."; '
            'exit 62; '
            'fi; '
            'fi;'
        )

    def controlar_governor(
        self, accion, confirmar_conflictos=False, desactivar_conflictos=False
    ):
        selected = self._selected_gpu_governor()
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            raise RuntimeError(
                f"GPU governor service management is not supported on {init_manager.display_name}. "
                "Live GPU telemetry and an already-running Cyan D-Bus range remain readable."
            )
        self._require_openrc_governor_preflight(selected)
        spec = GOVERNOR_SPECS[selected]
        servicio = str(spec["service"])
        if accion not in {"activar", "desactivar", "reiniciar"}:
            raise ValueError("Invalid governor action.")
        if not self._command_path(str(spec["binary"])):
            raise RuntimeError(
                f"{selected} is not installed. Use Prepare dependencies first."
            )
        conflicts = []
        prefix = ""
        if accion in {"activar", "reiniciar"}:
            conflicts = ensure_no_incompatible_governors(
                self,
                selected=selected,
                confirmed=bool(confirmar_conflictos or desactivar_conflictos),
            )
            if desactivar_conflictos and conflicts:
                prefix = (
                    self._comando_desactivar_gobernadores_incompatibles(conflicts)
                    + "; "
                )
        if accion == "activar":
            comando = self._governor_activation_command(selected, servicio, prefix)
        elif accion == "desactivar":
            # systemctl status intentionally returns 3 for a clean inactive
            # service.  Preserve the status report but do not make a successful
            # disable look like a failed workflow.
            if detect_init_manager().kind == "openrc":
                key = service_key(servicio)
                helper = shlex.quote(str(self._openrc_service_helper_path()))
                comando = (
                    f"set -e; sudo {helper} remove {key}; "
                    f"rc-service {key} status || true; "
                    f'echo "OK: {key} is disabled and inactive."'
                )
            else:
                comando = (
                    f"set -e; sudo systemctl disable --now {servicio}; "
                    f"systemctl status {servicio} --no-pager || true; "
                    f'echo "OK: {servicio} is disabled and inactive."'
                )
        else:
            comando = self._governor_restart_command(selected, servicio, prefix)
        self.estado_bc250_cache = None
        self.estado_herramientas_cache = None
        titles = {
            "activar": "Activar",
            "desactivar": "Desactivar",
            "reiniciar": "Reiniciar",
        }
        return self._abrir_terminal(comando, f"{titles[accion]} {selected}")

    @staticmethod
    def _cyan_dbus_wait_steps(service, failure_message):
        return (
            "bc250_cyan_dbus_ready=0;",
            "for bc250_cyan_dbus_attempt in {1..30}; do",
            "  if busctl --system status com.cyanskillfish.Governor >/dev/null 2>&1; then bc250_cyan_dbus_ready=1; break; fi;",
            "  sleep 0.1;",
            "done;",
            'if [ "$bc250_cyan_dbus_ready" -ne 1 ]; then',
            f"  journalctl -b -u {service} -n 80 --no-pager || true;",
            f'  echo "ERROR: {failure_message}";',
            "  exit 62;",
            "fi;",
            'echo "OK: Cyan service and D-Bus interface are active.";',
        )

    @staticmethod
    def _cyan_openrc_dbus_wait_steps(service, failure_message):
        """Wait for Cyan's bus name without assuming journald exists.

        A successful ``rc-service restart`` only proves that OpenRC launched
        the process.  GPU requests still fail if the process cannot acquire
        its system D-Bus name, so restart must verify the same contract as
        activation.  OpenRC installations may intentionally have no journal,
        therefore the failure diagnostic is limited to rc-service status.
        """
        key = service_key(service)
        return (
            "bc250_cyan_dbus_ready=0;",
            (
                "for bc250_cyan_dbus_attempt in {1..30}; do "
                "if busctl --system status com.cyanskillfish.Governor >/dev/null 2>&1; "
                "then bc250_cyan_dbus_ready=1; break; fi; sleep 0.1; done;"
            ),
            (
                '[ "$bc250_cyan_dbus_ready" -eq 1 ] || { '
                f'echo "ERROR: {failure_message}"; rc-service {key} status || true; exit 62; }};'
            ),
            'echo "OK: Cyan service and D-Bus interface are active.";',
        )

    def _governor_activation_command(self, selected, service, prefix):
        if detect_init_manager().kind == "openrc":
            key = service_key(service)
            helper = shlex.quote(str(self._openrc_service_helper_path()))
            steps = ["set -e;"]
            if selected == CYAN_GOVERNOR:
                steps.append(self._cyan_metrics_overlay_preflight_command())
                steps.append(self._cyan_activation_dbus_repair_command() + ";")
            steps.extend(
                (
                    f"sudo {helper} install {key};",
                    f"sudo rc-service {key} restart || sudo rc-service {key} start;",
                    f"if ! rc-service {key} status; then exit 1; fi;",
                )
            )
            if selected == CYAN_GOVERNOR:
                steps.extend(
                    self._cyan_openrc_dbus_wait_steps(
                        service,
                        "Cyan is running but its D-Bus name is unavailable after policy repair",
                    )
                )
            return prefix + " ".join(steps)
        steps = ["set -e;"]
        if selected == CYAN_GOVERNOR:
            steps.append(self._cyan_metrics_overlay_preflight_command())
            steps.append(self._cyan_activation_dbus_repair_command() + ";")
        steps.extend(
            (
                f"sudo systemctl unmask {service};",
                "sudo systemctl daemon-reload;",
                f"sudo systemctl reset-failed {service} 2>/dev/null || true;",
                f"sudo systemctl enable --now {service};",
            )
        )
        if selected == CYAN_GOVERNOR:
            steps.append(f"sudo systemctl restart {service};")
        steps.extend(
            (
                f"if ! systemctl is-active --quiet {service}; then",
                f"  systemctl status {service} --no-pager --full || true;",
                f"  journalctl -b -u {service} -n 80 --no-pager || true;",
                "  exit 1;",
                "fi;",
            )
        )
        if selected == CYAN_GOVERNOR:
            steps.extend(
                self._cyan_dbus_wait_steps(
                    service,
                    "Cyan is running but its D-Bus name is unavailable after policy repair",
                )
            )
        steps.append(f"systemctl status {service} --no-pager --full")
        return prefix + " ".join(steps)

    def _governor_restart_command(self, selected, service, prefix):
        if detect_init_manager().kind == "openrc":
            key = service_key(service)
            steps = [
                "set -e;",
                *(
                    [self._cyan_metrics_overlay_preflight_command()]
                    if selected == CYAN_GOVERNOR
                    else []
                ),
                *(
                    [self._cyan_activation_dbus_repair_command() + ";"]
                    if selected == CYAN_GOVERNOR
                    else []
                ),
                f"sudo rc-service {key} restart;",
                f"rc-service {key} status;",
            ]
            if selected == CYAN_GOVERNOR:
                steps.extend(
                    self._cyan_openrc_dbus_wait_steps(
                        service,
                        "Cyan restarted but its D-Bus name is unavailable after policy repair",
                    )
                )
            return prefix + " ".join(steps)
        if selected != CYAN_GOVERNOR:
            return prefix + (
                f"sudo systemctl restart {service}; "
                f"systemctl status {service} --no-pager"
            )
        steps = [
            "set -e;",
            self._cyan_metrics_overlay_preflight_command(),
            self._cyan_activation_dbus_repair_command() + ";",
            f"sudo systemctl restart {service};",
            *self._cyan_dbus_wait_steps(
                service,
                "Cyan restarted but its D-Bus name is unavailable after policy repair",
            ),
            f"systemctl status {service} --no-pager --full",
        ]
        return prefix + " ".join(steps)

    def _governor_config_helper_path(self):
        candidates = (
            Path("/usr/libexec/bc250-control-center/bc250-governor-config-helper"),
            Path(
                "/usr/local/libexec/bc250-control-center/bc250-governor-config-helper"
            ),
        )
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if not os.access(candidate, os.X_OK):
                continue
            try:
                source = candidate.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeError):
                continue
            if (
                governor_config_helper_protocol(source)
                != GOVERNOR_CONFIG_HELPER_PROTOCOL
            ):
                continue
            return str(candidate)
        return ""

    def _cyan_runtime_identity(self):
        return detect_cyan_runtime_identity(self)

    def _cyan_runtime_config_path(self, *, require_managed=False):
        if not callable(getattr(self, "_ejecutar", None)):
            path = Path(self._GOVERNOR_CONFIG)
        else:
            identity = self._cyan_runtime_identity()
            path = Path(str(identity.get("config_path") or self._GOVERNOR_CONFIG))
        if require_managed and path != self._GOVERNOR_CONFIG:
            raise RuntimeError(
                "The active Cyan service is using a different TOML than BC250 Control Center "
                f"manages: {path}. Expected {self._GOVERNOR_CONFIG}. Run Prepare dependencies "
                "to repair the service/config binding before editing GPU settings."
            )
        return path

    def _require_cyan_runtime_for_live_control(self):
        """Require the reviewed BC250CC Cyan runtime on Bazzite live writes."""

        family = ""
        os_repository_factory = getattr(self, "_os_repository", None)
        if callable(os_repository_factory):
            try:
                family = str(os_repository_factory().info.family or "").lower()
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                family = ""
        if family != "bazzite":
            return self._cyan_runtime_identity()

        identity = self._cyan_runtime_identity()
        if not identity.get("config_matches_managed_path"):
            raise RuntimeError(
                "Bazzite Cyan is running with a TOML that BC250 Control Center does not manage. "
                "Run Prepare dependencies to repair the service/config binding before changing GPU frequency."
            )
        if not identity.get("runtime_bc250cc_verified"):
            raise RuntimeError(
                "Bazzite GPU control requires the reviewed BC250CC Cyan runtime. "
                "Run Prepare dependencies to build and verify the managed Cyan runtime before applying a live GPU range."
            )
        return identity

    def _editar_governor_toml(self, action, *arguments):
        request = plan_governor_config_request(action, arguments)
        if action != "set-oberon-operating-points":
            self._cyan_runtime_config_path(require_managed=True)
        game_helper = getattr(self, "_usar_steamos_game_helper", lambda: False)
        if game_helper():
            result = self._ejecutar_steamos_game_helper(
                "governor-config",
                request.action,
                *request.arguments,
                timeout=120,
            )
            self.estado_bc250_cache = None
            return result
        helper = self._governor_config_helper_path()
        if not helper:
            raise RuntimeError(
                "The privileged governor configuration helper is not installed. "
                "Reinstall BC250 Control Center locally or from its package before editing /etc."
            )
        rc, out, err = self._ejecutar(request.argv(helper), timeout=120)
        if rc != 0:
            raise RuntimeError(
                err or out or f"Governor configuration helper exited with code {rc}."
            )
        self.estado_bc250_cache = None
        return (out or "").strip()

    def _frequency_range_state(self):
        return GovernorTomlEditor(
            self._cyan_runtime_config_path()
        ).frequency_range_state()

    def _cyan_high_points_enabled(self):
        return bool(
            GovernorTomlEditor(self._cyan_runtime_config_path())
            .high_frequency_state()
            .get("enabled")
        )

    def _cyan_set_method(self) -> str:
        try:
            state = GovernorTomlEditor(
                self._cyan_runtime_config_path()
            ).gpu_telemetry_state()
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeError(
                "The Cyan GPU backend could not be validated before changing frequency."
            ) from error
        method = str(state.get("set_method") or "").strip().lower()
        if method not in {"smu", "kernel"}:
            raise RuntimeError("Cyan gpu.set-method must be smu or kernel.")
        return method

    def aplicar_perfil_gpu(self, minimo, maximo):
        """Apply a live GPU profile without rewriting persistent TOML limits.

        Runtime range and persistent configuration are intentionally separate.
        The TOML high-point switch only controls which safe-points Cyan can load;
        an explicit profile remains a D-Bus operation.
        """
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            return self.aplicar_rango_bc250(minimo, maximo)
        minimo, maximo = int(minimo), int(maximo)
        self._require_cyan_runtime_for_live_control()
        self._ensure_cyan_frequency_range_loaded(minimo, maximo)
        return self._apply_cyan_runtime_range(minimo, maximo)

    def _ensure_cyan_frequency_range_loaded(self, minimo: int, maximo: int) -> None:
        """Ensure the running Cyan process has loaded a requested high point.

        Enabling >2000 MHz points is intentionally a TOML-only operation.  Both
        adaptive and fixed requests therefore share this one reload gate so a
        fixed 2200 MHz request cannot fail merely because the service still has
        the old Allowed table in memory.
        """
        minimo, maximo = int(minimo), int(maximo)
        allowed = self._leer_rango_governor("Allowed")
        if allowed is None:
            raise RuntimeError(
                "Cyan D-Bus Allowed range is unavailable. Refresh the governor "
                "status before applying a GPU frequency."
            )
        if int(allowed[0]) <= minimo <= maximo <= int(allowed[1]):
            return
        if minimo < int(allowed[0]):
            raise ValueError(
                f"{minimo} MHz is below Cyan's active minimum of {allowed[0]} MHz."
            )
        high_state = GovernorTomlEditor(
            self._cyan_runtime_config_path()
        ).high_frequency_state()
        enabled = tuple(
            int(value) for value in high_state.get("enabled_frequencies") or ()
        )
        if maximo <= 2000 or not enabled or maximo > max(enabled):
            raise ValueError(
                f"{maximo} MHz is not loaded by Cyan. Enable the advanced TOML "
                "safe-points first, then apply the frequency again."
            )
        self._reload_cyan_for_high_range(minimo, maximo)

    def _reload_cyan_for_high_range(self, minimo: int, maximo: int) -> None:
        """Reload Cyan only when a newly enabled TOML safe-point is not live.

        A service restart here is a configuration reload, not a frequency-state
        workaround. Normal upward SetRange/SetFixedFrequency transitions never
        restart Cyan in the redesigned runtime.
        """
        service = self._GOVERNOR_SERVICE
        if not self._service_is_active(service):
            raise RuntimeError(
                "Cyan is not active, so its newly enabled high safe-points are not "
                "loaded yet. Start the governor, refresh its status, then apply the "
                "selected range again."
            )
        # If this Cyan process already loaded the high table, avoid a needless
        # restart and the brief stale D-Bus window it creates.
        allowed = self._leer_rango_governor("Allowed")
        if (
            allowed is not None
            and int(allowed[0]) <= int(minimo) <= int(allowed[1])
            and int(allowed[0]) <= int(maximo) <= int(allowed[1])
        ):
            return
        self._restart_governor_if_active(service)
        deadline = time.monotonic() + 8.0
        last_allowed = None
        while time.monotonic() < deadline:
            allowed = self._leer_rango_governor("Allowed")
            last_allowed = allowed
            if (
                allowed is not None
                and int(allowed[0]) <= int(minimo) <= int(allowed[1])
                and int(allowed[0]) <= int(maximo) <= int(allowed[1])
            ):
                return
            time.sleep(0.15)
        raise RuntimeError(
            "Cyan restarted but D-Bus did not expose the requested "
            f"{minimo}-{maximo} MHz high safe-point range (allowed {last_allowed!r}). "
            "The TOML was saved; inspect the governor service status before retrying."
        )

    def fijar_piso_gpu_persistente(self, minimo):
        """Persist only the governor floor without creating a hidden ceiling.

        ``frequency-range.max = 0`` is the upstream spelling for *no maximum
        limit*.  We deliberately do not send a D-Bus range here: changing a
        persistent floor must not silently replace the user's current runtime
        maximum or selected profile midway through a game.
        """
        try:
            floor = int(minimo)
        except (TypeError, ValueError) as error:
            raise ValueError("GPU frequency floor must be an integer.") from error
        if floor < 0:
            raise ValueError("GPU frequency floor cannot be negative.")
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            try:
                state = OberonYamlEditor(
                    GOVERNOR_SPECS[OBERON_GOVERNOR]["config_path"]
                ).state()
            except (OSError, RuntimeError, ValueError) as error:
                raise RuntimeError(
                    "The Oberon YAML could not be validated; no frequency was changed."
                ) from error
            maximum = int(state["frequency_max"])
            if floor > maximum:
                raise ValueError(
                    f"GPU frequency floor {floor} MHz exceeds the current Oberon "
                    f"maximum of {maximum} MHz."
                )
            floor, maximum = require_oberon_safe_profile(floor, maximum)
            minimum_voltage, maximum_voltage = self._oberon_profile_voltages(
                floor, maximum
            )
            self._require_oberon_idle_transition()
            result = self._editar_governor_toml(
                "set-oberon-operating-points",
                floor,
                maximum,
                minimum_voltage,
                maximum_voltage,
            )
            restarted = self._restart_governor_if_active(
                str(GOVERNOR_SPECS[OBERON_GOVERNOR]["service"])
            )
            self.estado_bc250_cache = None
            return (
                f"{result} Oberon minimum set to {floor} MHz; maximum remained "
                f"{maximum} MHz. "
                + (
                    "The active service was restarted."
                    if restarted
                    else "It will load when the service next starts."
                )
            )
        allowed = self._leer_rango_governor("Allowed")
        if allowed is not None and not allowed[0] <= floor <= allowed[1]:
            raise ValueError(
                f"GPU frequency floor {floor} MHz is outside the allowed "
                f"{allowed[0]}-{allowed[1]} MHz range."
            )
        result = self._editar_governor_toml("set-frequency-floor", floor)
        self.estado_bc250_cache = None
        return (
            f"{result} Persistent floor set to {floor} MHz; the active custom "
            "maximum was preserved, or profile mode remained unlimited. Restart "
            "the governor or reboot to load it."
        )

    def _validar_curva_oc_alta(self, maximo):
        """Validate only invariants Cyan itself requires.

        Frequencies above 2000 MHz are experimental but are no longer blocked by
        Control Center-specific voltage profiles. Cyan supports interpolation
        between valid safe-points, so the requested maximum does not need to be
        an exact table entry. Stability remains a board-specific warning in the UI.
        """
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            return
        try:
            diagnostics = GovernorTomlEditor(
                self._cyan_runtime_config_path()
            ).safe_point_diagnostics()
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeError(
                "The governor TOML could not be validated before changing GPU frequency."
            ) from error
        if diagnostics.get("duplicate_frequencies"):
            raise RuntimeError(
                "The Cyan TOML contains duplicate active safe-point frequencies."
            )
        if diagnostics.get("missing_voltage"):
            raise RuntimeError("Every active Cyan safe-point must define a voltage.")
        if diagnostics.get("voltage_order_errors"):
            raise RuntimeError(
                "The active Cyan voltage curve decreases as frequency rises."
            )

    def _leer_rango_governor(self, kind):
        if kind not in {"Current", "Allowed"}:
            raise ValueError("Invalid governor range kind.")
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            if kind == "Allowed":
                return 1000, 2000
            try:
                state = OberonYamlEditor(
                    GOVERNOR_SPECS[OBERON_GOVERNOR]["config_path"]
                ).state()
            except (OSError, RuntimeError, ValueError):
                return None
            return int(state["frequency_min"]), int(state["frequency_max"])
        objeto = f"/com/cyanskillfish/Governor/Range/{kind}"
        minimo = self._dbus_uint_property(
            objeto,
            self._GOVERNOR_RANGE_INTERFACE,
            "Min",
        )
        maximo = self._dbus_uint_property(
            objeto,
            self._GOVERNOR_RANGE_INTERFACE,
            "Max",
        )
        if minimo is None or maximo is None or minimo > maximo:
            return None
        return int(minimo), int(maximo)

    def _esperar_rango_governor(self, expected, *, timeout=1.5):
        expected = int(expected[0]), int(expected[1])
        deadline = time.monotonic() + max(0.1, float(timeout))
        current = None
        while time.monotonic() < deadline:
            current = self._leer_rango_governor("Current")
            if current == expected:
                return current
            time.sleep(0.05)
        return current

    def _require_cyan_runtime_range_ready(self):
        """Block a new live request while Cyan is still recovering its D-Bus API.

        A voltage-curve transaction restarts Cyan and restores the previous
        range before it returns.  If that transaction reports a failure, the
        system-bus objects can still be absent while SteamOS retries the
        hwmon/fix-freq path.  Sending another SetRange at that point only
        produces a second, less useful failure and obscures the first one.
        """
        current = self._leer_rango_governor("Current")
        if current is None:
            raise RuntimeError(
                "Cyan D-Bus runtime range is not ready after a governor restart. "
                "Wait for Cyan to recover, then refresh GPU status before applying a new range."
            )
        return current

    @staticmethod
    def _limitar_rango_governor(previous, allowed):
        minimo_anterior, maximo_anterior = (int(previous[0]), int(previous[1]))
        minimo_permitido, maximo_permitido = (int(allowed[0]), int(allowed[1]))
        minimo = max(minimo_permitido, min(minimo_anterior, maximo_permitido))
        maximo = max(minimo_permitido, min(maximo_anterior, maximo_permitido))
        minimo = min(minimo, maximo)
        return minimo, maximo

    def _restaurar_rango_governor(self, previous, *, timeout=6.0):
        deadline = time.monotonic() + max(0.5, float(timeout))
        last_error = "D-Bus range objects did not become ready."
        while time.monotonic() < deadline:
            allowed = self._leer_rango_governor("Allowed")
            if allowed is None:
                time.sleep(0.15)
                continue
            minimo, maximo = self._limitar_rango_governor(previous, allowed)
            rc, out, err = self._ejecutar(
                [
                    "busctl",
                    "call",
                    "com.cyanskillfish.Governor",
                    "/com/cyanskillfish/Governor",
                    "com.cyanskillfish.Governor.PerformanceMode",
                    "SetRange",
                    "uu",
                    str(minimo),
                    str(maximo),
                ],
                timeout=5,
            )
            if rc != 0:
                last_error = err or out or "busctl SetRange failed."
                time.sleep(0.15)
                continue
            current = self._leer_rango_governor("Current")
            if current == (minimo, maximo):
                return current
            last_error = (
                f"The governor reported {current!r} after requesting "
                f"{minimo}-{maximo} MHz."
            )
            time.sleep(0.15)
        raise RuntimeError(
            "The governor restarted, but its previous runtime range could not "
            f"be restored safely. {last_error} Do not start a GPU workload; "
            "apply a known-safe range first."
        )

    def alternar_puntos_gpu_altos(self, enabled):
        """Edit the experimental table without changing the live GPU range.

        Cyan derives its startup range from the active TOML points.  Restarting
        it immediately after exposing a 2400 MHz point can therefore request
        500-2400 MHz before the operator has pressed an explicit Apply
        action.  The high-point switch is intentionally configuration-only:
        it makes validated choices available to the UI, while D-Bus range
        changes remain exclusively behind the range-apply actions.
        """
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            raise RuntimeError(
                "Oberon Governor has no multipoint safe-point table. Set its "
                "validated maximum directly with Apply range instead."
            )
        action = "enable-high-points" if bool(enabled) else "disable-high-points"
        # Enabling is a pure file edit.  Do not require a working D-Bus
        # session just to expose choices; it cannot affect the running GPU.
        if not enabled:
            was_active = self._service_is_active(self._GOVERNOR_SERVICE)
        else:
            was_active = False
        if was_active:
            current_range = self._leer_rango_governor("Current")
            if current_range is None:
                raise RuntimeError(
                    "The active governor range could not be read through D-Bus. "
                    "The +2000 MHz points were not changed because the live "
                    "range cannot be verified."
                )
            if not enabled and int(current_range[1]) > 2000:
                raise RuntimeError(
                    "Apply a range at or below 2000 MHz before disabling the "
                    "+2000 MHz TOML points. The live GPU range was not changed."
                )
        result = self._editar_governor_toml(action)
        self.estado_bc250_cache = None
        return (
            f"{result} The live GPU range and Cyan service were not changed. "
            "Select a safe-point and use Apply active range to request any new range."
        )

    def status_governor(self):
        selected = self._selected_gpu_governor()
        spec = GOVERNOR_SPECS[selected]
        servicio = str(spec["service"])
        if not self._command_path(str(spec["binary"])):
            raise RuntimeError(
                f"{selected} is not installed. Use Prepare dependencies first."
            )
        init_manager = detect_init_manager()
        if not init_manager.persistence_supported:
            return init_manager.persistence_detail
        command = (
            ["rc-service", service_key(servicio), "status"]
            if init_manager.kind == "openrc"
            else ["systemctl", "status", servicio, "--no-pager"]
        )
        _rc, out, err = self._ejecutar(command, timeout=8)
        texto = (out or err or "").strip()
        if not texto:
            texto = f"{'rc-service' if init_manager.kind == 'openrc' else 'systemctl'} status {servicio} returned no output."
        return texto

    def abrir_laboratorio_voltaje_gpu(self):
        script = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "bc250-gpu-voltage-lab.sh"
        )
        if not script.exists():
            raise RuntimeError(f"GPU voltage lab was not found at {script}")
        return self._abrir_terminal(
            shlex.quote(str(script)) + " menu", "BC250 GPU Voltage Lab"
        )

    def aplicar_laboratorio_voltaje_gpu(self, nivel):
        nivel = int(nivel)
        if nivel not in SUPPORTED_VOLTAGE_LEVELS:
            raise ValueError("Invalid lab level. Use 0, 3 or 6.")
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            raise RuntimeError(
                "Oberon voltage editing is unavailable. Its two OPP endpoints do not "
                "provide a validated cross-board voltage curve; use an Oberon frequency "
                "profile while idle, or use Cyan for the voltage laboratory."
            )
        if self._usar_steamos_game_helper():
            salida = self._ejecutar_steamos_game_helper(
                "gpu-voltage", "apply", nivel, timeout=420
            )
            self.estado_bc250_cache = None
            self.estado_herramientas_cache = None
            return salida
        return self._apply_cyan_voltage_edit("set-cyan-voltage-level", nivel)

    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        if not valores:
            raise ValueError("No custom values to apply.")
        normalized = {}
        for frecuencia, voltaje in valores.items():
            frecuencia = int(frecuencia)
            voltaje = int(voltaje)
            if frecuencia <= 0:
                raise ValueError(f"Invalid safe-point frequency: {frecuencia}")
            if voltaje < CUSTOM_VOLTAGE_MIN_MV or voltaje > CUSTOM_VOLTAGE_MAX_MV:
                raise ValueError(
                    f"Voltage outside editor range for {frecuencia}: {voltaje} mV. "
                    f"Allowed: {CUSTOM_VOLTAGE_MIN_MV}..{CUSTOM_VOLTAGE_MAX_MV} mV"
                )
            previous = normalized.get(frecuencia)
            if previous is not None and previous != voltaje:
                raise ValueError(
                    "A GPU frequency cannot have conflicting voltage values."
                )
            normalized[frecuencia] = voltaje
        partes = [
            f"{frecuencia}={normalized[frecuencia]}"
            for frecuencia in sorted(normalized)
        ]
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            raise RuntimeError(
                "Oberon voltage editing is unavailable. Its two OPP endpoints do not "
                "provide a validated cross-board voltage curve; use an Oberon frequency "
                "profile while idle, or use Cyan for the voltage laboratory."
            )
        if self._usar_steamos_game_helper():
            salida = self._ejecutar_steamos_game_helper(
                "gpu-voltage", "apply-custom", *partes, timeout=420
            )
            self.estado_bc250_cache = None
            self.estado_herramientas_cache = None
            return salida
        return self._apply_cyan_voltage_edit("set-cyan-custom-voltages", *partes)

    def _apply_cyan_voltage_edit(self, action, *arguments):
        """Edit Cyan through the root-owned helper and preserve its live range."""
        service = self._GOVERNOR_SERVICE
        if not self._service_is_active(service):
            raise RuntimeError(
                "The Cyan governor must be active before changing its voltage curve."
            )
        previous_range = self._leer_rango_governor("Current")
        if previous_range is None:
            raise RuntimeError(
                "The active governor range could not be read through D-Bus. "
                "The voltage curve was not changed."
            )
        result = self._editar_governor_toml(action, *arguments)
        if not self._restart_governor_if_active(service):
            raise RuntimeError("The active Cyan governor could not be restarted.")
        restored = self._restaurar_rango_governor(previous_range)
        self.estado_bc250_cache = None
        return (
            f"{result} Runtime range preserved at "
            f"{restored[0]}-{restored[1]} MHz after the governor restart."
        )

    @staticmethod
    def _unavailable_range(error):
        return {
            "present": False,
            "enabled": False,
            "valid": False,
            "mode": "unavailable",
            "min": None,
            "max": None,
            "error": str(error),
        }

    def _safe_points_config(self):
        path = self._cyan_runtime_config_path()
        try:
            diagnostics = GovernorTomlEditor(path).safe_point_diagnostics()
            diagnostics["error"] = ""
        except (GovernorTomlError, OSError, TypeError, ValueError) as error:
            diagnostics = {
                "points": [],
                "points_with_voltage": [],
                "max_frequency": None,
                "max_voltage": None,
                "missing_voltage": [],
                "voltage_order_errors": [],
                "duplicate_frequencies": [],
                "error": str(error),
            }
        diagnostics["config_path"] = str(path)
        return diagnostics

    def _oberon_configuration_state(self, selected_spec):
        """Read Oberon's two endpoint OPPs without leaking YAML failures."""
        try:
            oberon_state = OberonYamlEditor(selected_spec["config_path"]).state()
        except (OberonYamlError, OSError, TypeError, ValueError) as error:
            return (
                None,
                {
                    "points": (),
                    "points_with_voltage": (),
                    "max_frequency": None,
                    "max_voltage": None,
                    "missing_voltage": (),
                    "voltage_order_errors": (),
                    "duplicate_frequencies": (),
                    "config_path": str(selected_spec["config_path"]),
                },
                self._unavailable_range(error),
                {
                    "available": False,
                    "frequencies": (),
                    "enabled_frequencies": (),
                    "enabled": False,
                },
                {},
            )

        points = tuple(
            {
                "frequency": int(oberon_state[f"frequency_{bound}"]),
                "voltage": int(oberon_state[f"voltage_{bound}"]),
            }
            for bound in ("min", "max")
        )
        safe_info = {
            "points": points,
            "points_with_voltage": points,
            "max_frequency": max(point["frequency"] for point in points),
            "max_voltage": max(point["voltage"] for point in points),
            "missing_voltage": (),
            "voltage_order_errors": (),
            "duplicate_frequencies": (),
            "config_path": str(selected_spec["config_path"]),
        }
        frequency_range = {
            "present": True,
            "enabled": True,
            "valid": True,
            "mode": "custom",
            "min": int(oberon_state["frequency_min"]),
            "max": int(oberon_state["frequency_max"]),
            "error": ""
            if oberon_state["safe_voltage"]
            else (f"Oberon contains voltage below {OBERON_SAFE_VOLTAGE_MIN_MV} mV."),
        }
        high_points = {
            "available": False,
            "frequencies": (),
            "enabled_frequencies": (),
            "enabled": False,
        }
        return oberon_state, safe_info, frequency_range, high_points, {}

    def _cyan_configuration_state(self):
        """Read all Cyan files defensively while keeping telemetry usable."""
        safe_info = self._safe_points_config()
        editor = GovernorTomlEditor(safe_info["config_path"])
        try:
            telemetry = editor.gpu_telemetry_state()
        except (GovernorTomlError, OSError, TypeError, ValueError) as error:
            telemetry = {
                "fix_metrics": False,
                "fix_frequency": False,
                "method": "",
                "valid": False,
                "error": str(error),
            }
        runtime = detect_cyan_frequency_fix_runtime(self)
        runtime.update(detect_cyan_metrics_fix_runtime(self))
        identity = self._cyan_runtime_identity()
        telemetry.update(
            {
                "runtime_config_path": str(identity.get("config_path") or ""),
                "runtime_config_matches_managed_path": bool(
                    identity.get("config_matches_managed_path")
                ),
                "runtime_version": str(identity.get("version") or ""),
                "runtime_binary_sha256": str(identity.get("binary_sha256") or ""),
                "runtime_revision": str(identity.get("runtime_revision") or ""),
                "runtime_upstream_commit": str(
                    identity.get("runtime_upstream_commit") or ""
                ),
                "runtime_hash_matches": bool(identity.get("runtime_hash_matches")),
                "runtime_bc250cc_verified": bool(
                    identity.get("runtime_bc250cc_verified")
                ),
                "runtime_binary": runtime.get("binary_path", ""),
                "runtime_frequency_fix_supported": bool(
                    runtime.get("supports_frequency_fix")
                ),
                "runtime_managed_override": bool(runtime.get("managed_override")),
                "runtime_metrics_fix_error": bool(
                    runtime.get("metrics_fix_runtime_error")
                ),
            }
        )
        try:
            high_points = editor.high_frequency_state()
        except (GovernorTomlError, OSError, TypeError, ValueError):
            high_points = {
                "available": False,
                "frequencies": (),
                "enabled_frequencies": (),
                "enabled": False,
            }
        try:
            frequency_range = editor.frequency_range_state()
        except (GovernorTomlError, OSError, TypeError, ValueError) as error:
            frequency_range = self._unavailable_range(error)
        return None, safe_info, frequency_range, high_points, telemetry

    def _governor_runtime_state(
        self,
        selected_governor,
        selected_spec,
        oberon_state,
    ):
        selected_binary = str(selected_spec["binary"])
        if not self._command_path(selected_binary):
            return {
                "service_active": "not-found",
                "service_sub": "",
                "service_enabled": "not-found",
                "service_main_pid": 0,
                "current_min": None,
                "current_max": None,
                "allowed_min": None,
                "allowed_max": None,
                "dbus_performance": None,
            }

        service = str(selected_spec["service"])
        state = {
            "service_active": self._service_prop(service, "ActiveState"),
            "service_sub": self._service_prop(service, "SubState"),
            "service_enabled": self._service_prop(service, "UnitFileState"),
            "service_main_pid": self._service_prop(service, "MainPID"),
        }
        if selected_governor == OBERON_GOVERNOR:
            state.update(
                {
                    "current_min": int(oberon_state["frequency_min"])
                    if oberon_state
                    else None,
                    "current_max": int(oberon_state["frequency_max"])
                    if oberon_state
                    else None,
                    "allowed_min": 1000,
                    "allowed_max": 2000,
                    "dbus_performance": None,
                }
            )
            return state

        current_obj = "/com/cyanskillfish/Governor/Range/Current"
        allowed_obj = "/com/cyanskillfish/Governor/Range/Allowed"
        interface = self._GOVERNOR_RANGE_INTERFACE
        state.update(
            {
                "current_min": self._dbus_uint_property(current_obj, interface, "Min"),
                "current_max": self._dbus_uint_property(current_obj, interface, "Max"),
                "allowed_min": self._dbus_uint_property(allowed_obj, interface, "Min"),
                "allowed_max": self._dbus_uint_property(allowed_obj, interface, "Max"),
                "dbus_performance": self._dbus_bool_property(
                    "/com/cyanskillfish/Governor",
                    "com.cyanskillfish.Governor.PerformanceMode",
                    "Enabled",
                ),
            }
        )
        return state

    def _gpu_device_evidence(self, gpu):
        """Read one coherent sysfs sample without mixing governor decisions."""
        if not gpu:
            return GpuDeviceEvidence(
                path="",
                device=None,
                vendor=None,
                sclk_text="",
                mclk_text="",
                sclk_actual=None,
                mclk_actual=None,
                voltage_actual=None,
                od_sclk_min=None,
                od_sclk_max=None,
                busy=self._gpu_busy_percent(None),
                vram_total=None,
                vram_used=None,
                power_level=None,
                power_state=None,
            )
        sclk_text = self._leer_texto(gpu / "pp_dpm_sclk")
        mclk_text = self._leer_texto(gpu / "pp_dpm_mclk")
        od = self._parse_od(self._leer_texto(gpu / "pp_od_clk_voltage"))
        hwmon_sclk, hwmon_vddgfx = self._gpu_hwmon_live_metrics(gpu)
        return GpuDeviceEvidence(
            path=str(gpu),
            device=self._leer_texto(gpu / "device"),
            vendor=self._leer_texto(gpu / "vendor"),
            sclk_text=sclk_text or "",
            mclk_text=mclk_text or "",
            # Only the active DPM entry is a valid fallback. OD describes
            # configured limits and must never masquerade as a live clock.
            sclk_actual=(
                hwmon_sclk
                if hwmon_sclk is not None
                else self._parse_dpm_actual(sclk_text)
            ),
            mclk_actual=self._parse_dpm_actual(mclk_text),
            voltage_actual=(
                hwmon_vddgfx if hwmon_vddgfx is not None else od.get("vddc")
            ),
            od_sclk_min=od.get("range_sclk_min"),
            od_sclk_max=od.get("range_sclk_max"),
            busy=self._gpu_busy_percent(gpu),
            vram_total=self._leer_entero(gpu / "mem_info_vram_total"),
            vram_used=self._leer_entero(gpu / "mem_info_vram_used"),
            power_level=self._leer_texto(gpu / "power_dpm_force_performance_level"),
            power_state=self._leer_texto(gpu / "power_dpm_state"),
        )

    def _gpu_hwmon_live_metrics(self, gpu):
        """Return live SCLK MHz and VDDGFX mV from the GPU's amdgpu hwmon.

        The kernel hwmon ABI reports ``freq*_input`` in Hz and ``in*_input``
        in mV.  Labels, rather than fixed indexes, keep this correct across
        board layouts.  Invalid or partial sensors are ignored so callers can
        retain their DPM/OD fallback.
        """
        sclk = read_hwmon_clock_mhz(gpu)
        vddgfx = None
        for hwmon in sorted((Path(gpu) / "hwmon").glob("hwmon*")):
            if not hwmon.is_dir():
                continue
            for label_path in sorted(hwmon.glob("*_label")):
                label = (self._leer_texto(label_path) or "").strip().lower()
                input_path = label_path.with_name(
                    label_path.name.replace("_label", "_input")
                )
                value = self._leer_entero(input_path)
                if value is None:
                    continue
                if label == "sclk" and 100_000_000 <= value <= 5_000_000_000:
                    sclk = round(value / 1_000_000)
                elif label == "vddgfx":
                    # hwmon voltage inputs are mV. Accept microvolt-form
                    # values too for compatible non-SteamOS kernels.
                    millivolts = value // 1000 if value > 10_000 else value
                    if 400 <= millivolts <= 1_500:
                        vddgfx = millivolts
        return sclk, vddgfx

    def estado_bc250(self):
        ahora = time.monotonic()
        if (
            self.estado_bc250_cache is not None
            and ahora - self.estado_bc250_cache_time < 1.5
        ):
            return dict(self.estado_bc250_cache)
        gpu = self._gpu_device_path()
        device_evidence = self._gpu_device_evidence(gpu)
        governor_context = self._gpu_governor_context()
        selected_governor = str(governor_context["selected"])
        selected_spec = GOVERNOR_SPECS[selected_governor]
        if selected_governor == OBERON_GOVERNOR:
            config_state = self._oberon_configuration_state(selected_spec)
        else:
            config_state = self._cyan_configuration_state()
        oberon_state, safe_info, frequency_range, high_points, cyan_telemetry = (
            config_state
        )
        tools = self.estado_herramientas_bc250()
        runtime = self._governor_runtime_state(
            selected_governor, selected_spec, oberon_state
        )
        governor_evidence = GpuGovernorEvidence(
            selected=selected_governor,
            context=governor_context,
            runtime=runtime,
            safe_points=safe_info,
            frequency_range=frequency_range,
            high_frequency_points=high_points,
            cyan_telemetry=cyan_telemetry,
            tools=tools,
        )
        resultado = build_gpu_state_snapshot(device_evidence, governor_evidence)
        self.estado_bc250_cache = resultado
        self.estado_bc250_cache_time = ahora
        return dict(resultado)

    def aplicar_rango_bc250(self, minimo, maximo):
        self.estado_bc250_cache = None
        minimo = int(minimo)
        maximo = int(maximo)
        if minimo > maximo:
            raise ValueError("GPU minimum frequency cannot exceed maximum frequency.")
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            minimo, maximo = require_oberon_safe_profile(minimo, maximo)
            self._require_oberon_idle_transition()
            minimum_voltage, maximum_voltage = self._oberon_profile_voltages(
                minimo, maximo
            )
            result = self._editar_governor_toml(
                "set-oberon-operating-points",
                minimo,
                maximo,
                minimum_voltage,
                maximum_voltage,
            )
            restarted = self._restart_governor_if_active(
                str(GOVERNOR_SPECS[OBERON_GOVERNOR]["service"])
            )
            self.estado_bc250_cache = None
            state = self.estado_bc250()
            state["operation_message"] = result + (
                " Active Oberon service restarted."
                if restarted
                else " Oberon will load the range when its service next starts."
            )
            return state
        return self._apply_cyan_runtime_range(minimo, maximo)

    @staticmethod
    def _raise_if_cyan_hardware_rejected(result, *, fixed: bool) -> None:
        """Reject an unconfirmed fixed clock, not an adaptive ceiling.

        SetRange promises bounds, not that the GPU reaches the maximum even
        at high utilization (thermal recovery and workloads can hold it lower).
        Preserve the observation in gpu_operation instead of reporting an
        accepted adaptive request as a failed write. Never restart implicitly.
        """

        verification = str(getattr(result, "hardware_verification", "") or "")
        mismatch = fixed and verification == "not-confirmed"
        if not mismatch:
            return
        observed = getattr(result, "observed_frequency", None)
        busy = getattr(result, "observed_busy", None)
        temperature = getattr(result, "observed_temperature", None)
        requested = int(result.requested_max)
        details = []
        if observed is not None:
            details.append(f"observed {int(observed)} MHz")
        if busy is not None:
            details.append(f"GPU load {int(busy)}%")
        if temperature is not None:
            details.append(f"temperature {float(temperature):.1f} C")
        suffix = ", ".join(details) or "physical clock evidence did not match"
        raise RuntimeError(
            f"Cyan accepted the {'fixed-frequency' if fixed else 'adaptive-range'} "
            f"request up to {requested} MHz, but the BC-250 hardware did not confirm "
            f"that target ({suffix}). The D-Bus request remains active; this is not "
            "reported as a successful GPU operation."
        )

    def _apply_cyan_runtime_range(self, minimo, maximo):
        """Apply and verify one Cyan adaptive range request."""

        self._require_cyan_runtime_for_live_control()
        self._validar_curva_oc_alta(maximo)
        result = CyanGpuEngine(self).apply_range(minimo, maximo)
        self._raise_if_cyan_hardware_rejected(result, fixed=False)
        self.estado_bc250_cache = None
        state = self.estado_bc250()
        state["gpu_operation"] = result.as_dict()
        state["operation_message"] = (
            f"Cyan accepted runtime range {result.current_min}-{result.current_max} MHz. "
            f"Hardware observation: {result.hardware_verification}"
            + (
                f" ({result.observed_frequency} MHz)."
                if result.observed_frequency is not None
                else "."
            )
        )
        return state

    def fijar_frecuencia_bc250(self, frecuencia):
        self.estado_bc250_cache = None
        frecuencia = int(frecuencia)
        if self._selected_gpu_governor() == OBERON_GOVERNOR:
            minimo, maximo = require_oberon_safe_profile(frecuencia, frecuencia)
            minimum_voltage, maximum_voltage = self._oberon_profile_voltages(
                minimo, maximo
            )
            self._require_oberon_idle_transition()
            result = self._editar_governor_toml(
                "set-oberon-operating-points",
                minimo,
                maximo,
                minimum_voltage,
                maximum_voltage,
            )
            restarted = self._restart_governor_if_active(
                str(GOVERNOR_SPECS[OBERON_GOVERNOR]["service"])
            )
            self.estado_bc250_cache = None
            state = self.estado_bc250()
            state["operation_message"] = result + (
                " Active Oberon service restarted." if restarted else ""
            )
            return state
        self._require_cyan_runtime_for_live_control()
        current = self._leer_rango_governor("Current")
        allowed = self._leer_rango_governor("Allowed")
        if allowed is None:
            raise RuntimeError("Cyan D-Bus Allowed range is unavailable.")
        minimum = int(current[0]) if current is not None else int(allowed[0])
        minimum = min(minimum, frecuencia)
        self._ensure_cyan_frequency_range_loaded(minimum, frecuencia)
        self._validar_curva_oc_alta(frecuencia)
        result = CyanGpuEngine(self).apply_fixed(frecuencia)
        self._raise_if_cyan_hardware_rejected(result, fixed=True)
        self.estado_bc250_cache = None
        state = self.estado_bc250()
        state["gpu_operation"] = result.as_dict()
        state["operation_message"] = (
            f"Cyan fixed-frequency mode accepted {frecuencia} MHz. "
            f"Hardware observation: {result.hardware_verification}"
            + (
                f" ({result.observed_frequency} MHz)."
                if result.observed_frequency is not None
                else "."
            )
        )
        return state
