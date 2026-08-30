"""Decky backend for BC250 Quick Access.

Decky runs this plugin as root by declaration.  The plugin never receives a
shell command from its frontend; every write is delegated to the root-owned
BC250 helper using a named, finite operation.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import stat
import subprocess
import sys
import time

import decky

# Decky loads plugin modules by filename and does not guarantee that the
# plugin directory is on ``sys.path``. Keep the bundled immutable policy
# runtime importable on every loader version without reaching into the
# user-writable Desktop application tree.
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from bc250cc.domain.gpu.profiles import profiles_payload  # noqa: E402

HELPER = pathlib.Path("/usr/libexec/bc250-control-center/bc250-quick-access-helper")
# Protocol 13 adds the Oberon 2000 MHz Benchmark profile and the conservative
# 1000 MHz clock-only idle fallback used when Fedora omits gpu_busy_percent.
HELPER_PROTOCOL = 13
GPU_PROFILES = (
    "recovery", "balanced", "gaming", "benchmark",
    "oberon-1500", "oberon-1850", "oberon-2000",
)
CU_MODES = tuple(str(value) for value in range(24, 41, 2))
FAN_PRESETS = ("quiet", "balanced", "boost", "automatic")
FAN_CHANNELS = (2, 3, 4, 5)
FAN_MIN_PERCENT = 20
FAN_MAX_PERCENT = 100
CPU_FREQUENCIES = tuple(range(3500, 4201, 50))
CPU_VIDS = tuple(range(950, 1326, 5))
CPU_SCALES = tuple(range(-50, 1))
MAX_RECENT_ACTIONS = 10


class Plugin:
    def __init__(self) -> None:
        self._operation_lock = asyncio.Lock()
        # Serialize every helper subprocess, including passive status reads.
        # Polling therefore waits behind a write instead of racing UMR/hwmon,
        # while the operation lock still rejects duplicate action clicks.
        self._helper_lock = asyncio.Lock()
        # Session-only feedback for the player.  It is intentionally bounded
        # and in-memory: QAM must not create a second persistent tuning store.
        self._recent_actions: list[dict[str, object]] = []

    def _record_action(self, module: str, target: str, result: dict) -> dict:
        succeeded = result.get("ok") is not False
        self._recent_actions.append({
            "module": module,
            "target": target,
            "ok": succeeded,
            # Frontend dates use Date.now(), so publish Unix milliseconds.
            # The UI also accepts legacy seconds during a hot reload.
            "at": int(time.time() * 1000),
        })
        del self._recent_actions[:-MAX_RECENT_ACTIONS]
        # Keep an evidence trail in plugin_loader.service without logging raw
        # helper output, register dumps, or user-provided strings.
        decky.logger.info(
            "BC250 operation module=%s target=%s result=%s",
            module,
            target,
            "verified" if succeeded else "failed",
        )
        return result

    async def _main(self):
        decky.logger.info("BC250 Quick Access plugin ready")

    async def _unload(self):
        decky.logger.info("BC250 Quick Access plugin unloaded")

    @staticmethod
    def _trusted_helper() -> bool:
        """Do not execute a replaced Decky helper, even from a root plugin."""
        try:
            metadata = HELPER.lstat()
        except OSError:
            return False
        return (
            stat.S_ISREG(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and bool(metadata.st_mode & stat.S_IXUSR)
        )

    def _run(self, *args: str, timeout: int = 190) -> dict:
        if not self._trusted_helper():
            return {"ok": False, "error": "BC250 helper is missing or not protected. Reinstall BC250 Quick Access from Desktop Mode."}
        try:
            result = subprocess.run(
                [str(HELPER), *args], text=True, capture_output=True,
                timeout=timeout, check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "BC250 operation timed out; verify state in the full application."}
        output = (result.stdout or "").strip()
        if result.returncode:
            return {"ok": False, "error": (result.stderr or output or "BC250 helper failed.").strip()[-4000:]}
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            payload = {"ok": True, "message": output[-4000:]}
        return payload if isinstance(payload, dict) else {"ok": True, "value": payload}

    def _verified_status(self) -> dict:
        result = self._run("status", timeout=20)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": (
                    "BC250 Quick Access helper protocol is incompatible. "
                    "Reinstall BC250 Control Center from Desktop Mode."
                ),
            }
        return result

    def _run_verified(self, *args: str, timeout: int = 190) -> dict:
        status = self._verified_status()
        if status.get("ok") is False:
            return status
        return self._run(*args, timeout=timeout)

    async def status(self) -> dict:
        async with self._helper_lock:
            result = await asyncio.to_thread(self._verified_status)
        if result.get("ok") is not False:
            allowed = result.get("gpu_allowed_range")
            governor = result.get("gpu_governor", "cyan")
            if isinstance(allowed, (list, tuple)) and len(allowed) == 2:
                try:
                    result["gpu_profiles"] = profiles_payload(
                        int(allowed[0]), int(allowed[1]), governor=governor,
                    )
                except (TypeError, ValueError, OverflowError):
                    result.pop("gpu_profiles", None)
            result["recent_actions"] = list(reversed(self._recent_actions))
            result["helper_protected"] = True
        return result

    async def cpu_telemetry(self) -> dict:
        """Read CPU clocks during a long tuning action without queuing.

        The normal status route intentionally shares the helper lock with
        writes.  This endpoint is a separate read-only helper action and must
        remain outside both operation locks so the Decky panel stays alive
        while bc250-detect is running.
        """
        result = await asyncio.to_thread(self._run, "cpu-telemetry", timeout=5)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": "BC250 CPU telemetry protocol is incompatible. Reinstall BC250 Control Center from Desktop Mode.",
            }
        return result

    async def _run_single_operation(self, *args: str, timeout: int = 190) -> dict:
        """Run one protected helper operation at a time, never queue clicks."""
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "BC250 Quick Access is already applying an operation. Wait for its verified result before choosing another control.",
            }
        async with self._operation_lock, self._helper_lock:
            return await asyncio.to_thread(self._run_verified, *args, timeout=timeout)

    async def apply_gpu_profile(self, profile: str) -> dict:
        if profile not in GPU_PROFILES:
            return {"ok": False, "error": "Unsupported GPU Quick Access profile."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for the verified result before changing the GPU range.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                # The root helper accepts only a named profile and performs
                # its own active-governor validation and backend-specific
                # read-back. Running a
                # complete status scan before it added 5–10 seconds of CPU,
                # CU and fan reads to every GPU press without improving this
                # hardware boundary.
                result = await asyncio.to_thread(self._run, "gpu-profile", profile, timeout=30)
            return self._record_action("gpu", profile, result)

    async def apply_gpu_safe_point(self, frequency: int) -> dict:
        """Apply one ceiling advertised by the selected protected governor.

        The helper validates Cyan TOML or Oberon's reviewed curve immediately
        before the backend-specific operation.
        This outer boundary keeps arbitrary numeric ranges out of the Decky
        RPC contract without performing an extra, slow whole-panel status scan.
        """
        if isinstance(frequency, bool) or type(frequency) not in {int, str}:
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        try:
            normalized = int(frequency)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        if str(normalized) != str(frequency):
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU range.",
        }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-safe-point", str(normalized), timeout=30,
                )
            return self._record_action("gpu", f"toml-{normalized}", result)

    async def apply_cu_mode(self, mode: str) -> dict:
        aliases = {"stock": "24", "full": "40"}
        mode = aliases.get(str(mode), str(mode))
        if mode not in CU_MODES:
            return {"ok": False, "error": "Unsupported CU Quick Access mode."}
        result = await self._run_single_operation("cu-mode", mode, timeout=480)
        return self._record_action("cu", mode, result)

    async def apply_cu_table(self, masks: list[int] | tuple[int, ...]) -> dict:
        """Apply exactly four bounded WGP row masks through the closed helper."""
        if not isinstance(masks, (list, tuple)) or len(masks) != 4:
            return {"ok": False, "error": "A CU table must contain exactly four row masks."}
        if any(type(mask) is not int or not 0 <= mask <= 0x1F for mask in masks):
            return {"ok": False, "error": "Every CU row mask must be an integer from 0 through 31."}
        active_cus = sum(mask.bit_count() * 2 for mask in masks)
        if active_cus not in range(24, 41, 2):
            return {"ok": False, "error": "Quick Access CU tables must route 24 through 40 CUs in WGP pairs."}
        normalized = tuple(str(mask) for mask in masks)
        result = await self._run_single_operation("cu-table", *normalized, timeout=480)
        target = f"{active_cus}cu:{'-'.join(f'{mask:02x}' for mask in masks)}"
        return self._record_action("cu", target, result)

    async def save_cu_table(self, masks: list[int] | tuple[int, ...]) -> dict:
        """Apply and persist exactly one bounded four-row WGP table."""
        if not isinstance(masks, (list, tuple)) or len(masks) != 4:
            return {"ok": False, "error": "A CU table must contain exactly four row masks."}
        if any(type(mask) is not int or not 0 <= mask <= 0x1F for mask in masks):
            return {"ok": False, "error": "Every CU row mask must be an integer from 0 through 31."}
        active_cus = sum(mask.bit_count() * 2 for mask in masks)
        if active_cus not in range(24, 41, 2):
            return {"ok": False, "error": "Quick Access CU tables must route 24 through 40 CUs in WGP pairs."}
        result = await self._run_single_operation(
            "cu-save", *(str(mask) for mask in masks), timeout=660,
        )
        target = f"saved-{active_cus}cu:{'-'.join(f'{mask:02x}' for mask in masks)}"
        return self._record_action("cu", target, result)

    async def install_cu_service(self) -> dict:
        result = await self._run_single_operation("cu-service", "install", timeout=240)
        return self._record_action("cu", "service-install", result)

    async def remove_cu_service(self) -> dict:
        result = await self._run_single_operation("cu-service", "remove", timeout=90)
        return self._record_action("cu", "service-remove", result)

    async def apply_system_fan_preset(self, preset: str) -> dict:
        if preset not in FAN_PRESETS:
            return {"ok": False, "error": "Unsupported system-fan preset."}
        result = await self._run_single_operation("fan-system", preset, timeout=30)
        return self._record_action("fan", preset, result)

    async def apply_fan_channel(self, channel: int, target: int | str) -> dict:
        """Apply one temporary setting without exposing a generic root argv."""
        if isinstance(channel, bool) or type(channel) not in {int, str}:
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}
        try:
            normalized_channel = int(channel)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}
        if str(normalized_channel) != str(channel) or normalized_channel not in FAN_CHANNELS:
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}

        if target == "automatic":
            normalized_target = "automatic"
        else:
            if isinstance(target, bool) or type(target) not in {int, str}:
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            try:
                percent = int(target)
            except (TypeError, ValueError, OverflowError):
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            if str(percent) != str(target) or not FAN_MIN_PERCENT <= percent <= FAN_MAX_PERCENT:
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            normalized_target = str(percent)

        result = await self._run_single_operation(
            "fan-channel", str(normalized_channel), normalized_target, timeout=30,
        )
        return self._record_action("fan", f"pwm{normalized_channel}:{normalized_target}", result)

    async def apply_saved_cpu_profile(self) -> dict:
        result = await self._run_single_operation("cpu-apply-saved", timeout=920)
        return self._record_action("cpu", "saved", result)

    @staticmethod
    def _cpu_value(value: int, allowed: tuple[int, ...], label: str) -> int:
        if isinstance(value, bool) or type(value) not in {int, str}:
            raise ValueError(f"Unsupported CPU {label}.")
        try:
            normalized = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Unsupported CPU {label}.") from exc
        if str(normalized) != str(value) or normalized not in allowed:
            raise ValueError(f"Unsupported CPU {label}.")
        return normalized

    async def apply_cpu_tuning(self, frequency: int, vid: int) -> dict:
        try:
            frequency = self._cpu_value(frequency, CPU_FREQUENCIES, "frequency")
            vid = self._cpu_value(vid, CPU_VIDS, "maximum VID")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        result = await self._run_single_operation(
            "cpu-detect", str(frequency), str(vid), timeout=920,
        )
        return self._record_action("cpu", f"detect-{frequency}:{vid}", result)

    async def apply_cpu_scale(self, frequency: int, scale: int) -> dict:
        try:
            frequency = self._cpu_value(frequency, CPU_FREQUENCIES, "frequency")
            scale = self._cpu_value(scale, CPU_SCALES, "scale")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        result = await self._run_single_operation(
            "cpu-scale", str(frequency), str(scale), timeout=200,
        )
        return self._record_action("cpu", f"manual-{frequency}:{scale}", result)

    async def install_cpu_service(self) -> dict:
        # The root CPU helper, not Decky's process memory, validates that the
        # detector result is protected, exact, applied live and from this boot.
        result = await self._run_single_operation(
            "cpu-service", "install", timeout=180,
        )
        return self._record_action("cpu", "service-install-detected", result)

    async def remove_cpu_service(self) -> dict:
        result = await self._run_single_operation(
            "cpu-service", "remove", timeout=90,
        )
        return self._record_action("cpu", "service-remove", result)
