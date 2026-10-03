import {
  Button,
  ConfirmModal,
  Focusable,
  NavEntryPositionPreferences,
  Router,
  showModal,
  SliderField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import {
  type CSSProperties,
  type ReactElement,
  type ReactNode,
  cloneElement,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  FaBolt,
  FaClock,
  FaCog,
  FaExclamationTriangle,
  FaFan,
  FaGamepad,
  FaHdd,
  FaMemory,
  FaMicrochip,
  FaTh,
} from "react-icons/fa";
import { LuActivity, LuCpu, LuFan, LuGamepad2, LuGrid3X3, LuLayoutGrid, LuMemoryStick, LuMicrochip, LuSettings, LuSlidersHorizontal, LuTrash2 } from "react-icons/lu";
import { tokens } from "./theme";
// Generated from src/bc250cc/shared/error_catalog.py; rollup inlines it.
import errorCatalog from "./generated/error_catalog.json";
import { text } from "./i18n";

type CpuProfile = { frequency: number; scale: number; temperature: number };
type CpuDetectedProfile = CpuProfile & {
  ready: true;
  same_boot: true;
  applied_live: true;
  requested_frequency: number;
  requested_vid: number;
  requested_temperature: number;
  observed_at: number;
  active_profile?: CpuActiveProfile;
  manual_scale_ready?: boolean;
};
type CpuActiveProfile = CpuProfile & {
  mode: "automatic" | "manual" | "boot";
  estimated_vid: number;
  reference_scale: number;
  observed_at?: number;
  persistable: boolean;
};
type GpuPoint = { frequency: number; voltage: number };
type GpuProfile = { key: string; name: string; min: number; max: number };
type CpuPreset = { key: string; name: string; frequency: number; vid: number; default?: boolean };
type FanOption = {
  channel: number;
  label?: string;
  available: boolean;
  duty?: number;
  mode?: string | number;
  percent?: number;
  rpm?: number | null;
  rpm_observed?: boolean;
  wiring?: string;
  wiring_uncertain?: boolean;
};
// Every bound the controls use, published with the state by the helper so the
// panel keeps none of its own.
type ContractLimits = {
  revision?: number;
  cpu?: {
    frequency_range?: [number, number];
    frequency_step?: number;
    vid_range?: [number, number];
    vid_step?: number;
    scale_range?: [number, number];
    vid_model?: CpuVidModel;
  };
  cu?: { targets?: number[] };
  fan?: { channels?: number[]; percent_range?: [number, number]; percent_step?: number };
  vram?: { presets?: number[] };
};
type VramState = {
  supported: boolean; reason: string; uma_size_mb: number | null; boot_id: string | null;
  // Protocol 21: what the firmware booted with, and whether CMOS now holds
  // another size -- written here or by the desktop, it does not matter.
  active_mb?: number | null; reboot_pending?: boolean;
};
// The GPU memory limit (TTM pages_limit) as the desktop's own system-setup
// helper reports it. The panel keeps no copy of its own: desktop and panel
// read and change this one state.
type TtmState = {
  supported: boolean; backend: string; reason: string; page_size: number | null;
  presets_gib: number[]; manual_arguments: Record<string, string>;
  physical_ram_bytes: number | null; next_boot_ram_bytes: number | null;
  live_pages: number | null; boot_pages: number | null; configured_pages: number | null;
  managed: boolean; managed_pages: number | null; external: boolean; external_pages: number | null;
  gtt_total_bytes: number | null; gtt_override: number | null; legacy_pages: number | null;
  reboot_required: boolean;
};

type Result = {
  operation_in_progress?: { action: string; arguments?: string[]; started_at: number } | null;
  ok?: boolean;
  protocol?: number;
  error?: string;
  message?: string;
  contract?: ContractLimits;
  gpu_range?: [number, number];
  gpu_allowed_range?: [number, number];
  gpu_profiles?: GpuProfile[];
  gpu_core_mhz?: number;
  gpu_voltage_mv?: number;
  gpu_busy_percent?: number;
  gpu_performance_enabled?: boolean;
  gpu_temperature_c?: number;
  gpu_safe_point_ceilings?: GpuPoint[];
  gpu_voltage_points?: VoltagePoint[];
  gpu_voltage_level?: number | null;
  gpu_compatibility?: GpuCompatibility | null;
  cpu_frequency_mhz?: number;
  cpu_temperature_c?: number;
  observed_at?: number;
  cpu_saved_profile?: CpuProfile | null;
  cpu_detected_profile?: CpuDetectedProfile | null;
  cpu_active_profile?: CpuActiveProfile | null;
  cpu_manual_scale_ready?: boolean;
  cpu_service_installed?: boolean;
  cpu_service_enabled?: boolean;
  cpu_service_active?: boolean;
  cpu_tuning_ready?: boolean;
  cpu_tuning_temperature?: number | null;
  cpu_tuning_source?: "qam-detected" | "detector-required" | "stress-unavailable" | "helper-unavailable";
  cpu_tuning_error?: string;
  cyan_active?: boolean;
  oberon_active?: boolean;
  gpu_governor?: "cyan" | "oberon" | "conflict" | "none";
  gpu_governor_label?: string;
  gpu_governor_active?: boolean;
  gpu_service_target?: "cyan" | "oberon" | "";
  gpu_service_installed?: boolean;
  gpu_service_enabled?: boolean;
  gpu_service_active?: boolean;
  gpu_service_starting?: boolean;
  gpu_dbus_responsive?: boolean;
  gpu_service_conflict?: boolean;
  cu_backend_ready?: boolean;
  cu_kernel_managed?: boolean;
  cu_total_cus?: number;
  cu_masks?: number[];
  cu_driver_masks?: number[];
  cu_saved_masks?: number[] | null;
  cu_service_installed?: boolean;
  cu_service_enabled?: boolean;
  helper_protected?: boolean;
  cu_snapshot_published?: boolean;
  cu_snapshot_warning?: string;
  system_fan_channels?: number[];
  fan_channel_options?: FanOption[];
  bazzite?: boolean;
  gpu_memory_clock_mhz?: number | null;
  gpu_vram_used_mib?: number | null;
  gpu_vram_total_mib?: number | null;
  memory_zram_active?: boolean;
  memory_zram_total_bytes?: number | null;
  memory_backing_swap_active?: boolean;
  memory_backing_swap_total_bytes?: number | null;
  memory_zswap_enabled?: boolean | null;
  memory_ttm_pages_limit?: number | null;
  memory_ttm_limit_bytes?: number | null;
  memory_ram_total_bytes?: number | null;
  memory_ram_available_bytes?: number | null;
  memory_swap_total_bytes?: number | null;
  memory_swap_free_bytes?: number | null;
  storage_total_bytes?: number | null;
  storage_used_bytes?: number | null;
  vrm_available?: boolean;
  vrm_input_voltage_v?: number | null;
  vrm_total_power_w?: number | null;
  vrm_cpu_temperature_c?: number | null;
  vrm_cpu_voltage_v?: number | null;
  vrm_cpu_current_a?: number | null;
  vrm_cpu_power_w?: number | null;
  vrm_gpu_temperature_c?: number | null;
  vrm_gpu_voltage_v?: number | null;
  vrm_gpu_current_a?: number | null;
  vrm_gpu_power_w?: number | null;
  gpu_soc_clock_mhz?: number | null;
  gpu_fabric_clock_mhz?: number | null;
  gpu_gtt_used_mib?: number | null;
  gpu_gtt_total_mib?: number | null;
  gpu_pcie_link?: string;
  gpu_vbios_version?: string;
  cpu_voltage_mv?: number | null;
  cpu_usage_percent?: number | null;
  cpu_cores?: { core: number; core_id?: number | null; percent: number | null; frequency_mhz: number | null }[];
  cpu_physical_slots?: number;
  board_temperature_c?: number | null;
  vrm_mos_temperature_c?: number | null;
  nvme_temperature_c?: number | null;
  nvme_hotspot_temperature_c?: number | null;
  cu_active_cus?: number | null;
  cpu_profiles?: CpuPreset[];
  system_fan_preset?: string;
  system_fan_duty?: number | null;
  gddr6_available?: boolean;
  gddr6_reason?: string;
  gddr6_patch_error?: string | null;
  gddr6_chips?: { chip: number; temperature_c: number }[];
  gddr6_average_c?: number | null;
  gddr6_hotspot_c?: number | null;
  gddr6_hotspot_chip?: number | null;
  gddr6_bios_version?: string;
  gddr6_firmware_supported?: boolean;
  vram?: VramState;
  fan_profiles?: FanPreset[];
  system_fan_policy?: boolean;
  system_fan_override?: boolean;
  ace_available?: boolean;
  ace_busy_percent?: number | null;
  ace_process?: string;
};
type FanPreset = { key: string; name: string; percent: number };
type GameProfile = { app_id: string; name: string; gpu: string | null; fan: string | null };
type GameSession = { app_id: string; name: string; applied: { gpu: string | null; fan: string | null } };
type GameStore = { ok?: boolean; error?: string; enabled?: boolean; games?: GameProfile[]; session?: GameSession | null };
type GameEvent = { ok?: boolean; error?: string; applied?: boolean; restored?: boolean; name?: string; gpu?: string | null; fan?: string | null; reason?: string };
// Cyan's kernel compatibility, as the helper reads it from the protected TOML.
type GpuCompatibility = {
  set_method: "smu" | "kernel";
  usage_method: "busy-flag" | "process" | "kernel";
  fix_metrics: boolean;
  fix_frequency: boolean;
};
type Status = Result;
type VoltagePoint = { frequency: number; voltage: number; default: number };
type DraftKind = "cu" | "fan" | "gpu" | "cpu" | "none";

const getStatus = callable<[], Status>("status");
const getCpuTelemetry = callable<[], Result>("cpu_telemetry");
const getMonitorSnapshot = callable<[], Result>("monitor_snapshot");
const getGddr6Sensors = callable<[], Result>("gddr6_sensors");
const applyGddr6Patch = callable<[], Result>("apply_gddr6_patch");
const applyGpuProfile = callable<[profile: string], Result>("apply_gpu_profile");
const applyGpuSafePoint = callable<[frequency: number], Result>("apply_gpu_safe_point");
const setGpuHighFrequencyPoints = callable<[enabled: boolean], Result>("set_gpu_high_frequency_points");
const setGpuGovernorService = callable<[enabled: boolean], Result>("set_gpu_governor_service");
const applyGpuVoltageLevel = callable<[level: number], Result>("apply_gpu_voltage_level");
const applyGpuVoltagePoints = callable<[points: { frequency: number; voltage: number }[]], Result>("apply_gpu_voltage_points");
const applyGpuCompatibility = callable<[setMethod: string, usageMethod: string, fixMetrics: boolean, fixFrequency: boolean], Result>("apply_gpu_compatibility");
const applyCuTable = callable<[masks: number[]], Result>("apply_cu_table");
const saveCuTable = callable<[masks: number[]], Result>("save_cu_table");
const installCuService = callable<[], Result>("install_cu_service");
const removeCuService = callable<[], Result>("remove_cu_service");
const applyFanChannel = callable<[channel: number, target: number | "automatic"], Result>("apply_fan_channel");
const applyCpuTuning = callable<[frequency: number, vid: number], Result>("apply_cpu_tuning");
const applyCpuScale = callable<[frequency: number, scale: number], Result>("apply_cpu_scale");
const installCpuService = callable<[], Result>("install_cpu_service");
const removeCpuService = callable<[], Result>("remove_cpu_service");
const applyVramSize = callable<[sizeMb: number], Result>("apply_vram_size");
const getTtmState = callable<[], Result & { ttm?: TtmState }>("ttm_state");
const applyTtmLimit = callable<[value: string], Result & { ttm?: TtmState }>("apply_ttm_limit");
const applySystemFanPreset = callable<[preset: string], Result>("apply_system_fan_preset");
const getGameProfiles = callable<[], GameStore>("game_profiles");
const saveGameProfile = callable<[appId: string, name: string, gpu: string | null, fan: string | null], GameStore>("save_game_profile");
const removeGameProfile = callable<[appId: string], GameStore>("remove_game_profile");
const setGameProfilesEnabled = callable<[enabled: boolean], GameStore>("set_game_profiles_enabled");
const gameStarted = callable<[appId: string, name: string, refresh: boolean], GameEvent>("game_started");
const gameStopped = callable<[appId: string], GameEvent>("game_stopped");

const fanChannels = [2, 3, 4, 5] as const;
const cuRows = ["SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1"] as const;
// Same ladder the desktop's own VRAM control offers; used only until the
// first status() reply carries the contract-sourced list, so the dropdown
// never renders empty on first paint.
const VRAM_PRESETS_FALLBACK = [256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288];
function vramSizeLabel(sizeMb: number): string {
  return sizeMb < 1024 ? `${sizeMb} MiB` : `${Math.round(sizeMb / 1024 * 10) / 10} GiB`;
}
const GIB = 1024 ** 3;
// Whole GiB of a TTM page count, the unit the choices are offered in.
function ttmGib(pages: number | null | undefined, pageSize: number): number | null {
  return pages != null && pageSize > 0 ? Math.round(pages * pageSize / GIB * 10) / 10 : null;
}

// Which code a failure carries is decided by the generated catalogue, not
// here. This used to be a chain of substring guesses that disagreed with
// src/bc250cc/shared/error_catalog.py on eight of thirty-two markers, so the
// same fault reported one id in Game Mode and another on the Desktop and a
// user quoting a code to support was quoting the wrong one.
//
// The marker table below is generated by scripts/development/generate_contract.py
// and is already sorted longest-first, so a short marker cannot shadow a
// longer one that contains it. Only the *wording* stays local, because it is
// already translated in this plugin's own catalogs.
type ErrorDiagnosis = { code: string; summary: string; cause: string; action: string };

const wordingFor: Record<string, () => Omit<ErrorDiagnosis, "code">> = {
  "BC250-PROTOCOL-001": () => ({ summary: text.protocolFailed, cause: text.protocolCause, action: text.protocolAction }),
  "BC250-HELPER-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
  "BC250-BUSY-001": () => ({ summary: text.busyFailed, cause: text.busyCause, action: text.busyAction }),
  "BC250-TIMEOUT-001": () => ({ summary: text.timeoutFailed, cause: text.timeoutCause, action: text.timeoutAction }),
  "BC250-DBUS-001": () => ({ summary: text.gpuDbusFailed, cause: text.gpuDbusCause, action: text.gpuDbusAction }),
  "BC250-RANGE-001": () => ({ summary: text.gpuRangeFailed, cause: text.gpuRangeCause, action: text.gpuRangeAction }),
  "BC250-GPU-001": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
  "BC250-CU-001": () => ({ summary: text.cuOperationFailed, cause: text.cuCause, action: text.cuGuidance }),
  "BC250-FAN-001": () => ({ summary: text.fanOperationFailed, cause: text.fanCause, action: text.fanGuidance }),
  "BC250-CPU-001": () => ({ summary: text.cpuOperationFailed, cause: text.cpuCause, action: text.cpuGuidance }),
  "BC250-CPUTOOL-001": () => ({ summary: text.cpuVerifyFailed, cause: text.cpuVerifyCause, action: text.cpuVerifyAction }),
  "BC250-CMD-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
  "BC250-CONFIG-001": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
  "BC250-SERVICE-003": () => ({ summary: text.gpuOperationFailed, cause: text.gpuCause, action: text.gpuAction }),
  "BC250-HW-001": () => ({ summary: text.error, cause: text.unknownCause, action: text.retryGuidance }),
  "BC250-PERM-001": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
  "BC250-AUTH-002": () => ({ summary: text.helperFailed, cause: text.helperCause, action: text.helperAction }),
  "BC250-TTM-001": () => ({ summary: text.ttmFailed, cause: text.ttmCause, action: text.ttmAction }),
};

const codeByMarker = new Map<string, string>();
for (const entry of errorCatalog.codes) for (const marker of entry.markers) codeByMarker.set(marker, entry.code);

function diagnoseError(value: string): ErrorDiagnosis {
  const raw = String(value ?? "");
  let code = "";
  for (const marker of errorCatalog.markers_longest_first) {
    if (raw.includes(marker)) { code = codeByMarker.get(marker) ?? ""; break; }
  }
  if (!code) {
    // No marker: the message came from something other than our helpers.
    const lower = raw.toLowerCase();
    if (lower.includes("timed out") || lower.includes("timeout")) code = "BC250-TIMEOUT-001";
    else if (lower.includes("protocol") && lower.includes("incompat")) code = "BC250-PROTOCOL-001";
    else if (lower.includes("helper") && (lower.includes("missing") || lower.includes("protected") || lower.includes("ownership") || lower.includes("permission"))) code = "BC250-HELPER-001";
    else if (lower.includes("already") && (lower.includes("running") || lower.includes("operation"))) code = "BC250-BUSY-001";
    else if (lower.includes("d-bus")) code = "BC250-DBUS-001";
    else if (lower.includes("governor")) code = "BC250-GPU-001";
    else if (lower.includes("umr") || lower.includes("wgp") || lower.includes("cu table")) code = "BC250-CU-001";
    else if (lower.includes("pwm") || lower.includes("nct")) code = "BC250-FAN-001";
    else if (lower.includes("bc250-detect") || lower.includes("stress")) code = "BC250-CPU-001";
  }
  const wording = wordingFor[code];
  if (!wording) return { code: code || "BC250-GENERAL-001", summary: text.error, cause: text.unknownCause, action: text.retryGuidance };
  return { code, ...wording() };
}
const localizedErrorSummary = (value: string) => diagnoseError(value).summary;
const failed = (error: unknown): Result => ({ ok: false, error: error instanceof Error ? error.message : text.error });
const validMasks = (value: number[] | undefined): value is number[] => Array.isArray(value) && value.length === 4 && value.every((mask) => Number.isInteger(mask) && mask >= 0 && mask <= 31);
const countWgps = (masks: number[]) => masks.reduce((total, mask) => total + [0, 1, 2, 3, 4].filter((bit) => Boolean(mask & (1 << bit))).length, 0);
const sameMasks = (a: number[], b: number[]) => a.length === b.length && a.every((mask, index) => mask === b[index]);
const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"] as const;
function formatBytes(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return "—";
  let amount = value; let unit = 0;
  while (amount >= 1024 && unit < BYTE_UNITS.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${BYTE_UNITS[unit]}`;
}
function masksFromTarget(target: number, targets?: number[]) {
  const masks = [7, 7, 7, 7];
  // 12 WGPs are always on; the ladder decides how many more there can be.
  const lowest = targets && targets.length ? Math.min(...targets) : 24;
  const highest = targets && targets.length ? Math.max(...targets) : 40;
  let extra = Math.max(0, Math.min((highest - lowest) / 2, target / 2 - lowest / 2));
  for (let wgp = 3; wgp < 5 && extra > 0; wgp += 1) for (let row = 0; row < 4 && extra > 0; row += 1) { masks[row] |= 1 << wgp; extra -= 1; }
  return masks;
}
// ---------------------------------------------------------------- per game
// The game Steam says is running, shared by the lifetime listener registered
// when the plugin loads and by the panel, which only exists while the Quick
// Access menu is open. Applying and restoring a game's profile therefore
// never depends on the player opening this panel.
type RunningGame = { appId: string; name: string } | null;
let runningGame: RunningGame = null;
const runningGameListeners = new Set<(game: RunningGame) => void>();
const gameStoreListeners = new Set<() => void>();
const runningInstances = new Map<string, Set<number>>();

function setRunningGame(game: RunningGame) {
  runningGame = game;
  runningGameListeners.forEach((listener) => listener(game));
}
function notifyGameStore() { gameStoreListeners.forEach((listener) => listener()); }
function useRunningGame(): RunningGame {
  const [game, setGame] = useState<RunningGame>(runningGame);
  useEffect(() => { runningGameListeners.add(setGame); return () => { runningGameListeners.delete(setGame); }; }, []);
  return game;
}
type AppStoreGlobals = typeof globalThis & { appStore?: { GetAppOverviewByAppID?: (appId: number) => { display_name?: string } | null } };
function appName(appId: number): string {
  try {
    const name = (globalThis as AppStoreGlobals).appStore?.GetAppOverviewByAppID?.(appId)?.display_name;
    if (name) return String(name);
  } catch { /* the Steam store can be unavailable for a moment */ }
  return `App ${appId}`;
}
function presetLabel(key: string | null | undefined, presets?: FanPreset[]): string {
  if (!key) return text.unchanged;
  if (key === "automatic") return text.automatic;
  const exported = presets?.find((preset) => preset.key === key)?.name;
  if (exported) return exported;
  return key === "quiet" ? text.fanQuiet : key === "balanced" ? text.fanBalanced : key === "boost" ? text.fanBoost : key;
}
// The built-in ladder arrives with English names; a name the player gave a card on
// the desktop is shown as written, the built-in ones in the panel's language.
const BUILT_IN_GPU_NAMES: Record<string, () => string> = {
  Balanced: () => text.profileBalanced, Gaming: () => text.profileGaming, Benchmark: () => text.profileBenchmark,
};
function gpuProfileName(profile: GpuProfile): string {
  const builtIn = /^(oberon-\d+|balanced|gaming|benchmark)$/.test(profile.key) ? BUILT_IN_GPU_NAMES[profile.name] : undefined;
  return builtIn ? builtIn() : profile.name;
}
function gpuLabel(key: string | null | undefined, profiles?: GpuProfile[]): string {
  if (!key) return text.unchanged;
  const found = profiles?.find((profile) => profile.key === key);
  if (found) return gpuProfileName(found);
  if (key === "balanced") return text.profileBalanced;
  if (key === "gaming") return text.profileGaming;
  if (key === "benchmark") return text.profileBenchmark;
  return key.startsWith("oberon-") ? `${key.slice(7)} MHz` : key;
}
async function onGameStart(appId: string, name: string, refresh = false) {
  setRunningGame({ appId, name });
  try {
    const result = await gameStarted(appId, name, refresh);
    if (result.ok === false) toaster.toast({ title: `BC250 · ${name}`, body: `${text.gameProfileNotApplied}: ${localizedErrorSummary(result.error ?? text.error)}` });
    else if (result.applied) toaster.toast({ title: `BC250 · ${name}`, body: `${text.gameProfileApplied}${result.gpu ? ` · GPU ${gpuLabel(result.gpu)}` : ""}${result.fan ? ` · ${text.fans} ${presetLabel(result.fan)}` : ""}` });
  } catch (error) {
    toaster.toast({ title: `BC250 · ${name}`, body: `${text.gameProfileNotApplied}: ${localizedErrorSummary(failed(error).error ?? text.error)}` });
  } finally { notifyGameStore(); }
}
async function onGameStop(appId: string) {
  if (runningGame?.appId === appId) setRunningGame(null);
  try {
    const result = await gameStopped(appId);
    if (result.ok === false) toaster.toast({ title: "BC250", body: localizedErrorSummary(result.error ?? text.error) });
    else if (result.restored) toaster.toast({ title: `BC250 · ${result.name || appName(Number(appId))}`, body: text.gameProfileRestored });
  } catch (error) {
    toaster.toast({ title: "BC250", body: localizedErrorSummary(failed(error).error ?? text.error) });
  } finally { notifyGameStore(); }
}
function onAppLifetime(update: { unAppID: number; nInstanceID: number; bRunning: boolean }) {
  const appId = String(update.unAppID ?? "");
  if (!appId || appId === "0") return;
  // A launcher and its game can be two instances of one app: the profile
  // stays on until the last of them ends.
  const instances = runningInstances.get(appId) ?? new Set<number>();
  if (update.bRunning) {
    const first = instances.size === 0;
    instances.add(update.nInstanceID);
    runningInstances.set(appId, instances);
    if (first) void onGameStart(appId, appName(update.unAppID));
    return;
  }
  instances.delete(update.nInstanceID);
  if (instances.size === 0) { runningInstances.delete(appId); void onGameStop(appId); }
}

// ---------------------------------------------------------------- settings
// Purely cosmetic, per-device preferences (focus ring color, poll cadence,
// sensor tile layout). None of this reaches the privileged helper or affects
// a hardware decision, so it is stored client-side rather than round-tripped
// through the root-owned contract that everything else in this file answers
// to. localStorage on this origin survives plugin reloads and Steam restarts
// on this one Deck, which is exactly the durability a look-and-feel choice
// needs and no more.
type AccentKey = "orange" | "cyan" | "white" | "blue" | "purple" | "green";
type SensorLayout = "grid" | "list";
type QuickAccessSettings = { accent: AccentKey; refreshIntervalMs: number; sensorLayout: SensorLayout };

// The accent recolors every selected/active/primary-action surface in the
// interface (active tab, selected profile, primary button, section icons
// that used the brand color) — everything that isn't a fixed per-module
// identity color (CPU=blue, GPU=purple, Fan=cyan stay put). It never touches
// the controller focus ring, which is fixed white (tokens.colors.focus) on
// purpose: that ring means "this is where the pad is right now" and must
// read the same no matter which accent is active.
const ACCENT_KEYS: AccentKey[] = ["orange", "cyan", "white", "blue", "purple", "green"];
const ACCENT_SWATCHES: Record<AccentKey, { focus: string; focus_soft: string; label: string }> = {
  // "orange" is the plugin's original, non-configurable brand color — kept
  // as the default so a player who never opens Settings sees the same
  // interface they always have.
  orange: { focus: tokens.colors.orange, focus_soft: tokens.colors.orange_soft, label: text.accentOrange },
  cyan: { focus: tokens.colors.cyan, focus_soft: tokens.colors.cyan_soft, label: text.accentCyan },
  white: { focus: "#FFFFFF", focus_soft: "rgba(255, 255, 255, 0.18)", label: text.accentWhite },
  blue: { focus: tokens.colors.blue, focus_soft: tokens.colors.blue_soft, label: text.accentBlue },
  purple: { focus: tokens.colors.purple, focus_soft: tokens.colors.purple_soft, label: text.accentPurple },
  green: { focus: tokens.colors.green, focus_soft: tokens.colors.green_soft, label: text.accentGreen },
};
const REFRESH_INTERVAL_OPTIONS = [2000, 5000, 10000, 30000] as const;
const DEFAULT_SETTINGS: QuickAccessSettings = { accent: "orange", refreshIntervalMs: 5000, sensorLayout: "grid" };
// GDDR6 monitoring as on the desktop: nothing is read until the player asks,
// and each live session ends itself after ten minutes. The SMU it reads
// through is shared with the GPU governor and the CPU overclock, so it is not
// a setting that stays on. Module scope: the panel remounts with Quick Access.
const GDDR6_SESSION_MS = 10 * 60 * 1000;
let gddr6LiveUntil = 0;
type Gddr6Session = { live: boolean; minutesLeft: number; setLive: (on: boolean) => void; merge: (fields: Partial<Status>) => void };
const SETTINGS_STORAGE_KEY = "bc250-quick-access:settings";

function loadSettings(): QuickAccessSettings {
  try {
    const raw = globalThis.localStorage?.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<QuickAccessSettings>;
    return {
      accent: ACCENT_KEYS.includes(parsed.accent as AccentKey) ? (parsed.accent as AccentKey) : DEFAULT_SETTINGS.accent,
      refreshIntervalMs: REFRESH_INTERVAL_OPTIONS.includes(parsed.refreshIntervalMs as typeof REFRESH_INTERVAL_OPTIONS[number])
        ? (parsed.refreshIntervalMs as number) : DEFAULT_SETTINGS.refreshIntervalMs,
      sensorLayout: parsed.sensorLayout === "list" ? "list" : "grid",
    };
  } catch { return DEFAULT_SETTINGS; }
}
function saveSettings(settings: QuickAccessSettings) {
  try { globalThis.localStorage?.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings)); } catch { /* best-effort only */ }
}

// A record of "the last VRAM size this browser asked CMOS to hold, and the
// boot it asked during" -- a plain useRef does not survive this: the Memory
// tab remounts every time the player leaves and returns to it (see
// PanelTab's ternary render below), which was silently dropping the
// pending-reboot notice the moment someone switched tabs. localStorage plus
// the backend's boot_id survives that, survives a Decky reload, and clears
// itself correctly the moment a real reboot changes the boot id.
type VramPendingRecord = { mb: number; bootId: string };
const VRAM_PENDING_STORAGE_KEY = "bc250-quick-access:vram-pending";

function loadVramPending(): VramPendingRecord | null {
  try {
    const raw = globalThis.localStorage?.getItem(VRAM_PENDING_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<VramPendingRecord>;
    return typeof parsed.mb === "number" && typeof parsed.bootId === "string" ? (parsed as VramPendingRecord) : null;
  } catch { return null; }
}
function saveVramPending(record: VramPendingRecord | null) {
  try {
    if (record) globalThis.localStorage?.setItem(VRAM_PENDING_STORAGE_KEY, JSON.stringify(record));
    else globalThis.localStorage?.removeItem(VRAM_PENDING_STORAGE_KEY);
  } catch { /* best-effort only */ }
}

const SettingsContext = createContext<{ settings: QuickAccessSettings; setSettings: (next: QuickAccessSettings) => void; gddr6: Gddr6Session }>({
  settings: DEFAULT_SETTINGS, setSettings: () => {},
  gddr6: { live: false, minutesLeft: 0, setLive: () => {}, merge: () => {} },
});

// The player's accent, for the surfaces that used to be a fixed green.
function useAccent() {
  return ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
}

// Lucide's default stroke is 2; navigation icons are drawn finer.
const NAV_STROKE = 1.25;

function PadButton({ children, disabled = false, onActivate, style, preferredFocus = false, label }: {
  children: ReactNode; disabled?: boolean; onActivate: () => void; style?: CSSProperties; preferredFocus?: boolean; label?: string;
}) {
  const [focused, setFocused] = useState(false);
  const locked = useRef(false);
  const activate = () => {
    if (disabled || locked.current) return;
    locked.current = true;
    onActivate();
    globalThis.setTimeout(() => { locked.current = false; }, 180);
  };
  return (
    <Button aria-label={label} disabled={disabled} focusable={!disabled} onClick={activate} onOKButton={activate} preferredFocus={preferredFocus}
      onGamepadFocus={() => setFocused(true)} onGamepadBlur={() => setFocused(false)}
      style={{
        background: tokens.colors.panel_raised,
        borderRadius: 6,
        boxSizing: "border-box",
        color: tokens.colors.text,
        outline: "none",
        transition: "border-color 90ms ease",
        ...style,
        opacity: disabled ? .38 : (style?.opacity ?? 1),
        border: focused ? `1px solid ${tokens.colors.focus}` : (style?.border ?? `1px solid ${tokens.colors.border}`),
        boxShadow: focused ? `inset 0 0 0 1px ${tokens.colors.focus_soft}` : "none",
      }}>
      {children}
    </Button>
  );
}

function SectionTitle({ kind, title, trailing }: { kind: "gpu" | "cu" | "cpu" | "fan" | "power" | "memory" | "storage" | "settings" | "game"; title: string; trailing?: ReactNode }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const data = {
    gpu: [<FaMicrochip />, accent.focus, accent.focus_soft],
    cu: [<FaTh />, accent.focus, accent.focus_soft],
    cpu: [<FaBolt />, accent.focus, accent.focus_soft],
    fan: [<FaFan />, accent.focus, accent.focus_soft],
    power: [<FaBolt />, accent.focus, accent.focus_soft],
    memory: [<FaMemory />, tokens.colors.green, tokens.colors.green_soft],
    storage: [<FaHdd />, tokens.colors.green, tokens.colors.green_soft],
    settings: [<FaCog />, accent.focus, accent.focus_soft],
    game: [<FaGamepad />, accent.focus, accent.focus_soft],
  }[kind] as [ReactNode, string, string];
  return <div style={{ alignItems: "center", display: "flex", gap: 6, margin: "0 2px 6px" }}>
    <span style={{ alignItems: "center", background: data[2], borderRadius: 4, color: data[1], display: "flex", fontSize: 10, height: 16, justifyContent: "center", width: 16 }}>{data[0]}</span>
    <span style={{ color: tokens.colors.subtle, flex: 1, fontSize: 10, fontWeight: 650, letterSpacing: ".05em" }}>{title}</span>
    {trailing}
  </div>;
}

function Notice({ value, dismiss }: { value: string; dismiss: () => void }) {
  const [open, setOpen] = useState(false);
  const diagnosis = diagnoseError(value);
  return <div role="alert" style={{ background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red}`, borderRadius: 8, marginBottom: 10, padding: 9 }}>
    <div style={{ display: "flex", gap: 7 }}><FaExclamationTriangle color={tokens.colors.red} /><div><b>{text.error}</b><div style={{ color: tokens.colors.red, fontSize: 11, marginTop: 3 }}>{diagnosis.summary}</div><div style={{ color: tokens.colors.muted, fontSize: 10, marginTop: 4 }}><b>{text.likelyCause}:</b> {diagnosis.cause}</div><div style={{ color: tokens.colors.muted, fontSize: 10, marginTop: 4 }}><b>{text.next}:</b> {diagnosis.action}</div></div></div>
    <div style={{ display: "flex", gap: 6, marginTop: 7 }}><PadButton onActivate={() => setOpen(!open)} style={{ fontSize: 10, minHeight: 30, padding: "4px 8px" }}>{open ? text.hide : text.details}</PadButton><PadButton onActivate={dismiss} style={{ fontSize: 10, minHeight: 30, padding: "4px 8px" }}>{text.close}</PadButton></div>
    {open ? <pre style={{ background: tokens.colors.console_bg, color: tokens.colors.red, fontSize: 9, margin: "7px 0 0", overflowWrap: "anywhere", padding: 6, whiteSpace: "pre-wrap" }}>{text.diagnosticCode}: {diagnosis.code}{"\n"}{value}</pre> : null}
  </div>;
}

// The installed governor's service, under the frequency controls it serves.
// Every change is confirmed first and read back by the root helper, which
// picks the unit itself and refuses while both governors run.
function GovernorServiceRow({ state, busy, execute }: {
  state: Status; busy: boolean;
  execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void>;
}) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const target = state.gpu_service_target ?? "";
  const name = target === "oberon" ? "Oberon" : target === "cyan" ? "Cyan Skillfish" : "";
  const installed = Boolean(state.gpu_service_installed && target);
  const running = Boolean(state.gpu_service_active);
  const atBoot = Boolean(state.gpu_service_enabled);
  const conflict = Boolean(state.gpu_service_conflict);
  const confirm = (enable: boolean) => showModal(<ConfirmModal
    strTitle={enable ? text.enableService : text.disableService}
    strDescription={(enable ? text.enableServiceHint : text.disableServiceHint).replace("{name}", name)}
    strOKButtonText={enable ? text.enableService : text.disableService}
    bDestructiveWarning={!enable}
    onOK={() => void execute(`GPU · ${text.governorService}`, () => setGpuGovernorService(enable), "gpu")}
  />);
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, marginTop: 6, padding: "9px 9px 9px" }}>
    <div style={{ color: tokens.colors.text, fontSize: 11, fontWeight: 650, margin: "0 2px 8px" }}>{text.governorService}</div>
    <ActionRow height={32}>
      <Action label={text.enableService} primary={installed && !running} disabled={busy || !installed || conflict || (running && atBoot)} onActivate={() => confirm(true)} />
      <Action label={text.disableService} danger disabled={busy || !installed || conflict || (!running && !atBoot)} onActivate={() => confirm(false)} />
    </ActionRow>
  </div>;
}

// Cyan's commented TOML points above 2000 MHz, as the switch it is. It sits at
// the top of "More frequencies", next to the points it unlocks. It asks first,
// and a cancelled question puts the switch back where the file is.
function HighPointsSwitch({ state, busy, execute }: {
  state: Status; busy: boolean;
  execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void>;
}) {
  const cyanActive = state.gpu_governor === "cyan";
  const enabled = (state.gpu_safe_point_ceilings ?? []).length > 0;
  const [revision, setRevision] = useState(0);
  const request = (next: boolean) => {
    if (next === enabled) return;
    showModal(<ConfirmModal
      strTitle={next ? text.enableHighPoints : text.disableHighPoints}
      strDescription={text.highFrequencyPointsHint}
      strOKButtonText={next ? text.enableHighPoints : text.disableHighPoints}
      bDestructiveWarning={next}
      onOK={() => void execute(text.highFrequencyPoints, () => setGpuHighFrequencyPoints(next), "gpu")}
      onCancel={() => setRevision((value) => value + 1)}
    />);
  };
  return <SwitchRow key={`${revision}-${enabled}`} label={text.unlockFrequencies} description={cyanActive ? text.highFrequencyPoints : text.highFrequencyCyanOnly} checked={enabled} danger disabled={busy || !cyanActive} onChange={request} />;
}

function Action({ label, disabled, primary, danger, onActivate }: { label: string; disabled: boolean; primary?: boolean; danger?: boolean; onActivate: () => void }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  return <PadButton disabled={disabled} onActivate={onActivate} style={{
    background: danger ? tokens.colors.red_soft : primary ? accent.focus : tokens.colors.panel_raised,
    border: `1px solid ${danger ? tokens.colors.red_soft : primary ? accent.focus : tokens.colors.border}`,
    color: danger ? tokens.colors.red : primary ? tokens.colors.selection : tokens.colors.text,
    alignItems: "center", boxSizing: "border-box", display: "flex", flex: 1, fontSize: 10, fontWeight: primary ? 700 : 600, height: "100%", minHeight: 32, justifyContent: "center", lineHeight: 1.15, minWidth: 0, padding: "4px 7px", textAlign: "center", whiteSpace: "normal", width: "100%",
  }}>{label}</PadButton>;
}

function ActionRow({ children, marginBottom = 0, height = 36 }: { children: ReactNode; marginBottom?: number; height?: number }) {
  return <Focusable flow-children="right" style={{ alignItems: "stretch", display: "flex", gap: 6, height, marginBottom, minHeight: height, width: "100%" }}>{children}</Focusable>;
}

function CompactSlider({ label, value, suffix, min, max, step, disabled, onChange, formatValue }: {
  label: string; value: number; suffix: string; min: number; max: number; step: number; disabled: boolean; onChange: (value: number) => void; formatValue?: (value: number) => string;
}) {
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginBottom: 4, padding: "4px 8px 0" }}>
    <div style={{ alignItems: "baseline", display: "flex", justifyContent: "space-between", marginBottom: -2 }}><span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{label}</span><b style={{ color: tokens.colors.text, fontSize: 11 }}>{formatValue ? formatValue(value) : value}{suffix}</b></div>
    <SliderField label="" layout="below" childrenContainerWidth="max" bottomSeparator="none" highlightOnFocus value={value} min={min} max={max} step={step} minimumDpadGranularity={step} validValues="steps" showValue={false} disabled={disabled} onChange={onChange} />
  </div>;
}

// Coefficients come from the shared contract, with the floor this copy used
// to drop: below it the upstream fit is not meaningful, and reporting a
// confident number there was a second disagreement with the Desktop.
type CpuVidModel = { square: number; p_base: number; p_scale: number; q_base: number; q_scale: number; floor_mhz: number };
function estimateCpuVid(frequency: number, scale: number, model?: CpuVidModel) {
  if (!model) return null;
  if (frequency < model.floor_mhz) return null;
  const p = model.p_base + scale * model.p_scale;
  const q = model.q_base + scale * model.q_scale;
  return Math.round(model.square * frequency * frequency + p * frequency + q);
}

function CuMatrix({ live, driver, draft, disabled, change, minimum }: { live: number[]; driver: number[]; draft: number[]; disabled: boolean; change: (masks: number[]) => void; minimum: () => void }) {
  const active = countWgps(draft);
  const cells = cuRows.flatMap((rowName, row) => [0, 1, 2, 3, 4].map((wgp) => {
    const selected = Boolean(draft[row] & (1 << wgp)); const routed = Boolean(live[row] & (1 << wgp)); const inDriver = Boolean(driver[row] & (1 << wgp)); const pending = selected !== routed;
    const token = selected ? inDriver ? "D+" : "S+" : inDriver ? "D!" : "—";
    const color = pending ? tokens.colors.amber : selected ? inDriver ? tokens.colors.green : tokens.colors.cyan : inDriver ? tokens.colors.red : tokens.colors.disabled_text;
    const background = pending ? tokens.colors.amber_soft : selected ? inDriver ? tokens.colors.green_soft : tokens.colors.cyan_soft : inDriver ? tokens.colors.red_soft : tokens.colors.panel_raised;
    return <PadButton key={`${rowName}-${wgp}`} label={`${rowName} WGP ${wgp} ${token}`} disabled={disabled} preferredFocus={row === 0 && wgp === 0}
      onActivate={() => { if (selected && active <= 12) { minimum(); return; } const next = draft.slice(); next[row] = selected ? next[row] & ~(1 << wgp) : next[row] | (1 << wgp); change(next); }}
      style={{ alignItems: "center", background, border: `1px solid ${pending ? tokens.colors.amber : tokens.colors.border}`, color, display: "flex", flexDirection: "column", fontSize: 9, fontWeight: 700, height: 30, justifyContent: "center", lineHeight: 1, minWidth: 0, padding: 0, width: "100%" }}>
      <span style={{ color: tokens.colors.muted, fontSize: 8, opacity: .72 }}>{row}.{wgp}</span><span style={{ color, marginTop: 2 }}>{token}</span>
    </PadButton>;
  }));
  return <><Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, boxSizing: "border-box", display: "grid", gap: 4, gridTemplateColumns: "repeat(5,minmax(0,1fr))", padding: 7, width: "100%" }}>{cells}</Focusable>
    <div style={{ color: tokens.colors.muted, display: "flex", fontSize: 10, gap: 8, margin: "6px 0" }}>{[[tokens.colors.green,"D+"],[tokens.colors.cyan,"S+"],[tokens.colors.amber,text.pending],[tokens.colors.red,"D!"]].map(([color,label]) => <span key={label} style={{ alignItems: "center", display: "flex", gap: 3 }}><i style={{ background: color, borderRadius: 2, height: 7, width: 7 }} />{label}</span>)}</div></>;
}

function MetricTile({ label, value, row = false }: { label: string; value: string; row?: boolean }) {
  if (row) {
    return <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between", padding: "7px 9px" }}>
      <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{label}</span>
      <span style={{ fontSize: 11, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</span>
    </div>;
  }
  return <div style={{ minWidth: 0, padding: "7px 8px" }}>
    <div style={{ color: tokens.colors.subtle, fontSize: 8 }}>{label}</div>
    <div style={{ fontSize: 11, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
  </div>;
}

function MetricGrid({ tiles }: { tiles: { label: string; value: string }[] }) {
  const { settings } = useContext(SettingsContext);
  const list = settings.sensorLayout === "list";
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gridTemplateColumns: list ? "1fr" : "1fr 1fr", marginBottom: 10, overflow: "hidden" }}>
    {tiles.map((tile, index) => <div key={tile.label} style={{ borderLeft: !list && index % 2 === 1 ? `1px solid ${tokens.colors.border}` : "none", borderTop: index >= (list ? 1 : 2) ? `1px solid ${tokens.colors.border}` : "none" }}><MetricTile label={tile.label} value={tile.value} row={list} /></div>)}
  </div>;
}

function UsageBar({ label, used, total, color }: { label: string; used: number | null; total: number | null; color: string }) {
  const percent = used != null && total != null && total > 0 ? Math.min(100, Math.round((used / total) * 100)) : null;
  return <div style={{ marginBottom: 8 }}>
    <div style={{ alignItems: "baseline", display: "flex", fontSize: 9, justifyContent: "space-between", marginBottom: 3 }}>
      <span style={{ color: tokens.colors.subtle }}>{label}</span>
      <span style={{ color: tokens.colors.text, fontWeight: 650 }}>
        {used != null && total != null ? `${formatBytes(used)} / ${formatBytes(total)}` : "—"}
        {percent != null ? ` · ${percent}%` : ""}
      </span>
    </div>
    <div style={{ background: tokens.colors.progress_track, borderRadius: 3, height: 6, overflow: "hidden", width: "100%" }}>
      <div style={{ background: color, height: "100%", width: `${percent ?? 0}%` }} />
    </div>
  </div>;
}

function StatusRow({ label, value, active }: { label: string; value: string; active: boolean | null }) {
  const color = active == null ? tokens.colors.subtle : active ? tokens.colors.green : tokens.colors.disabled_text;
  return <div style={{ alignItems: "center", display: "flex", fontSize: 10, justifyContent: "space-between", padding: "7px 9px" }}>
    <span style={{ color: tokens.colors.subtle }}>{label}</span>
    <span style={{ color, fontWeight: 650 }}>{value}</span>
  </div>;
}

type CoreEntry = { core: number; core_id?: number | null; percent: number | null; frequency_mhz: number | null };

// Logical CPUs grouped by physical core. The panel used to draw every SMT
// thread as its own "core" (12 tiles for 6 cores), and the die's two locked
// cores not at all. A core's id is its die position, so a missing id is a
// locked core.
function physicalCores(cores: CoreEntry[], slots?: number | null) {
  const known = cores.some((entry) => typeof entry.core_id === "number");
  if (!known) return cores.map((entry, index) => ({ id: index, threads: [entry] }));
  const total = Math.max(slots ?? 8, ...cores.map((entry) => (entry.core_id ?? 0) + 1));
  return Array.from({ length: total }, (_unused, id) => ({ id, threads: cores.filter((entry) => entry.core_id === id) }));
}

function CoreGrid({ cores, slots }: { cores: CoreEntry[]; slots?: number | null }) {
  const accent = useAccent();
  if (!cores.length) return null;
  const groups = physicalCores(cores, slots);
  const active = groups.filter((group) => group.threads.length > 0).length;
  // An idle thread reports the nominal clock, not a live one: a core shows
  // the clock of its busier thread, or the lower one when both idle.
  const busiest = (threads: CoreEntry[]) => {
    const lead = threads.reduce((best, entry) => (entry.percent ?? -1) > (best?.percent ?? -1) ? entry : best, threads[0]);
    if ((lead?.percent ?? 0) >= 1) return lead;
    return threads.reduce((low, entry) => (entry.frequency_mhz ?? Infinity) < (low?.frequency_mhz ?? Infinity) ? entry : low, threads[0]);
  };
  // One column per physical core: the bar's height is the core's load, its
  // clock and number underneath. Locked cores keep their column, empty.
  return <div style={{ background: tokens.colors.panel_alt, borderRadius: 6, marginBottom: 10, padding: "7px 8px 6px" }}>
    <div style={{ color: tokens.colors.subtle, fontSize: 9, marginBottom: 6 }}>{text.cpuCoresSummary.replace("{active}", String(active)).replace("{total}", String(groups.length)).replace("{threads}", String(cores.length))}</div>
    <div style={{ display: "grid", gap: 4, gridTemplateColumns: `repeat(${groups.length},minmax(0,1fr))` }}>
      {groups.map((group) => {
        const locked = !group.threads.length;
        const lead = locked ? undefined : busiest(group.threads);
        const usage = group.threads.filter((entry) => entry.percent != null);
        const load = usage.length ? Math.round(usage.reduce((sum, entry) => sum + (entry.percent ?? 0), 0) / usage.length) : 0;
        const tone = load >= 85 ? tokens.colors.red : load >= 60 ? tokens.colors.amber : accent.focus;
        return <div key={group.id} title={locked ? text.cpuCoreLocked : `${load}%`} style={{ alignItems: "center", display: "flex", flexDirection: "column", gap: 3, opacity: locked ? .4 : 1 }}>
          <div style={{ alignItems: "flex-end", background: tokens.colors.panel, border: locked ? `1px dashed ${tokens.colors.border}` : "none", borderRadius: 3, display: "flex", height: 34, overflow: "hidden", width: "100%" }}>
            {locked ? null : <div style={{ background: tone, height: `${Math.max(4, Math.min(100, load))}%`, transition: "height .4s ease", width: "100%" }} />}
          </div>
          <div style={{ fontSize: 9, fontWeight: 650, whiteSpace: "nowrap" }}>{lead?.frequency_mhz != null ? (lead.frequency_mhz / 1000).toFixed(1) : "—"}</div>
          <div style={{ color: tokens.colors.subtle, fontSize: 8 }}>{group.id + 1}</div>
        </div>;
      })}
    </div>
  </div>;
}

type MonitorSection = "cpu" | "gpu" | "cooling" | "all";

function SubNav<T extends string>({ value, onChange, items }: { value: T; onChange: (next: T) => void; items: { key: T; label: string; icon: ReactNode; color: string; colorSoft: string }[] }) {
  return <Focusable flow-children="row" style={{ display: "grid", gap: 5, gridTemplateColumns: `repeat(${items.length},minmax(0,1fr))`, marginBottom: 10 }}>
    {items.map((item) => {
      const active = item.key === value;
      return <PadButton key={item.key} label={item.label} onActivate={() => onChange(item.key)} style={{ alignItems: "center", background: active ? item.colorSoft : tokens.colors.panel_alt, border: `1px solid ${active ? item.color : tokens.colors.border}`, color: active ? item.color : tokens.colors.subtle, display: "flex", fontSize: 18, height: 36, justifyContent: "center", padding: 0 }}>
        {item.icon}
      </PadButton>;
    })}
  </Focusable>;
}

// The GDDR6 panel's own switch, one slim row: on starts a live session (and,
// quietly, this boot's SMU patch when it is missing); off stops every GDDR6
// read, so nothing reaches the SMU for it until it is turned on again.
// The one switch design of the whole panel: the name on the left, an optional
// quiet description under it, and a slim pill on the right -- off is dark with
// a grey knob, on takes the accent (red for a dangerous setting). A single
// controller stop that A toggles; Steam's own ToggleField is no longer used.
function SwitchRow({ label, description, checked, disabled = false, danger = false, onChange }: { label: string; description?: string; checked: boolean; disabled?: boolean; danger?: boolean; onChange: (next: boolean) => void }) {
  const accent = useAccent();
  const tone = danger ? tokens.colors.red : accent.focus;
  return <PadButton label={label} disabled={disabled} onActivate={() => onChange(!checked)} style={{ alignItems: "center", background: "transparent", border: "none", display: "flex", gap: 10, justifyContent: "space-between", minHeight: 34, padding: "4px 8px", textAlign: "left", width: "100%" }}>
    <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <span style={{ color: tokens.colors.text, fontSize: 11, fontWeight: 650 }}>{label}</span>
      {description ? <span style={{ color: tokens.colors.subtle, fontSize: 9, fontWeight: 400, lineHeight: 1.3 }}>{description}</span> : null}
    </span>
    <span style={{ background: checked ? tone : tokens.colors.panel_raised, border: `1px solid ${checked ? tone : tokens.colors.border}`, borderRadius: 10, display: "inline-block", flex: "0 0 auto", height: 18, position: "relative", transition: "background .2s ease", width: 34 }}>
      <span style={{ background: checked ? "#FFFFFF" : tokens.colors.subtle, borderRadius: "50%", height: 14, left: checked ? 17 : 2, position: "absolute", top: 1, transition: "left .2s ease", width: 14 }} />
    </span>
  </PadButton>;
}

function Gddr6Switch() {
  const { gddr6 } = useContext(SettingsContext);
  return <div style={{ margin: "2px 0 6px" }}><SwitchRow label={text.memoryMonitoring} checked={gddr6.live} onChange={gddr6.setLive} /></div>;
}

// The switch sits OUTSIDE any ScrollStop: a ScrollStop is a Focusable with a
// no-op activate, and wrapped in one the controller landed on it and swallowed
// A -- the switch could be selected but never toggled. Only the read-only
// temperatures below it are a scroll stop.
function Gddr6Panel({ state }: { state: Status }) {
  const panelContext = useContext(SettingsContext);
  const accent = ACCENT_SWATCHES[panelContext.settings.accent];
  if (!panelContext.gddr6.live) return <div style={{ marginBottom: 6 }}><Gddr6Switch /></div>;
  const chips = state.gddr6_chips ?? [];
  const available = Boolean(state.gddr6_available) && chips.length > 0;
  return <div style={{ marginBottom: 6 }}>
    <Gddr6Switch />
    <ScrollStop>
      {!available
        ? state.gddr6_patch_error
          ? <div style={{ color: tokens.colors.red, fontSize: 9, lineHeight: 1.35, margin: "0 2px 6px", overflowWrap: "anywhere" }}>{state.gddr6_patch_error.replace(/^QUICK_ACCESS_GDDR6:\s*/, "")}</div>
          : <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 6px" }}>{state.gddr6_reason === "GDDR6_PATCH_INACTIVE" ? text.gddr6Patching : text.gddr6Unavailable}</div>
        : <>
          <MetricGrid tiles={[
            { label: "AVG", value: state.gddr6_average_c != null ? `${state.gddr6_average_c.toFixed(1)} °C` : "—" },
            { label: "HOTSPOT", value: state.gddr6_hotspot_c != null ? `${state.gddr6_hotspot_c.toFixed(1)} °C` : "—" },
          ]} />
          <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gap: 1, gridTemplateColumns: "repeat(4,minmax(0,1fr))", overflow: "hidden" }}>
            {chips.map((chip) => <div key={chip.chip} style={{ background: chip.chip === state.gddr6_hotspot_chip ? accent.focus_soft : tokens.colors.panel_raised, padding: "6px 7px" }}>
              <div style={{ color: tokens.colors.subtle, fontSize: 8 }}>CHIP {chip.chip}</div>
              <div style={{ fontSize: 10, fontWeight: 650 }}>{chip.temperature_c.toFixed(1)} °C</div>
            </div>)}
          </div>
        </>}
    </ScrollStop>
  </div>;
}

// Read-only sensor tiles are plain divs, and a Quick Access panel scrolls only
// to reveal the element the controller has focused: with nothing focusable
// under the sub-tabs, "down" had nowhere to go and every sensor below the
// fold was out of reach. Each block is a quiet focus stop -- outlined in the
// accent while focused, so the player sees where they are -- and an invisible
// stop at the very end carries the scroll to the bottom of the section.
function ScrollStop({ children, end = false }: { children?: ReactNode; end?: boolean }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const [focused, setFocused] = useState(false);
  const focusEvents = {
    onGamepadFocus: () => setFocused(true),
    onGamepadBlur: () => setFocused(false),
  } as Record<string, unknown>;
  return <Focusable noFocusRing onActivate={() => undefined} {...focusEvents}
    style={end
      ? { height: 16 }
      : { borderRadius: 8, boxShadow: focused ? `0 0 0 1px ${accent.focus}` : "none", marginBottom: 2, padding: 1, transition: "box-shadow 90ms ease" }}>
    {children ?? <span />}
  </Focusable>;
}

// A GPU or CPU profile as one card: its name and the figure it sets. The one in
// force carries the accent and a small dot in the corner.
function ProfileCard({ title, detail, current, disabled, preferredFocus, onActivate }: { title: string; detail: string; current: boolean; disabled: boolean; preferredFocus?: boolean; onActivate: () => void }) {
  const accent = useAccent();
  return <PadButton label={title} disabled={disabled} preferredFocus={preferredFocus} onActivate={onActivate} style={{ alignItems: "stretch", background: current ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, display: "flex", flexDirection: "column", gap: 3, height: 54, justifyContent: "center", minWidth: 0, padding: "7px 8px", position: "relative", textAlign: "left", width: "100%" }}>
    {current ? <span style={{ background: accent.focus, borderRadius: "50%", height: 6, position: "absolute", right: 8, top: 8, width: 6 }} /> : null}
    <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
      <span style={{ WebkitBoxOrient: "vertical", WebkitLineClamp: 2, color: current ? accent.focus : tokens.colors.text, display: "-webkit-box", fontSize: 10.5, fontWeight: 650, lineHeight: 1.15, overflow: "hidden", overflowWrap: "anywhere", paddingRight: current ? 8 : 0 }}>{title}</span>
      <span style={{ color: tokens.colors.subtle, fontSize: 8.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{detail}</span>
    </span>
  </PadButton>;
}

// 500 -> "0.5", 1850 -> "1.85", 2000 -> "2": gigahertz without trailing zeros.
const ghz = (mhz: number) => String(Number((mhz / 1000).toFixed(2)));


// ---- the drawers of the settings tab -------------------------------------
// One look for what opens under a DisclosureRow: a quiet panel, small spaced
// labels, joined segmented choices instead of a row of separate buttons, and
// hairline dividers between groups.
function Drawer({ children }: { children: ReactNode }) {
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, marginBottom: 8, padding: "8px 8px 6px" }}>{children}</div>;
}

function DrawerLabel({ children }: { children: ReactNode }) {
  return <div style={{ color: tokens.colors.subtle, fontSize: 8.5, fontWeight: 650, letterSpacing: ".08em", margin: "2px 2px 5px", textTransform: "uppercase" }}>{children}</div>;
}

function Divider() {
  return <div style={{ background: tokens.colors.border_soft, height: 1, margin: "6px 0" }} />;
}

function Segmented({ options, value, onChange, disabled = false, columns }: { options: { key: string; label: string }[]; value: string | null; onChange: (key: string) => void; disabled?: boolean; columns?: number }) {
  const accent = useAccent();
  return <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ background: tokens.colors.panel, borderRadius: 8, display: "grid", gap: 2, gridTemplateColumns: `repeat(${columns ?? options.length},minmax(0,1fr))`, marginBottom: 8, padding: 2 }}>
    {options.map((option) => {
      const selected = option.key === value;
      return <PadButton key={option.key} label={option.label} disabled={disabled} preferredFocus={selected} onActivate={() => onChange(option.key)} style={{ alignItems: "center", background: selected ? accent.focus_soft : "transparent", border: selected ? `1px solid ${accent.focus}` : "1px solid transparent", borderRadius: 6, color: selected ? accent.focus : tokens.colors.muted, display: "flex", fontSize: 10, fontWeight: 650, height: 28, justifyContent: "center", overflow: "hidden", padding: "0 4px", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{option.label}</PadButton>;
    })}
  </Focusable>;
}

// One header for every drop-down row of the GPU settings (more frequencies,
// voltage lab, kernel compatibility): the name on the left, which may shorten
// but never collides, the current choice as a small pill and the chevron on
// the right.
function DisclosureRow({ label, value, open, onActivate, disabled = false, warn = false }: { label: string; value?: string; open: boolean; onActivate: () => void; disabled?: boolean; warn?: boolean }) {
  const accent = useAccent();
  const tone = warn ? tokens.colors.amber : accent.focus;
  return <PadButton onActivate={onActivate} disabled={disabled} style={{ alignItems: "center", display: "flex", fontSize: 11, gap: 10, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 10px", width: "100%" }}>
    <span style={{ flex: "1 1 auto", minWidth: 0, overflow: "hidden", textAlign: "left", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
    <span style={{ alignItems: "center", display: "flex", flex: "0 0 auto", gap: 6 }}>
      {value ? <span style={{ background: warn ? tokens.colors.amber_soft : accent.focus_soft, borderRadius: 10, color: tone, fontSize: 9, fontWeight: 650, padding: "2px 8px", whiteSpace: "nowrap" }}>{value}</span> : null}
      <span style={{ color: tone, fontSize: 10 }}>{open ? "▴" : "▾"}</span>
    </span>
  </PadButton>;
}

const VOLTAGE_LEVELS = [0, 1, 2, 3] as const;
const VOLTAGE_STEP_MV = 5;
const VOLTAGE_MAX_ABOVE_DEFAULT_MV = 60;

// The desktop's "Cyan kernel compatibility", for the same reason it is there:
// on a kernel without the BC-250 patches the way Cyan reads GPU usage decides
// whether it keeps answering. The "process" reading walks every open file of
// every program, so with a game open Cyan stops answering and the range, the
// high points and the voltage lab stop working with it. Switching to
// busy-flag from here is how it recovers without leaving Game Mode.
const COMPAT_SET_METHODS = ["smu", "kernel"] as const;
const COMPAT_USAGE_METHODS = ["busy-flag", "process", "kernel"] as const;

function CyanCompatibility({ state, busy, execute }: { state: Status; busy: boolean; execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void> }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const current = state.gpu_compatibility ?? null;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<GpuCompatibility | null>(null);
  const keyOf = (value: GpuCompatibility) => `${value.set_method}:${value.usage_method}:${value.fix_metrics}:${value.fix_frequency}`;
  const signature = current ? keyOf(current) : "";
  useEffect(() => { setDraft(null); }, [signature]);
  if (state.gpu_governor === "oberon" || !current) return null;
  const value = draft ?? current;
  const changed = keyOf(value) !== signature;
  // Editable while Cyan is stopped, as on the desktop: a "kernel" choice this
  // kernel cannot serve is exactly what stops Cyan, so requiring it to run
  // made that choice impossible to undo from Game Mode.
  const cyanActive = state.gpu_governor !== "conflict" && state.gpu_service_target === "cyan" && Boolean(state.gpu_service_installed);
  const cyanRunningNow = state.gpu_governor === "cyan";
  const choose = (patch: Partial<GpuCompatibility>) => setDraft({ ...value, ...patch });
  const confirm = () => showModal(<ConfirmModal
    strTitle={text.compatTitle}
    strDescription={text.compatConfirm}
    strOKButtonText={text.compatApply}
    onOK={() => void execute(`GPU · ${text.compatTitle}`, () => applyGpuCompatibility(value.set_method, value.usage_method, value.fix_metrics, value.fix_frequency), "gpu")} />);
  return <>
    <DisclosureRow label={text.compatTitle} value={`${current.set_method === "smu" ? "SMU" : "Kernel"} · ${current.usage_method}`} open={open} warn={current.usage_method === "process"} onActivate={() => setOpen(!open)} />
    {open ? <Drawer>
      {!cyanActive ? <div style={{ color: tokens.colors.amber, fontSize: 9, margin: "0 2px 6px" }}>{text.compatNeedsCyan}</div> : null}
      {cyanActive && !cyanRunningNow ? <div style={{ color: tokens.colors.amber, fontSize: 9, margin: "0 2px 6px" }}>{text.compatStaged}</div> : null}
      <DrawerLabel>{text.compatSetMethod}</DrawerLabel>
      <Segmented disabled={busy || !cyanActive} value={value.set_method} onChange={(method) => choose({ set_method: method as GpuCompatibility["set_method"] })}
        options={COMPAT_SET_METHODS.map((method) => ({ key: method, label: method === "smu" ? "SMU" : "Kernel" }))} />
      <DrawerLabel>{text.compatUsage}</DrawerLabel>
      <Segmented disabled={busy || !cyanActive} value={value.usage_method} onChange={(method) => choose({ usage_method: method as GpuCompatibility["usage_method"] })}
        options={COMPAT_USAGE_METHODS.map((method) => ({ key: method, label: method }))} />
      {value.usage_method === "process" ? <div style={{ color: tokens.colors.amber, fontSize: 9, lineHeight: 1.35, margin: "-2px 2px 6px" }}>{text.compatProcessWarning}</div> : null}
      <Divider />
      <SwitchRow label={text.compatFixMetrics} checked={value.fix_metrics} disabled={busy || !cyanActive} onChange={(checked) => choose({ fix_metrics: checked })} />
      <SwitchRow label={text.compatFixFrequency} checked={value.fix_frequency} disabled={busy || !cyanActive} onChange={(checked) => choose({ fix_frequency: checked })} />
      <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.35, margin: "2px 8px 8px" }}>{text.compatHint}</div>
      <ActionRow marginBottom={2}><Action label={text.compatApply} primary disabled={busy || !cyanActive || !changed} onActivate={confirm} /><Action label={text.voltageDiscard} disabled={busy || !changed} onActivate={() => setDraft(null)} /></ActionRow>
    </Drawer> : null}
  </>;
}

// The desktop voltage drawer, cut down to what a controller can do safely:
// the governor curve or +10/+20/+30 mV on the points from 2000 MHz up, and a
// per-point nudge in 5 mV steps that can never go below the governor value
// or more than 60 mV above it. The helper re-checks every bound.
function VoltageLab({ state, busy, execute }: { state: Status; busy: boolean; execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void> }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const [open, setOpen] = useState(false);
  const points = (state.gpu_voltage_points ?? []).filter((point) => point.frequency >= 2000);
  const [draft, setDraft] = useState<Record<number, number>>({});
  const signature = points.map((point) => `${point.frequency}:${point.voltage}`).join(",");
  useEffect(() => { setDraft({}); }, [signature]);
  const cyanRunning = state.gpu_governor === "cyan" && Boolean(state.gpu_service_active ?? state.cyan_active);
  const level = state.gpu_voltage_level;
  const levelLabel = level == null ? text.voltageCustom : level === 0 ? text.voltageGovernor : `+${level * 10} mV`;
  if (state.gpu_governor === "oberon") return null;
  const valueOf = (point: VoltagePoint) => draft[point.frequency] ?? point.voltage;
  const floorOf = (point: VoltagePoint) => point.default || point.voltage;
  const nudge = (point: VoltagePoint, delta: number) => {
    const index = points.indexOf(point);
    const below = index > 0 ? valueOf(points[index - 1]) : 0;
    const above = index < points.length - 1 ? valueOf(points[index + 1]) : 1210;
    const next = Math.max(floorOf(point), below, Math.min(floorOf(point) + VOLTAGE_MAX_ABOVE_DEFAULT_MV, above, valueOf(point) + delta));
    setDraft({ ...draft, [point.frequency]: next });
  };
  const changed = points.filter((point) => valueOf(point) !== point.voltage);
  const confirmLevel = (value: number) => showModal(<ConfirmModal
    strTitle={text.voltageLab}
    strDescription={text.voltageConfirm}
    strOKButtonText={value === 0 ? text.voltageGovernor : `+${value * 10} mV`}
    onOK={() => void execute(`GPU · ${text.voltageLab}`, () => applyGpuVoltageLevel(value), "gpu")} />);
  const confirmPoints = () => showModal(<ConfirmModal
    strTitle={text.voltageLab}
    strDescription={text.voltageConfirm}
    strOKButtonText={text.voltageApplyPoints}
    onOK={() => void execute(`GPU · ${text.voltageLab}`, () => applyGpuVoltagePoints(changed.map((point) => ({ frequency: point.frequency, voltage: valueOf(point) }))), "gpu")} />);
  return <>
    <DisclosureRow label={text.voltageLab} value={points.length ? levelLabel : text.unavailable} open={open} disabled={!points.length} onActivate={() => setOpen(!open)} />
    {open ? <Drawer>
      {!cyanRunning ? <div style={{ color: tokens.colors.amber, fontSize: 9, margin: "0 2px 6px" }}>{text.voltageNeedsCyan}</div> : null}
      <DrawerLabel>{text.voltageLab}</DrawerLabel>
      <Segmented disabled={busy || !cyanRunning} value={level == null ? null : String(level)} onChange={(key) => { if (Number(key) !== level) confirmLevel(Number(key)); }}
        options={VOLTAGE_LEVELS.map((value) => ({ key: String(value), label: value === 0 ? text.voltageGovernor : `+${value * 10} mV` }))} />
      <div style={{ background: tokens.colors.panel, borderRadius: 8, padding: "2px 8px" }}>
        <Focusable flow-children="down">
          {points.map((point, index) => {
            const value = valueOf(point);
            const moved = value !== point.voltage;
            return <Focusable key={point.frequency} flow-children="row" style={{ alignItems: "center", borderTop: index ? `1px solid ${tokens.colors.border_soft}` : "none", display: "grid", gap: 6, gridTemplateColumns: "1fr 28px 64px 28px", padding: "5px 0" }}>
              <span style={{ color: tokens.colors.muted, fontSize: 10, fontWeight: 650 }}>{ghz(point.frequency)} GHz</span>
              <PadButton label="-5 mV" disabled={busy || !cyanRunning || value <= floorOf(point)} onActivate={() => nudge(point, -VOLTAGE_STEP_MV)} style={{ borderRadius: 14, fontSize: 13, height: 26, padding: 0, width: "100%" }}>−</PadButton>
              <span style={{ color: moved ? accent.focus : tokens.colors.text, fontSize: 11, fontWeight: 650, textAlign: "center" }}>{value} mV</span>
              <PadButton label="+5 mV" disabled={busy || !cyanRunning || value >= floorOf(point) + VOLTAGE_MAX_ABOVE_DEFAULT_MV} onActivate={() => nudge(point, VOLTAGE_STEP_MV)} style={{ borderRadius: 14, fontSize: 13, height: 26, padding: 0, width: "100%" }}>+</PadButton>
            </Focusable>;
          })}
        </Focusable>
      </div>
      <div style={{ height: 8 }} />
      <ActionRow marginBottom={2}><Action label={text.voltageApplyPoints} primary disabled={busy || !cyanRunning || !changed.length} onActivate={confirmPoints} /><Action label={text.voltageDiscard} disabled={busy || !changed.length} onActivate={() => setDraft({})} /></ActionRow>
    </Drawer> : null}
  </>;
}

// Desktop defaults arrive with an English name; show them in the panel's language.
const cpuPresetName = (preset: CpuPreset) => preset.default ? ({ board_average: text.cpuPresetBoardAverage, mid_point: text.cpuPresetMidPoint, safe_maximum: text.cpuPresetSafeMaximum } as Record<string, string>)[preset.key] ?? preset.name : preset.name;

// Monitoring › CPU: what a CPU run is doing while it runs, then the result on top.
// The player is not moved here; the run's progress is also in the CPU settings.
function cpuRunNotice(state: Status, cpuRun: { target: number; elapsed: number } | null | undefined) {
  const box: CSSProperties = { alignItems: "center", background: tokens.colors.green_soft, border: `1px solid ${tokens.colors.green}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 7, padding: "6px 8px" };
  if (cpuRun) return <div role="status" aria-live="polite" style={box}><span style={{ color: tokens.colors.green, lineHeight: 1.35 }}>{text.cpuMonitorApplying.replace("{target}", String(cpuRun.target))}</span><b style={{ color: tokens.colors.green, whiteSpace: "nowrap" }}>{cpuRun.elapsed}s</b></div>;
  const detected = state.cpu_detected_profile;
  if (!detected?.ready) return null;
  const active = state.cpu_active_profile ?? detected.active_profile;
  const frequency = active?.frequency ?? detected.frequency;
  const scale = active?.scale ?? detected.scale;
  return <div style={box}><span style={{ color: tokens.colors.subtle }}>{text.cpuDetected}</span><b style={{ color: tokens.colors.green }}>{`${frequency} MHz · scale ${scale}`}</b></div>;
}

// Monitoring › CPU, as two cards instead of an eight-row list: what the CPU
// is doing now (clock, temperature, load, voltage) and what overclock it runs.
// The list mixed the sensor voltage and the overclock's estimated VID under
// the same label, and called the live average a "target".
function heatTone(celsius: number | null | undefined, normal: string = tokens.colors.green) {
  if (celsius == null) return tokens.colors.text;
  return celsius >= 85 ? tokens.colors.red : celsius >= 75 ? tokens.colors.amber : normal;
}

// Clock and temperature as headlines, a thin load bar, load and voltage under
// it: shared by Monitoring › CPU and › GPU so the two read alike.
function ChipOverview({ mhz, celsius, usage, millivolts }: { mhz: number | null | undefined; celsius: number | null | undefined; usage: number | null | undefined; millivolts: number | null | undefined }) {
  const accent = useAccent();
  const ghz = mhz != null ? (mhz / 1000).toFixed(2) : "—";
  return <div style={{ background: tokens.colors.panel_alt, borderRadius: 6, marginBottom: 8, padding: "8px 10px" }}>
    <div style={{ alignItems: "flex-end", display: "flex", justifyContent: "space-between" }}>
      <div><div style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.cpuNow}</div><div style={{ fontSize: 18, fontWeight: 700 }}>{ghz} <span style={{ color: tokens.colors.subtle, fontSize: 10, fontWeight: 500 }}>GHz</span></div></div>
      <div style={{ textAlign: "right" }}><div style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.cpuTemperature}</div><div style={{ color: heatTone(celsius, accent.focus), fontSize: 18, fontWeight: 700 }}>{celsius != null ? celsius.toFixed(1) : "—"} <span style={{ color: tokens.colors.subtle, fontSize: 10, fontWeight: 500 }}>°C</span></div></div>
    </div>
    <div style={{ background: tokens.colors.panel, borderRadius: 2, height: 3, margin: "7px 0 5px", overflow: "hidden" }}><div style={{ background: accent.focus, height: "100%", transition: "width .4s ease", width: `${Math.max(1, Math.min(100, usage ?? 0))}%` }} /></div>
    <div style={{ color: tokens.colors.subtle, display: "flex", fontSize: 9, justifyContent: "space-between" }}><span>{text.usage} <b style={{ color: tokens.colors.text }}>{usage != null ? `${usage}%` : "—"}</b></span><span>{text.gpuVoltage} <b style={{ color: tokens.colors.text }}>{millivolts != null ? `${millivolts} mV` : "—"}</b></span></div>
  </div>;
}

function CpuOverview({ state }: { state: Status }) {
  return <ChipOverview mhz={state.cpu_frequency_mhz} celsius={state.cpu_temperature_c} usage={state.cpu_usage_percent} millivolts={state.cpu_voltage_mv} />;
}

// Rows of name and value on one panel: the overclock and GPU detail cards.
function DetailCard({ title, status, statusOn, rows, children }: { title: string; status?: string; statusOn?: boolean; rows: [string, string][]; children?: ReactNode }) {
  const accent = useAccent();
  return <div style={{ background: tokens.colors.panel_alt, borderRadius: 6, marginBottom: 8, padding: "6px 10px 4px" }}>
    <div style={{ display: "flex", fontSize: 10, justifyContent: "space-between", padding: "2px 0 5px" }}><b>{title}</b>{status ? <span style={{ color: statusOn ? accent.focus : tokens.colors.subtle, fontSize: 9 }}>{status}</span> : null}</div>
    {rows.map(([name, value]) => <div key={name} style={{ borderTop: `1px solid ${tokens.colors.border}`, display: "flex", fontSize: 10, gap: 8, justifyContent: "space-between", padding: "4px 0" }}><span style={{ color: tokens.colors.subtle, whiteSpace: "nowrap" }}>{name}</span><span style={{ overflow: "hidden", textAlign: "right", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</span></div>)}
    {children}
  </div>;
}

function CpuOcCard({ state }: { state: Status }) {
  const active = state.cpu_active_profile ?? state.cpu_detected_profile?.active_profile;
  const mode = !active ? "—" : active.mode === "manual" ? text.cpuManual : active.mode === "boot" ? text.cpuModeBoot : text.automatic;
  const rows: [string, string][] = [
    [text.mode, mode],
    ["OC", active ? `${active.frequency} MHz` : "—"],
    [active?.mode === "manual" ? text.cpuScale : text.cpuEstimatedVid, !active ? "—" : active.mode === "manual" ? String(active.scale) : `${active.estimated_vid} mV`],
    // "persistable" only means it may be installed; the boot service decides.
    [text.cpuOnBoot, state.cpu_service_enabled === true ? text.enabled : text.disabled],
    [text.cpuThermalLimit, `${state.cpu_tuning_temperature ?? "—"} °C`],
  ];
  return <DetailCard title={text.cpuOcTitle} status={active ? text.enabled : text.disabled} statusOn={Boolean(active)} rows={rows} />;
}

// Without the I2C modification a rail has nothing to report: one line, not
// four rows of dashes.
function RailVrm({ state, label, tiles }: { state: Status; label: string; tiles: { label: string; value: string }[] }) {
  if (state.vrm_available) return <MetricGrid tiles={tiles} />;
  return <div style={{ alignItems: "center", border: `1px dashed ${tokens.colors.border}`, borderRadius: 6, color: tokens.colors.subtle, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 10, padding: "6px 8px" }}><b style={{ color: tokens.colors.text, fontSize: 9, whiteSpace: "nowrap" }}>{label}</b><span style={{ textAlign: "right" }}>{text.vrmUnavailable}</span></div>;
}

// Async compute as one slim meter: share of time on the compute queues.
function AceMeter({ state }: { state: Status }) {
  const accent = useAccent();
  const game = useRunningGame();
  const percent = state.ace_busy_percent;
  const available = Boolean(state.ace_available);
  const active = typeof percent === "number" && percent > 0;
  const who = active ? (game?.name || state.ace_process || "") : "";
  return <div title={who || undefined} style={{ alignItems: "center", background: tokens.colors.panel_alt, borderRadius: 6, display: "flex", fontSize: 9, gap: 8, marginBottom: 8, padding: "6px 10px" }}>
    <span style={{ color: tokens.colors.subtle, whiteSpace: "nowrap" }}>Async compute</span>
    <div style={{ background: tokens.colors.panel, borderRadius: 2, flex: 1, height: 3, overflow: "hidden" }}><div style={{ background: accent.focus, height: "100%", transition: "width .4s ease", width: `${active ? Math.max(2, Math.min(100, percent ?? 0)) : 0}%` }} /></div>
    <b style={{ color: active ? accent.focus : tokens.colors.subtle, minWidth: 26, textAlign: "right" }}>{!available || percent == null ? "—" : `${percent}%`}</b>
  </div>;
}

function GpuDetails({ state }: { state: Status }) {
  const accent = useAccent();
  const mhz = (value: number | null | undefined) => value != null ? `${value} MHz` : "—";
  const range = (pair: [number, number] | null | undefined) => pair ? `${pair[0]}–${pair[1]} MHz` : "—";
  const rows: [string, string][] = [
    [text.governor, state.gpu_governor_label || "—"],
    [text.gpuActiveRange, range(state.gpu_range)],
    [text.gpuValidatedRange, range(state.gpu_allowed_range)],
    ["CU", state.cu_active_cus != null && state.cu_total_cus != null ? `${state.cu_active_cus} / ${state.cu_total_cus}` : "—"],
    [text.gpuMemoryClock, mhz(state.gpu_memory_clock_mhz)],
    [text.gpuSocClock, mhz(state.gpu_soc_clock_mhz)],
    [text.gpuFabricClock, mhz(state.gpu_fabric_clock_mhz)],
    ["PCIe", state.gpu_pcie_link || "—"],
    ["VBIOS", state.gpu_vbios_version || "—"],
  ];
  const mib = 1024 * 1024;
  return <DetailCard title={text.gpuDetails} rows={rows}>
    <div style={{ borderTop: `1px solid ${tokens.colors.border}`, paddingTop: 6 }}>
      <UsageBar label="VRAM" used={state.gpu_vram_used_mib != null ? state.gpu_vram_used_mib * mib : null} total={state.gpu_vram_total_mib != null ? state.gpu_vram_total_mib * mib : null} color={accent.focus} />
      <UsageBar label="GTT" used={state.gpu_gtt_used_mib != null ? state.gpu_gtt_used_mib * mib : null} total={state.gpu_gtt_total_mib != null ? state.gpu_gtt_total_mib * mib : null} color={tokens.colors.cyan} />
    </div>
  </DetailCard>;
}

function GpuOverview({ state }: { state: Status }) {
  return <ChipOverview mhz={state.gpu_core_mhz} celsius={state.gpu_temperature_c} usage={state.gpu_busy_percent} millivolts={state.gpu_voltage_mv} />;
}

// Monitoring › All: the fans as one card, a slim duty bar per channel.
function FanCard({ state }: { state: Status }) {
  const options = state.fan_channel_options ?? [];
  const lead = options.find((option) => option.channel === 2) ?? options[0];
  const mode = typeof lead?.mode === "string" ? lead.mode : lead?.mode != null ? String(lead.mode) : "";
  return <div style={{ background: tokens.colors.panel_alt, borderRadius: 6, marginBottom: 8, padding: "6px 10px 6px" }}>
    <div style={{ display: "flex", fontSize: 10, justifyContent: "space-between", padding: "2px 0 5px" }}><b>{text.fans}</b>{mode ? <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{mode}</span> : null}</div>
    {fanChannels.map((channel) => {
      const option = options.find((item) => item.channel === channel);
      const available = Boolean(option?.available);
      const percent = available ? option?.percent ?? null : null;
      return <div key={channel} style={{ borderTop: `1px solid ${tokens.colors.border}`, opacity: available ? 1 : .45, padding: "5px 0" }}>
        <div style={{ display: "flex", fontSize: 10, justifyContent: "space-between", marginBottom: 3 }}>
          <span style={{ color: tokens.colors.subtle }}>{option?.label ?? `PWM ${channel}`}</span>
          <span>{!available ? text.unavailable : `${percent ?? "—"}%${option?.rpm_observed && option.rpm != null ? ` · ${option.rpm} RPM` : ""}`}</span>
        </div>
        <div style={{ background: tokens.colors.panel, borderRadius: 2, height: 3, overflow: "hidden" }}><div style={{ background: tokens.colors.cyan, height: "100%", transition: "width .4s ease", width: `${Math.max(0, Math.min(100, percent ?? 0))}%` }} /></div>
      </div>;
    })}
  </div>;
}

// Board temperatures as rows, each coloured by heat like the CPU/GPU headlines.
function BoardCard({ state }: { state: Status }) {
  const accent = useAccent();
  const rows: [string, number | null | undefined][] = [
    [text.board, state.board_temperature_c],
    ["M.2", state.nvme_temperature_c],
    ["M.2 hotspot", state.nvme_hotspot_temperature_c],
    ["VRM MOS", state.vrm_mos_temperature_c],
  ];
  return <div style={{ background: tokens.colors.panel_alt, borderRadius: 6, marginBottom: 8, padding: "6px 10px 4px" }}>
    <div style={{ fontSize: 10, padding: "2px 0 5px" }}><b>{text.board}</b></div>
    {rows.map(([name, celsius]) => <div key={name} style={{ borderTop: `1px solid ${tokens.colors.border}`, display: "flex", fontSize: 10, justifyContent: "space-between", padding: "4px 0" }}><span style={{ color: tokens.colors.subtle }}>{name}</span><span style={{ color: celsius != null ? heatTone(celsius, accent.focus) : tokens.colors.subtle }}>{celsius != null ? `${celsius.toFixed(1)} °C` : "—"}</span></div>)}
  </div>;
}

function MonitorTab({ state, cpuRun }: { state: Status; cpuRun?: { target: number; elapsed: number } | null }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const [section, setSection] = useState<MonitorSection>("cpu");
  const gpuVramKnown = typeof state.gpu_vram_used_mib === "number" && typeof state.gpu_vram_total_mib === "number";
  const gpuGttKnown = typeof state.gpu_gtt_used_mib === "number" && typeof state.gpu_gtt_total_mib === "number";
  const fanOptions = state.fan_channel_options ?? [];
  const vrmAvailable = Boolean(state.vrm_available);
  const defaultFan = fanOptions.find((option) => option.channel === 2) ?? fanOptions[0];

  // Built once and reused by both each module's own tab and the "All" tab,
  // so the two views can never drift into showing different numbers for the
  // same sensor.
  const cpuVrmTiles = [
    { label: "VRM CPU · TEMP", value: vrmAvailable && state.vrm_cpu_temperature_c != null ? `${state.vrm_cpu_temperature_c.toFixed(1)} °C` : "—" },
    { label: `VRM CPU · ${text.gpuVoltage.toUpperCase()}`, value: state.vrm_cpu_voltage_v != null ? `${state.vrm_cpu_voltage_v.toFixed(2)} V` : "—" },
    { label: "VRM CPU · A", value: state.vrm_cpu_current_a != null ? `${state.vrm_cpu_current_a.toFixed(2)} A` : "—" },
    { label: "VRM CPU · W", value: state.vrm_cpu_power_w != null ? `${state.vrm_cpu_power_w.toFixed(1)} W` : "—" },
  ];
  const gpuVrmTiles = [
    { label: "VRM GPU · TEMP", value: vrmAvailable && state.vrm_gpu_temperature_c != null ? `${state.vrm_gpu_temperature_c.toFixed(1)} °C` : "—" },
    { label: `VRM GPU · ${text.gpuVoltage.toUpperCase()}`, value: state.vrm_gpu_voltage_v != null ? `${state.vrm_gpu_voltage_v.toFixed(2)} V` : "—" },
    { label: "VRM GPU · A", value: state.vrm_gpu_current_a != null ? `${state.vrm_gpu_current_a.toFixed(2)} A` : "—" },
    { label: "VRM GPU · W", value: state.vrm_gpu_power_w != null ? `${state.vrm_gpu_power_w.toFixed(1)} W` : "—" },
  ];
  // Board/M.2/VRM MOS: general system sensors, not fan controls. They live
  // only in the "All" tab now, alongside every other module's sensors, so a
  // single screenshot there covers the whole board instead of one per tab.
  const powerTiles = [
    { label: text.inputVoltage.toUpperCase(), value: state.vrm_input_voltage_v != null ? `${state.vrm_input_voltage_v.toFixed(2)} V` : "—" },
    { label: text.totalPower.toUpperCase(), value: state.vrm_total_power_w != null ? `${state.vrm_total_power_w.toFixed(1)} W` : "—" },
  ];

  return <>
    <SubNav<MonitorSection> value={section} onChange={setSection} items={[
      { key: "cpu", label: "CPU", icon: <LuCpu strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "gpu", label: "GPU", icon: <LuMicrochip strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "all", label: text.allSensors, icon: <LuLayoutGrid strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
    ]} />

    {section === "cpu" ? <Focusable flow-children="down">
      {cpuRunNotice(state, cpuRun)}
      <ScrollStop><CpuOverview state={state} /><CpuOcCard state={state} /></ScrollStop>
      <ScrollStop><CoreGrid cores={state.cpu_cores ?? []} slots={state.cpu_physical_slots} /></ScrollStop>
      <ScrollStop><RailVrm state={state} label="VRM CPU" tiles={cpuVrmTiles} /></ScrollStop>
      <ScrollStop end />
    </Focusable> : null}

    {section === "gpu" ? <Focusable flow-children="down">
      <ScrollStop><GpuOverview state={state} /><AceMeter state={state} /></ScrollStop>
      <ScrollStop><GpuDetails state={state} /></ScrollStop>
      <ScrollStop><RailVrm state={state} label="VRM GPU" tiles={gpuVrmTiles} /></ScrollStop>
      <Gddr6Panel state={state} />
      <ScrollStop end />
    </Focusable> : null}

    {section === "all" ? <section>
      {/* Every sensor from every module, stacked in one screen, purely so a
          player can take a single screenshot instead of one per tab. Each
          block is a ScrollStop so the D-pad can walk down to the last one. */}
      <Focusable flow-children="down">
        <ScrollStop><SectionTitle kind="cpu" title="CPU" /><CpuOverview state={state} /><CpuOcCard state={state} /></ScrollStop>
        <ScrollStop><CoreGrid cores={state.cpu_cores ?? []} slots={state.cpu_physical_slots} /></ScrollStop>
        <ScrollStop><RailVrm state={state} label="VRM CPU" tiles={cpuVrmTiles} /></ScrollStop>

        <ScrollStop><SectionTitle kind="gpu" title="GPU" /><GpuOverview state={state} /><AceMeter state={state} /></ScrollStop>
        <ScrollStop><GpuDetails state={state} /></ScrollStop>
        <ScrollStop><RailVrm state={state} label="VRM GPU" tiles={gpuVrmTiles} /></ScrollStop>
        <Gddr6Panel state={state} />

        <ScrollStop><SectionTitle kind="fan" title={text.fan} /><FanCard state={state} /></ScrollStop>
        <ScrollStop><BoardCard state={state} /></ScrollStop>

        <ScrollStop><SectionTitle kind="power" title={text.power} /><RailVrm state={state} label="VRM" tiles={powerTiles} /></ScrollStop>
        <ScrollStop end />
      </Focusable>
    </section> : null}
  </>;
}

function GpuMemoryLimit({ ttm, error, busy, execute, onState }: {
  ttm: TtmState | null; error: string | null; busy: boolean;
  execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void>;
  onState: (next: TtmState) => void;
}) {
  const pageSize = ttm?.page_size ?? 4096;
  const managedChoice = ttm?.managed ? String(ttmGib(ttm.managed_pages, pageSize) ?? "") : null;
  // "Kernel default" is only a choice when there is something of ours to take off.
  const restorable = Boolean(ttm?.managed || ttm?.legacy_pages != null);
  const choices = useMemo(
    () => [...(restorable ? ["default"] : []), ...(ttm?.presets_gib ?? []).map(String)],
    [restorable, ttm?.presets_gib],
  );
  // The choice is kept by value, not by position: "Kernel default" appears and
  // disappears from the front of the list as the limit is set and restored.
  const [selected, setSelected] = useState<string | null>(null);
  const choice = selected != null && choices.includes(selected)
    ? selected
    : managedChoice && choices.includes(managedChoice) ? managedChoice : choices[0] ?? null;
  const choiceIndex = choice == null ? 0 : choices.indexOf(choice);
  const choiceLabel = (value: string | null) => value == null ? "—" : value === "default" ? text.ttmKernelDefault : `${value} GiB`;
  // amdgpu.gttsize would make a new limit do nothing: only taking ours off is allowed.
  const blockedByGttsize = ttm?.gtt_override != null && choice !== "default";
  const unchanged = choice == null || blockedByGttsize
    || (choice === "default" ? !restorable : choice === managedChoice && ttm?.legacy_pages == null);
  const note = (body: string, key: string) => <div key={key} style={{ color: tokens.colors.amber, fontSize: 9, lineHeight: 1.4, margin: "0 2px 6px" }}>{body}</div>;
  const confirm = () => {
    if (choice == null) return;
    showModal(<ConfirmModal
      strTitle={text.ttmApply}
      strDescription={`${choiceLabel(choice)}. ${text.ttmApplyDescription} ${text.vramRebootRequired}`}
      strOKButtonText={text.ttmApply}
      onOK={() => {
        void execute(text.ttmTitle, async () => {
          const reply = await applyTtmLimit(choice);
          if (reply.ok !== false && reply.ttm) onState(reply.ttm);
          return reply;
        });
      }}
    />);
  };
  if (!ttm) return error ? note(error, "error") : <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 6px" }}>{text.ttmReading}</div>;
  const nextBoot = ttm.configured_pages != null
    ? `${formatBytes(ttm.configured_pages * pageSize)}${ttm.managed ? "" : ` · ${text.ttmSetElsewhereShort}`}`
    : text.ttmKernelDefault;
  const notes: ReactNode[] = [];
  if (!ttm.supported) {
    notes.push(note(ttm.reason || text.ttmUnavailable, "reason"));
    const manual = Object.entries(ttm.manual_arguments ?? {});
    if (manual.length && ttm.backend === "unsupported" && !/steamos/i.test(ttm.reason)) {
      notes.push(<div key="manual" style={{ color: tokens.colors.subtle, fontFamily: "monospace", fontSize: 9, lineHeight: 1.5, margin: "0 2px 6px" }}>
        {manual.map(([gib, argument]) => <div key={gib}>{gib} GiB · {argument}</div>)}
      </div>);
    }
  }
  if (ttm.gtt_override != null) notes.push(note(text.ttmGttOverride.replace("{value}", String(ttm.gtt_override)), "override"));
  if (ttm.external) notes.push(note(text.ttmSetElsewhere, "external"));
  if (ttm.legacy_pages != null) notes.push(note(text.ttmLegacy, "legacy"));
  if (ttm.next_boot_ram_bytes != null) notes.push(note(text.ttmVramPending.replace("{size}", formatBytes(ttm.next_boot_ram_bytes)), "vram"));
  // Somebody else's limit is reported, never replaced; amdgpu.gttsize would make a new one do nothing.
  const canChoose = ttm.supported && choices.length > 0 && !(ttm.external && !ttm.managed);
  return <>
    <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.4, margin: "0 2px 6px" }}>{text.ttmHelp}</div>
    <StatusRow label={text.ttmNow} active={null} value={formatBytes(ttm.gtt_total_bytes)} />
    <StatusRow label={text.ttmNextBoot} active={null} value={nextBoot} />
    {ttm.reboot_required ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.vramPending}</span><b style={{ color: tokens.colors.amber }}>{text.vramRebootRequired}</b></div> : null}
    {notes}
    {canChoose ? <>
      <CompactSlider label={text.ttmTitle} value={choiceIndex} suffix="" min={0} max={choices.length - 1} step={1} disabled={busy || choices.length < 2}
        onChange={(at) => setSelected(choices[at] ?? null)} formatValue={() => choiceLabel(choice)} />
      <div style={{ marginTop: 6, marginBottom: 10 }}>
        <ActionRow><Action label={text.ttmApply} primary disabled={busy || unchanged} onActivate={confirm} /></ActionRow>
      </div>
    </> : null}
  </>;
}

function MemoryTab({ state, busy, execute }: { state: Status; busy: boolean; execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void> }) {
  const vram = state.vram;
  // Read when the tab opens and after every change: it can ask rpm-ostree,
  // so it is not part of the regular status poll.
  const [ttm, setTtm] = useState<TtmState | null>(null);
  const [ttmError, setTtmError] = useState<string | null>(null);
  const loadTtm = useCallback(async () => {
    try {
      const reply = await getTtmState();
      if (reply.ok === false || !reply.ttm) { setTtmError(localizedErrorSummary(reply.error ?? text.error)); return; }
      setTtmError(null); setTtm(reply.ttm);
    } catch (error) { setTtmError(localizedErrorSummary(failed(error).error ?? text.error)); }
  }, []);
  // Once on mount, and again when the VRAM size changes: a new size changes how
  // much memory the next boot has left for the limit. One read, not two.
  const vramSizeKey = vram?.uma_size_mb ?? null;
  useEffect(() => { void loadTtm(); }, [loadTtm, vramSizeKey]);
  const vramPresets = state.contract?.vram?.presets?.length ? state.contract.vram.presets : VRAM_PRESETS_FALLBACK;
  const vramSupported = Boolean(vram?.supported);
  // An index into vramPresets, not the megabyte value itself: this drives a
  // SliderField, the same discrete-step control CPU/fan already use in this
  // panel. A native Dropdown was tried first and dropped -- opening its
  // context menu inside the Quick Access Menu unmounted this whole panel, so
  // picking a size silently threw the player back to the Board/GPU tab.
  const [vramIndex, setVramIndex] = useState(0);
  const vramInitialized = useRef(false);
  useEffect(() => {
    if (vramInitialized.current || vram?.uma_size_mb == null) return;
    const matched = vramPresets.indexOf(vram.uma_size_mb);
    if (matched >= 0) setVramIndex(matched);
    vramInitialized.current = true;
    // vramPresets only changes shape once, right after the first status()
    // reply -- excluding it keeps this effect from re-snapping the slider
    // back onto the current size while the player is still dragging it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vram?.uma_size_mb]);
  const vramTarget = vramPresets[Math.min(vramIndex, vramPresets.length - 1)] ?? vramPresets[0];
  const vramUnchanged = vram?.uma_size_mb != null && vramTarget === vram.uma_size_mb;
  // Persisted, not a plain ref: a ref is lost the instant the player leaves
  // this tab (it remounts every time), which is exactly what made the
  // pending-reboot notice disappear right after a successful apply. This
  // record is written the moment the player confirms and cleared once
  // vram.boot_id shows a real reboot happened -- see loadVramPending().
  const [vramPending, setVramPending] = useState<VramPendingRecord | null>(() => loadVramPending());
  useEffect(() => {
    if (!vramPending || !vram?.boot_id) return;
    if (vramPending.bootId !== vram.boot_id) { saveVramPending(null); setVramPending(null); }
  }, [vramPending, vram?.boot_id]);
  // The helper compares CMOS with what the firmware booted with, so a size
  // written from the desktop shows up here too; the local record covers an
  // older helper that does not report it.
  const helperPending = Boolean(vram?.reboot_pending);
  const vramRebootPending = helperPending || Boolean(
    vramPending && vram?.boot_id === vramPending.bootId && vram?.uma_size_mb === vramPending.mb,
  );
  const pendingSize = helperPending && vram?.uma_size_mb != null ? vram.uma_size_mb : vramPending?.mb ?? vramTarget;
  // A limit already set for the next boot that this VRAM size would no longer leave room for.
  const ttmBytes = ttm?.configured_pages != null ? ttm.configured_pages * (ttm.page_size ?? 4096) : null;
  const activeVramBytes = vram?.active_mb != null ? vram.active_mb * 1024 * 1024 : null;
  const ramAfterVram = ttm?.physical_ram_bytes != null && activeVramBytes != null
    ? ttm.physical_ram_bytes + activeVramBytes - vramTarget * 1024 * 1024 : null;
  const vramTtmConflict = ttmBytes != null && ramAfterVram != null && ttmBytes > ramAfterVram;
  const confirmVram = () => showModal(<ConfirmModal
    strTitle={text.vramApply}
    strDescription={`${vramSizeLabel(vramTarget)}. ${text.vramApplyDescription} ${text.vramRebootRequired}${vramTtmConflict ? ` ${text.vramTtmConflict.replace("{limit}", formatBytes(ttmBytes)).replace("{size}", formatBytes(ramAfterVram))}` : ""}`}
    strOKButtonText={text.vramApply}
    onOK={() => {
      if (vram?.boot_id) { const record = { mb: vramTarget, bootId: vram.boot_id }; saveVramPending(record); setVramPending(record); }
      void execute("BC250 VRAM", () => applyVramSize(vramTarget));
    }}
  />);
  const ramTotal = state.memory_ram_total_bytes ?? null;
  const ramAvailable = state.memory_ram_available_bytes ?? null;
  const ramUsed = ramTotal != null && ramAvailable != null ? Math.max(0, ramTotal - ramAvailable) : null;
  const swapTotal = state.memory_swap_total_bytes ?? null;
  const swapFree = state.memory_swap_free_bytes ?? null;
  const swapUsed = swapTotal != null && swapFree != null ? Math.max(0, swapTotal - swapFree) : null;
  const swapActive = swapTotal != null && swapTotal > 0;
  const storageUsed = state.storage_used_bytes ?? null;
  const storageTotal = state.storage_total_bytes ?? null;
  const gpuVramKnown = typeof state.gpu_vram_used_mib === "number" && typeof state.gpu_vram_total_mib === "number";
  const gpuGttKnown = typeof state.gpu_gtt_used_mib === "number" && typeof state.gpu_gtt_total_mib === "number";
  return <>
    <section style={{ marginBottom: 12 }}><SectionTitle kind="memory" title={text.memory} />
      <UsageBar label="RAM" used={ramUsed} total={ramTotal} color={tokens.colors.green} />
      {/* A swap TOTAL of 0 is a real, common state (no swap configured at
          all) -- distinct from swapActive/swapUsed being unavailable because
          the sensor read failed, which is what "—" already communicates via
          UsageBar when used/total are null. */}
      <UsageBar label="SWAP" used={swapActive ? swapUsed : 0} total={swapActive ? swapTotal : 0} color={tokens.colors.amber} />
      <UsageBar label={text.storage.toUpperCase()} used={storageUsed} total={storageTotal} color={tokens.colors.blue} />
    </section>
    <section style={{ marginBottom: 12 }}><SectionTitle kind="memory" title={text.vramPartition} />
      {!vramSupported
        ? <div style={{ color: tokens.colors.amber, fontSize: 10, lineHeight: 1.4, margin: "0 2px 6px" }}>{vram?.reason || text.vramUnavailable}</div>
        : <>
          <StatusRow label={text.vramCurrentSize} active={null} value={vram?.active_mb != null ? vramSizeLabel(vram.active_mb) : vram?.uma_size_mb != null ? vramSizeLabel(vram.uma_size_mb) : "—"} />
          {vramRebootPending ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.vramPending}</span><b style={{ color: tokens.colors.amber }}>{vramSizeLabel(pendingSize)} · {text.vramRebootRequired}</b></div> : null}
          <CompactSlider label={text.vramPartition} value={vramIndex} suffix="" min={0} max={vramPresets.length - 1} step={1} disabled={busy}
            onChange={setVramIndex} formatValue={() => vramSizeLabel(vramTarget)} />
          <div style={{ marginTop: 6, marginBottom: 10 }}>
            <ActionRow><Action label={text.vramApply} primary disabled={busy || vramUnchanged} onActivate={confirmVram} /></ActionRow>
          </div>
          <MetricGrid tiles={[
            { label: "VRAM", value: gpuVramKnown ? `${formatBytes((state.gpu_vram_used_mib ?? 0) * 1024 * 1024)} / ${formatBytes((state.gpu_vram_total_mib ?? 0) * 1024 * 1024)}` : "—" },
            { label: "GTT", value: gpuGttKnown ? `${formatBytes((state.gpu_gtt_used_mib ?? 0) * 1024 * 1024)} / ${formatBytes((state.gpu_gtt_total_mib ?? 0) * 1024 * 1024)}` : "—" },
            { label: "MCLK", value: state.gpu_memory_clock_mhz != null ? `${state.gpu_memory_clock_mhz} MHz` : "—" },
            { label: text.ttmLimit.toUpperCase(), value: state.memory_ttm_limit_bytes != null ? formatBytes(state.memory_ttm_limit_bytes) : "—" },
          ]} />
        </>}
    </section>
    <section style={{ marginBottom: 12 }}><SectionTitle kind="memory" title={text.ttmTitle} />
      <GpuMemoryLimit ttm={ttm} error={ttmError} busy={busy} execute={execute} onState={(next) => { setTtm(next); setTtmError(null); }} />
    </section>
  </>;
}

type PanelTab = "board" | "monitor" | "memory" | "settings";
type BoardSection = "gpu" | "cu" | "cpu" | "fan";

// Decky unmounts this panel every time Quick Access closes -- a confirmation
// modal is enough -- so which tab and board section the player was on lives
// here, outside React, and survives the remount.
let rememberedTab: PanelTab = "board";
let rememberedSection: BoardSection = "gpu";

function Content() {
  const [state, setState] = useState<Status>({});
  const [settings, setSettingsState] = useState<QuickAccessSettings>(() => loadSettings());
  const setSettings = useCallback((next: QuickAccessSettings) => { setSettingsState(next); saveSettings(next); }, []);
  const accent = ACCENT_SWATCHES[settings.accent];
  const [activeTab, setActiveTabState] = useState<PanelTab>(() => rememberedTab);
  const setActiveTab = useCallback((tab: PanelTab) => { rememberedTab = tab; setActiveTabState(tab); }, []);
  const topRef = useRef<HTMLDivElement>(null);
  const [boardSection, setBoardSectionState] = useState<BoardSection>(() => rememberedSection);
  const setBoardSection = useCallback((section: BoardSection) => { rememberedSection = section; setBoardSectionState(section); }, []);
  const [loaded, setLoaded] = useState(false);
  const [busyLocal, setBusy] = useState(false);
  // An operation this mounted panel did not start (it began before a
  // remount) still blocks every control until the backend reports it done.
  const busy = busyLocal || Boolean(state.operation_in_progress);
  const [stale, setStale] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [highOpen, setHighOpen] = useState(true);
  const [highSelection, setHighSelection] = useState(0);
  const [cuDraft, setCuDraft] = useState<number[]>(masksFromTarget(24));
  const [cuConflict, setCuConflict] = useState(false);
  const [fanOpen, setFanOpen] = useState(false);
  const [fanChannel, setFanChannel] = useState(2);
  const [fanDuty, setFanDuty] = useState(50);
  const [cpuFrequency, setCpuFrequency] = useState(3100);
  const [cpuVid, setCpuVid] = useState(1150);
  const [cpuScale, setCpuScale] = useState(-30);
  const [cpuManual, setCpuManual] = useState(false);
  const [cpuError, setCpuError] = useState<string | null>(null);
  const [cpuOperation, setCpuOperation] = useState<{ target: number; manual: boolean; startedAt: number } | null>(null);
  // A CPU run started before a remount: show its progress again.
  const running = state.operation_in_progress;
  useEffect(() => {
    if (busyRef.current) return;
    if (running && (running.action === "cpu-detect" || running.action === "cpu-scale")) {
      setCpuOperation((current) => current ?? { target: Number(running.arguments?.[0]) || 0, manual: running.action === "cpu-scale", startedAt: running.started_at });
    } else { setCpuOperation(null); }
  }, [running?.action, running?.started_at]);
  const [cpuElapsed, setCpuElapsed] = useState(0);
  const busyRef = useRef(false); const refreshing = useRef(false);
  const cpuTelemetryRefreshing = useRef(false);
  const monitorSensorsRefreshing = useRef(false);
  const gddr6Refreshing = useRef(false);
  const dirty = useRef({ cu: false, fan: false, gpu: false, cpu: false });
  const selectionRef = useRef({ fan: 2 });
  useEffect(() => { selectionRef.current.fan = fanChannel; }, [fanChannel]);

  const refresh = useCallback(async (reason: "initial" | "poll" | "after" = "initial") => {
    if (refreshing.current || (reason === "poll" && busyRef.current)) return;
    refreshing.current = true;
    try {
      const result = await getStatus();
      if (result.ok === false) { setLoaded(true); setStale(true); if (reason === "initial") setFeedback(result.error ?? text.error); return; }
      // A merge, not a replace: status() no longer carries cpu_cores,
      // cpu_usage_percent or vrm_* (moved to monitor_snapshot() so a long
      // operation can't freeze them — see sampleMonitorSensors). Replacing
      // the whole state object here wiped those fields out again every 5 s,
      // which is exactly what made the CPU core grid blink in and out.
      // gpu_busy_percent is the one passive sensor both calls report: status() has
      // only the kernel's counter (absent on most kernels) while monitor_snapshot()
      // fills it in from the clients' engine time, so a null here must not wipe it.
      setState((current) => ({ ...current, ...result, gpu_busy_percent: result.gpu_busy_percent ?? current.gpu_busy_percent })); setLoaded(true); setStale(false);
      if (validMasks(result.cu_masks)) setCuDraft((existing) => { if (dirty.current.cu && reason !== "after") { if (!sameMasks(existing, result.cu_masks!)) setCuConflict(true); return existing; } dirty.current.cu = false; setCuConflict(false); return result.cu_masks!.slice(); });
      const points = result.gpu_safe_point_ceilings ?? [];
      if (!dirty.current.gpu || reason === "after") {
        // A high point is orange only after Cyan has verified it as the live
        // range. Do not preselect the first TOML point while Benchmark (or
        // another <=2000 MHz profile) is active: that made a controller focus
        // ring look like a second selected frequency.
        const liveHigh = result.gpu_range?.[0] === 1000 && (result.gpu_range?.[1] ?? 0) > 2000
          ? result.gpu_range![1]
          : 0;
        setHighSelection(points.some((point) => point.frequency === liveHigh) ? liveHigh : 0);
        dirty.current.gpu = false;
      }
      // Bounds from the payload, never from a copy kept here. Clamping a
      // saved profile against the wrong floor is not a display problem: the
      // clamped value is what the panel then re-applies, so a Desktop profile
      // saved at 3200 MHz used to come back as an unrequested 3500.
      const cpuLimits = result.contract?.cpu;
      const lowFreq = cpuLimits?.frequency_range?.[0] ?? 3100;
      const highFreq = cpuLimits?.frequency_range?.[1] ?? 4200;
      const freqStep = cpuLimits?.frequency_step ?? 50;
      const lowVid = cpuLimits?.vid_range?.[0] ?? 950;
      const highVid = cpuLimits?.vid_range?.[1] ?? 1325;
      const lowScale = cpuLimits?.scale_range?.[0] ?? -50;
      const highScale = cpuLimits?.scale_range?.[1] ?? 0;
      const lowFan = result.contract?.fan?.percent_range?.[0] ?? 20;
      const highFan = result.contract?.fan?.percent_range?.[1] ?? 100;
      const fan = result.fan_channel_options?.find((option) => option.channel === selectionRef.current.fan); const duty = fan?.percent;
      if (duty != null && (!dirty.current.fan || reason === "after")) { setFanDuty(Math.max(lowFan, Math.min(highFan, duty))); dirty.current.fan = false; }
      if (!dirty.current.cpu && result.cpu_detected_profile?.ready) {
        const active = result.cpu_active_profile ?? result.cpu_detected_profile.active_profile;
        const selectedFrequency = active?.mode === "manual" ? active.frequency : result.cpu_detected_profile.requested_frequency;
        setCpuFrequency(Math.max(lowFreq, Math.min(highFreq, selectedFrequency)));
        setCpuVid(Math.max(lowVid, Math.min(highVid, result.cpu_detected_profile.requested_vid)));
        setCpuScale(Math.max(lowScale, Math.min(highScale, active?.scale ?? result.cpu_detected_profile.scale)));
        setCpuManual(active?.mode === "manual");
      } else if (!dirty.current.cpu && result.cpu_saved_profile) {
        setCpuFrequency(Math.max(lowFreq, Math.min(highFreq, Math.round(result.cpu_saved_profile.frequency / freqStep) * freqStep)));
        setCpuScale(Math.max(lowScale, Math.min(highScale, result.cpu_saved_profile.scale)));
      }
    } catch (error) { if (reason === "initial") setLoaded(true); setStale(true); if (reason === "initial") setFeedback(failed(error).error ?? text.error); }
    finally { refreshing.current = false; }
  }, []);
  useEffect(() => { void refresh("initial"); const timer = globalThis.setInterval(() => void refresh("poll"), 5000); return () => globalThis.clearInterval(timer); }, [refresh]);

  const sampleCpuTelemetry = useCallback(async () => {
    if (cpuTelemetryRefreshing.current) return;
    cpuTelemetryRefreshing.current = true;
    try {
      const result = await getCpuTelemetry();
      if (result.ok !== false) setState((current) => ({
        ...current,
        ...(typeof result.cpu_frequency_mhz === "number" ? { cpu_frequency_mhz: result.cpu_frequency_mhz } : {}),
        ...(typeof result.cpu_temperature_c === "number" ? { cpu_temperature_c: result.cpu_temperature_c } : {}),
        ...(typeof result.cpu_tuning_ready === "boolean" ? { cpu_tuning_ready: result.cpu_tuning_ready } : {}),
        ...(typeof result.cpu_tuning_temperature === "number" ? { cpu_tuning_temperature: result.cpu_tuning_temperature } : {}),
        ...(typeof result.observed_at === "number" ? { observed_at: result.observed_at } : {}),
      }));
    } catch {
      // A missed read-only sample is passive: the next sample retries and an
      // explicit OC result remains the authoritative success/failure signal.
    } finally { cpuTelemetryRefreshing.current = false; }
  }, []);

  useEffect(() => {
    if (!cpuOperation) setCpuElapsed(0);
    const tick = () => {
      if (cpuOperation) setCpuElapsed(Math.max(0, Math.floor((Date.now() - cpuOperation.startedAt) / 1000)));
    };
    void sampleCpuTelemetry();
    if (cpuOperation) tick();
    const telemetryTimer = globalThis.setInterval(() => void sampleCpuTelemetry(), cpuOperation ? 1000 : 3000);
    const elapsedTimer = cpuOperation ? globalThis.setInterval(tick, 1000) : undefined;
    return () => { globalThis.clearInterval(telemetryTimer); if (elapsedTimer !== undefined) globalThis.clearInterval(elapsedTimer); };
  }, [cpuOperation, sampleCpuTelemetry]);

  const sampleMonitorSensors = useCallback(async () => {
    if (monitorSensorsRefreshing.current) return;
    monitorSensorsRefreshing.current = true;
    try {
      const { ok: _ok, protocol: _protocol, error: _error, ...fields } = await getMonitorSnapshot();
      setState((current) => ({ ...current, ...fields }));
    } catch {
      // Same trade-off as sampleCpuTelemetry: a missed passive sample just
      // retries in 5 s, so it fails silently rather than surfacing a toast.
    } finally { monitorSensorsRefreshing.current = false; }
  }, []);

  // Independent of busy/cpuOperation on purpose: this is what keeps
  // Monitorización and Memoria y Video alive while a long board operation
  // (e.g. a ~920 s cpu-detect) holds status()'s own helper lock. Without
  // this, both tabs simply froze on stale "—" values for that whole time.
  useEffect(() => {
    void sampleMonitorSensors();
    const timer = globalThis.setInterval(() => void sampleMonitorSensors(), settings.refreshIntervalMs);
    return () => globalThis.clearInterval(timer);
  }, [sampleMonitorSensors, settings.refreshIntervalMs]);

  const [gddr6Now, setGddr6Now] = useState(() => Date.now());
  const gddr6Live = gddr6Now < gddr6LiveUntil;
  // A CPU run holds the SMU: the session waits instead of queuing behind it.
  const gddr6Paused = Boolean(cpuOperation) || Boolean(state.operation_in_progress && String(state.operation_in_progress.action).startsWith("cpu-"));
  const setGddr6Live = useCallback((on: boolean) => { gddr6LiveUntil = on ? Date.now() + GDDR6_SESSION_MS : 0; setGddr6Now(Date.now()); }, []);
  useEffect(() => {
    if (!gddr6Live) return;
    const timer = globalThis.setInterval(() => setGddr6Now(Date.now()), 15000);
    return () => globalThis.clearInterval(timer);
  }, [gddr6Live]);
  const gddr6Session = useMemo<Gddr6Session>(() => ({ live: gddr6Live, minutesLeft: Math.max(1, Math.ceil((gddr6LiveUntil - gddr6Now) / 60000)), setLive: setGddr6Live, merge: (fields: Partial<Status>) => setState((current) => ({ ...current, ...fields })) }), [gddr6Live, gddr6Now, setGddr6Live]);
  const sampleGddr6 = useCallback(async () => {
    if (gddr6Refreshing.current) return;
    gddr6Refreshing.current = true;
    try {
      const { ok: _ok, protocol: _protocol, error: _error, ...fields } = await getGddr6Sensors();
      setState((current) => ({ ...current, ...fields }));
    } catch {
      // Same trade-off as sampleMonitorSensors: a missed passive sample just
      // retries on the next tick.
    } finally { gddr6Refreshing.current = false; }
  }, []);

  // Its own, slower cadence: unlike qam-sensors this walks /home looking for
  // the desktop's reviewed checkout and shells out to a second reader binary,
  // so it costs more than the other passive reads for a value that changes
  // far more slowly than clocks or usage.
  useEffect(() => {
    if (!gddr6Live || gddr6Paused) return;
    void sampleGddr6();
    const timer = globalThis.setInterval(() => void sampleGddr6(), settings.refreshIntervalMs * 2);
    return () => globalThis.clearInterval(timer);
  }, [sampleGddr6, settings.refreshIntervalMs, gddr6Live, gddr6Paused]);
  // Turning GDDR6 on applies this boot's SMU patch when it is missing,
  // quietly and once per session; a refusal shows in the panel.
  const gddr6PatchTried = useRef(false);
  useEffect(() => { if (!gddr6Live) gddr6PatchTried.current = false; }, [gddr6Live]);
  useEffect(() => {
    if (!gddr6Live || gddr6Paused || gddr6PatchTried.current) return;
    if (state.gddr6_reason !== "GDDR6_PATCH_INACTIVE" || state.gddr6_firmware_supported === false) return;
    gddr6PatchTried.current = true;
    void (async () => {
      try {
        const result = await applyGddr6Patch();
        if (result.ok === false) setState((current) => ({ ...current, gddr6_patch_error: result.error ?? text.error }));
        else { const { ok: _ok, protocol: _protocol, error: _error, ...fields } = result; setState((current) => ({ ...current, ...fields, gddr6_patch_error: null })); }
      } catch (error) { setState((current) => ({ ...current, gddr6_patch_error: failed(error).error ?? text.error })); }
    })();
  }, [gddr6Live, gddr6Paused, state.gddr6_reason, state.gddr6_firmware_supported]);

  const execute = async (title: string, operation: () => Promise<Result>, kind: DraftKind = "none", cpuProgress?: { target: number; manual: boolean }) => {
    if (busyRef.current) return; busyRef.current = true; setBusy(true);
    if (kind === "cpu") setCpuError(null);
    if (cpuProgress) setCpuOperation({ ...cpuProgress, startedAt: Date.now() });
    try { const result = await operation(); if (result.ok === false) { const message = result.error ?? text.error; if (kind === "cpu") setCpuError(message); setFeedback(message); toaster.toast({ title, body: localizedErrorSummary(message) }); } else { setState((current) => ({ ...current, ...result })); const rangeWrite = kind === "gpu" && Array.isArray(result.gpu_range); if (rangeWrite) setHighSelection(result.gpu_range![0] === 1000 && result.gpu_range![1] > 2000 ? result.gpu_range![1] : 0); setFeedback(null); if (kind !== "none") dirty.current[kind] = false; toaster.toast({ title, body: text.success }); if (!rangeWrite) await refresh("after"); } }
    catch (error) { const result = failed(error); const message = result.error ?? text.error; if (kind === "cpu") setCpuError(message); setFeedback(message); toaster.toast({ title, body: localizedErrorSummary(message) }); }
    finally { void sampleCpuTelemetry(); busyRef.current = false; setBusy(false); setCpuOperation(null); }
  };

  const topology = validMasks(state.cu_masks); const liveMasks = useMemo(() => topology ? state.cu_masks!.slice() : [0,0,0,0], [topology, state.cu_masks]); const driverMasks = useMemo(() => validMasks(state.cu_driver_masks) ? state.cu_driver_masks!.slice() : [0,0,0,0], [state.cu_driver_masks]);
  const draftCUs = countWgps(cuDraft) * 2;
  const detectedFans = state.fan_channel_options?.filter((option) => option.available).map((option) => option.channel) ?? state.system_fan_channels ?? []; const fanDetected = detectedFans.includes(fanChannel); const liveFan = state.fan_channel_options?.find((option) => option.channel === fanChannel);
  const points = state.gpu_safe_point_ceilings ?? [];
  const liveHighPoint = points.find((point) => point.frequency === highSelection);
  const gpuReady = Boolean(state.gpu_governor_active ?? state.cyan_active);
  const governorName = state.gpu_governor === "oberon" ? "Oberon" : state.gpu_governor === "cyan" ? "Cyan" : "";
  const activeGpuProfiles = state.gpu_profiles ?? [];
  const cpuReady = Boolean(state.cpu_tuning_ready);
  const cpuLimit = state.cpu_tuning_temperature ?? 90;
  const detectedCpu = state.cpu_detected_profile;
  const activeCpu = state.cpu_active_profile ?? detectedCpu?.active_profile;
  const manualReady = Boolean(detectedCpu?.ready && detectedCpu.same_boot && (state.cpu_manual_scale_ready ?? detectedCpu.manual_scale_ready));
  const manualFrequencyReady = Boolean(manualReady && detectedCpu?.frequency === cpuFrequency);
  // While the player is dragging the manual scale slider, this banner should
  // track what they are about to apply, not the last automatic detection —
  // otherwise "detected configuration" kept showing a stale scale the panel
  // was no longer staging.
  const detectedCpuSummary = cpuManual
    ? `${cpuFrequency} MHz · scale ${cpuScale}`
    : detectedCpu
      ? detectedCpu.requested_frequency === detectedCpu.frequency
        ? `${detectedCpu.frequency} MHz · scale ${detectedCpu.scale}`
        : `${text.cpuTarget} ${detectedCpu.requested_frequency} → ${detectedCpu.frequency} MHz · scale ${detectedCpu.scale}`
      : "";
  const manualScaleDescription = !manualReady
    ? text.runAutomaticFirst
    : manualFrequencyReady
      ? text.cpuManualHelp
      : `${text.cpuManualHelp} · ${detectedCpu?.frequency ?? "—"} MHz`;
  // Every bound the controls below use comes from the helper with the state.
  // The panel used to declare its own, and its CPU floor was 3500 against a
  // real 3100 — so 3100-3450 MHz was unreachable in Game Mode, and a profile
  // saved at 3200 on the Desktop was rounded up before being re-applied.
  const limits = state.contract;
  const cpuBounds = limits?.cpu;
  const cpuMin = cpuBounds?.frequency_range?.[0] ?? 3100;
  const cpuMax = cpuBounds?.frequency_range?.[1] ?? 4200;
  const cpuStep = cpuBounds?.frequency_step ?? 50;
  const vidMin = cpuBounds?.vid_range?.[0] ?? 950;
  const vidMax = cpuBounds?.vid_range?.[1] ?? 1325;
  const vidStep = cpuBounds?.vid_step ?? 5;
  const scaleMin = cpuBounds?.scale_range?.[0] ?? -50;
  const scaleMax = cpuBounds?.scale_range?.[1] ?? 0;
  const fanMin = limits?.fan?.percent_range?.[0] ?? 20;
  const fanMax = limits?.fan?.percent_range?.[1] ?? 100;
  const fanStep = limits?.fan?.percent_step ?? 5;
  const selectedEstimatedVid = estimateCpuVid(cpuFrequency, cpuScale, cpuBounds?.vid_model);
  const activeMatchesTarget = cpuManual
    ? Boolean(activeCpu?.persistable && activeCpu.mode === "manual" && activeCpu.frequency === cpuFrequency && activeCpu.scale === cpuScale)
    : Boolean(activeCpu?.persistable && activeCpu.mode === "automatic" && detectedCpu?.requested_frequency === cpuFrequency && detectedCpu.requested_vid === cpuVid);
  const confirmCpu = (mode: "detect" | "install") => showModal(<ConfirmModal
    strTitle={mode === "detect" ? (cpuManual ? text.cpuApplyManual : text.cpuApplyAuto) : text.install}
    strDescription={mode === "detect"
      ? cpuManual
        ? `${cpuFrequency} MHz · ${text.cpuScale} ${cpuScale} · VID ${text.estimated} ${selectedEstimatedVid} mV · ${cpuLimit}°C. ${text.manualApplyWarning}`
        : `${cpuFrequency} MHz · ${text.cpuVoltage} ${cpuVid} mV · ${cpuLimit}°C. ${text.automaticApplyWarning}`
      : `${activeCpu?.frequency ?? "—"} MHz · ${text.cpuScale} ${activeCpu?.scale ?? "—"} · ${activeCpu?.estimated_vid ?? "—"} mV ${text.estimated} · ${activeCpu?.temperature ?? cpuLimit}°C. ${text.installExactProfile}`}
    strOKButtonText={mode === "detect" ? (cpuManual ? text.cpuApplyManual : text.cpuApplyAuto) : text.install}
    onOK={() => {
      // The player stays where they are: this tab shows the run's progress itself.
      void execute("BC250 CPU", mode === "detect" ? (cpuManual ? () => applyCpuScale(cpuFrequency, cpuScale) : () => applyCpuTuning(cpuFrequency, cpuVid)) : installCpuService, "cpu", mode === "detect" ? { target: cpuFrequency, manual: cpuManual } : undefined);
    }}
  />);

  return <Focusable flow-children="down" style={{ background: tokens.colors.panel, border: `1px solid ${tokens.colors.border}`, borderRadius: 12, boxSizing: "border-box", color: tokens.colors.text, minHeight: "100vh", padding: "12px 14px 72px", width: "100%" }}>
  <SettingsContext.Provider value={{ settings, setSettings, gddr6: gddr6Session }}>
    <div ref={topRef} />
    {stale ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "6px 9px" }}><FaClock />{text.stale}</div> : null}
    {feedback ? <Notice value={feedback} dismiss={() => setFeedback(null)} /> : null}

    <Focusable flow-children="row" style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, display: "grid", gap: 4, gridTemplateColumns: "repeat(4,minmax(0,1fr))", marginBottom: 12, padding: 4 }}>
      {([
        ["board", text.boardSetup, <LuSlidersHorizontal strokeWidth={NAV_STROKE} />],
        ["monitor", text.monitoring, <LuActivity strokeWidth={NAV_STROKE} />],
        ["memory", text.memoryAndVideo, <LuMemoryStick strokeWidth={NAV_STROKE} />],
        ["settings", text.settingsTab, <LuSettings strokeWidth={NAV_STROKE} />],
      ] as [PanelTab, string, ReactNode][]).map(([tab, label, tabIcon]) => {
        const active = activeTab === tab;
        return <PadButton key={tab} label={label} onActivate={() => setActiveTab(tab)} style={{ alignItems: "center", background: active ? accent.focus_soft : "transparent", border: active ? `1px solid ${accent.focus}` : "1px solid transparent", color: active ? accent.focus : tokens.colors.subtle, display: "flex", fontSize: 18, height: 38, justifyContent: "center", padding: 0, width: "100%" }}>
          {tabIcon}
        </PadButton>;
      })}
    </Focusable>

    {activeTab === "monitor" ? <MonitorTab state={state} cpuRun={cpuOperation ? { target: cpuOperation.target, elapsed: cpuElapsed } : null} /> : null}
    {activeTab === "memory" ? <MemoryTab state={state} busy={busy} execute={execute} /> : null}
    {activeTab === "settings" ? <SettingsTab settings={settings} setSettings={setSettings} state={state} busy={busy} execute={execute} /> : null}
    {activeTab === "board" ? <>
    <GameProfileCard state={state} busy={busy} />
    <SubNav<BoardSection> value={boardSection} onChange={setBoardSection} items={[
      { key: "gpu", label: "GPU", icon: <LuMicrochip strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "cpu", label: "CPU", icon: <LuCpu strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "cu", label: text.compute, icon: <LuGrid3X3 strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "fan", label: text.fan, icon: <LuFan strokeWidth={NAV_STROKE} />, color: accent.focus, colorSoft: accent.focus_soft },
    ]} />

    {busy && boardSection !== "cpu" ? <div style={{ alignItems: "center", background: accent.focus_soft, border: `1px solid ${accent.focus}`, borderRadius: 7, color: accent.focus, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "7px 9px" }}><FaClock />{text.operationInProgress}</div> : null}

    {boardSection === "gpu" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="gpu" title="GPU" trailing={governorName ? <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{governorName}</span> : undefined} />
    {!loaded ? <div style={{ color: tokens.colors.subtle, fontSize: 10, marginBottom: 6 }}>{text.loadingGpu}</div> : <>
    {gpuReady && state.gpu_dbus_responsive === false ? <div style={{ color: tokens.colors.amber, fontSize: 9, marginBottom: 6 }}>{text.governorUnresponsive}</div> : null}
    {!gpuReady ? <div style={{ color: state.gpu_governor === "conflict" ? tokens.colors.red : tokens.colors.amber, fontSize: 9, marginBottom: 6 }}>{state.gpu_governor === "conflict" ? text.governorConflict : state.gpu_service_installed ? text.governorStopped : text.governorMissing}</div> : null}
    <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: `repeat(${activeGpuProfiles.length || 1},minmax(0,1fr))`, marginBottom: 6 }}>
      {activeGpuProfiles.map((profile) => {
        const current = state.gpu_range?.[0] === profile.min && state.gpu_range?.[1] === profile.max && (state.gpu_governor !== "cyan" || state.gpu_performance_enabled === false);
        const allowed = Boolean(state.gpu_allowed_range && state.gpu_allowed_range[0] <= profile.min && profile.max <= state.gpu_allowed_range[1]);
        return <ProfileCard key={profile.key} title={gpuProfileName(profile)} detail={`${ghz(profile.min)}–${ghz(profile.max)} GHz`}
          current={current} disabled={busy || !gpuReady || !allowed}
          preferredFocus={profile.key === (state.gpu_governor === "oberon" ? "oberon-1850" : "balanced")}
          onActivate={() => { void execute(`GPU · ${profile.name}`, () => applyGpuProfile(profile.key), "gpu"); }} />;
      })}
    </Focusable>
    {points.length || state.gpu_governor === "cyan" ? <>
      <DisclosureRow label={text.more} value={points.length ? text.enabled : text.disabled} open={highOpen} disabled={busy || !gpuReady} onActivate={() => setHighOpen(!highOpen)} />
      {highOpen ? <Drawer>
        <HighPointsSwitch state={state} busy={busy} execute={execute} />
        {points.length ? <>
          <Divider />
          <DrawerLabel>{text.advanced}</DrawerLabel>
          <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 5, gridTemplateColumns: "repeat(3,minmax(0,1fr))", marginBottom: 4 }}>
            {points.map((point, index) => {
              const current = point.frequency === liveHighPoint?.frequency;
              const allowed = Boolean(state.gpu_allowed_range && point.frequency <= state.gpu_allowed_range[1]);
              return <PadButton key={point.frequency} label={`${ghz(point.frequency)} GHz`} disabled={busy || !gpuReady || !allowed} preferredFocus={current || (!liveHighPoint && index === 0)}
                onActivate={() => { if (!current) void execute(`GPU · ${governorName || text.advanced}`, () => applyGpuSafePoint(point.frequency), "gpu"); }}
                style={{ alignItems: "center", background: current ? accent.focus_soft : tokens.colors.panel, border: `1px solid ${current ? accent.focus : tokens.colors.border_soft}`, display: "flex", flexDirection: "column", gap: 1, height: 42, justifyContent: "center", padding: "3px 2px", width: "100%" }}>
                <span style={{ color: current ? accent.focus : tokens.colors.text, fontSize: 11, fontWeight: 700 }}>{ghz(point.frequency)} GHz</span>
                <span style={{ color: tokens.colors.subtle, fontSize: 8.5 }}>{point.voltage} mV</span>
              </PadButton>;
            })}
          </Focusable>
        </> : null}
      </Drawer> : null}
    </> : null}
    <VoltageLab state={state} busy={busy} execute={execute} />
    <CyanCompatibility state={state} busy={busy} execute={execute} />
    <GovernorServiceRow state={state} busy={busy} execute={execute} />
    </>}
    </section> : null}

    {boardSection === "cu" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="cu" title={text.compute} trailing={<b style={{ color: accent.focus, fontSize: 11 }}>{draftCUs}/40 {text.target}</b>} />
      {/* linux-cachyos-bc250 owns CU routing (bc250_cc_write_mode=3): read-only. */}
      {state.cu_kernel_managed ? <div style={{ color: tokens.colors.amber, fontSize: 10, marginBottom: 6 }}>{text.cuKernelManaged}</div> : null}
      {state.cu_snapshot_warning ? <div style={{ color: tokens.colors.amber, fontSize: 10, marginBottom: 6 }}>{text.snapshotWarning}</div> : null}
      {cuConflict ? <div style={{ background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, fontSize: 10, marginBottom: 6, padding: 6 }}>{text.external}<div style={{ marginTop: 5 }}><ActionRow><Action label={text.restore} disabled={busy} onActivate={() => { dirty.current.cu = false; setCuConflict(false); setCuDraft(liveMasks); }} /><Action label={text.keep} disabled={busy} onActivate={() => setCuConflict(false)} /></ActionRow></div></div> : null}
      {topology ? <CuMatrix live={liveMasks} driver={driverMasks} draft={cuDraft} disabled={busy || (!state.cu_backend_ready || Boolean(state.cu_kernel_managed))} change={(masks) => { dirty.current.cu = true; setCuConflict(false); setCuDraft(masks); }} minimum={() => setFeedback(text.safeCuMinimum)} /> : <div style={{ color: loaded ? tokens.colors.amber : tokens.colors.subtle, fontSize: 10, marginBottom: 6 }}>{loaded ? text.topologyUnavailable : text.loadingTopology}</div>}
      <div style={{ minHeight: 78, width: "100%" }}>
        <ActionRow marginBottom={6}><Action label={text.applyChanges} primary disabled={busy || !topology || (!state.cu_backend_ready || Boolean(state.cu_kernel_managed)) || sameMasks(cuDraft, liveMasks)} onActivate={() => void execute("BC250 CU", () => applyCuTable(cuDraft), "cu")} /><Action label={text.save} disabled={busy || !topology || (!state.cu_backend_ready || Boolean(state.cu_kernel_managed))} onActivate={() => void execute("BC250 CU", () => saveCuTable(cuDraft), "cu")} /></ActionRow>
        <ActionRow><Action label={text.install} disabled={busy || Boolean(state.cu_kernel_managed) || Boolean(state.cu_service_installed) || !validMasks(state.cu_saved_masks ?? undefined)} onActivate={() => void execute("BC250 CU", installCuService, "cu")} /><Action label={text.remove} danger disabled={busy || !state.cu_service_installed} onActivate={() => showModal(<ConfirmModal strTitle={text.remove} strDescription={text.liveRoutingUnchanged} strOKButtonText={text.remove} bDestructiveWarning onOK={() => void execute("BC250 CU", removeCuService, "cu")} />)} /></ActionRow>
      </div>
    </section> : null}

    {boardSection === "cpu" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="cpu" title="CPU" />
      {cpuError ? <div style={{ background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red}`, borderRadius: 6, color: tokens.colors.red, fontSize: 9, lineHeight: 1.35, marginBottom: 7, overflowWrap: "anywhere", padding: "6px 8px" }}>{localizedErrorSummary(cpuError)}</div> : null}
      {cpuOperation ? <div role="status" aria-live="polite" style={{ background: accent.focus_soft, border: `1px solid ${accent.focus}`, borderRadius: 7, marginBottom: 7, padding: "8px 9px" }}>
        <div style={{ alignItems: "center", display: "flex", gap: 7 }}><span style={{ background: accent.focus, borderRadius: "50%", boxShadow: `0 0 0 3px ${accent.focus_soft}`, height: 7, width: 7 }} /><b style={{ color: accent.focus, flex: 1, fontSize: 11 }}>{text.cpuApplying}</b><span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.elapsed}: {cpuElapsed}s</span></div>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "4px 0 7px 14px" }}>{text.cpuPleaseWait}</div>
        <div style={{ display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr" }}><div style={{ background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }}><span style={{ color: tokens.colors.muted, display: "block", fontSize: 8 }}>{text.cpuLiveClock}</span><b style={{ fontSize: 12 }}>{state.cpu_frequency_mhz ?? "—"} MHz</b></div><div style={{ background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }}><span style={{ color: tokens.colors.muted, display: "block", fontSize: 8 }}>{text.cpuTarget}</span><b style={{ fontSize: 12 }}>{cpuOperation.target} MHz</b></div></div>
      </div> : null}
      {!loaded ? <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 7px" }}>{text.loadingCpu}</div>
        : !cpuReady ? <div style={{ color: state.cpu_tuning_source === "detector-required" ? tokens.colors.subtle : tokens.colors.red, fontSize: 9, margin: "0 2px 7px" }}>{state.cpu_tuning_source === "stress-unavailable" ? text.stressMissing : (state.cpu_tuning_source === "detector-required" ? text.cpuNeedsDetection : (state.cpu_tuning_source === "helper-unavailable" ? text.cpuHelperUnavailable : text.cpuStatusUnavailable))}</div>
        : null}
      {loaded && !cpuReady && state.cpu_tuning_error && state.cpu_tuning_source !== "detector-required" ? <div style={{ color: tokens.colors.muted, fontSize: 8, margin: "-3px 2px 7px", overflowWrap: "anywhere" }}>{localizedErrorSummary(state.cpu_tuning_error)}</div> : null}
      {state.cpu_profiles?.length ? <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: `repeat(${state.cpu_profiles.length},minmax(0,1fr))`, marginBottom: 7 }}>
        {state.cpu_profiles.map((preset) => {
          const current = !cpuManual && cpuFrequency === preset.frequency && cpuVid === preset.vid;
          return <ProfileCard key={preset.key} title={cpuPresetName(preset)} detail={`${ghz(preset.frequency)} GHz`} current={current} disabled={busy || !cpuReady}
            onActivate={() => { setCpuFrequency(preset.frequency); setCpuVid(preset.vid); setCpuManual(false); dirty.current.cpu = true; }} />;
        })}
      </Focusable> : null}
      {detectedCpu?.ready ? <div style={{ alignItems: "center", background: tokens.colors.green_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.cpuDetected}</span><b style={{ color: tokens.colors.green }}>{detectedCpuSummary}</b></div> : null}
      <div style={{ borderTop: `1px solid ${tokens.colors.border_soft}`, paddingTop: 7 }}>
        <CompactSlider label={text.cpuFrequency} value={cpuFrequency} suffix=" MHz" min={cpuMin} max={cpuMax} step={cpuStep} disabled={busy || !cpuReady} onChange={(value) => { setCpuFrequency(Math.max(cpuMin, Math.min(cpuMax, Math.round(value / cpuStep) * cpuStep))); dirty.current.cpu = true; }} />
        <CompactSlider label={text.cpuVoltage} value={cpuVid} suffix=" mV" min={vidMin} max={vidMax} step={vidStep} disabled={busy || !cpuReady || cpuManual} onChange={(value) => { setCpuVid(Math.max(vidMin, Math.min(vidMax, Math.round(value / 5) * 5))); dirty.current.cpu = true; }} />
        {!cpuManual && cpuVid >= vidMax - 25 ? <div style={{ color: tokens.colors.amber, fontSize: 8, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuVidCeiling}</div> : null}
        <div title={manualScaleDescription} style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, fontSize: 11, marginBottom: 4, overflow: "hidden" }}><SwitchRow label={text.cpuManual} checked={cpuManual} disabled={busy || !manualReady} onChange={(checked) => { setCpuManual(checked); if (checked && detectedCpu) { setCpuScale(activeCpu?.frequency === detectedCpu.frequency ? (activeCpu.scale ?? detectedCpu.scale) : detectedCpu.scale); } dirty.current.cpu = true; }} /></div>
        {cpuManual && detectedCpu && !manualFrequencyReady ? <div style={{ color: tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuManualHelp} · {detectedCpu.frequency} MHz</div> : null}
        <CompactSlider label={text.cpuScale} value={cpuScale} suffix="" min={scaleMin} max={scaleMax} step={1} disabled={busy || !cpuManual || !manualFrequencyReady} onChange={(value) => { setCpuScale(Math.max(-50, Math.min(0, Math.round(value)))); dirty.current.cpu = true; }} />
        {cpuManual ? <div style={{ color: tokens.colors.disabled_text, display: "flex", fontSize: 9, justifyContent: "space-between", margin: "0 2px 7px" }}><span>{`${text.cpuScale}: ${scaleMin}…${scaleMax}`}</span><span>{`~${selectedEstimatedVid ?? "—"} mV`}</span></div> : null}
        <ActionRow><Action label={cpuManual ? text.cpuApplyManual : text.cpuApplyAuto} primary disabled={busy || !cpuReady || (cpuManual && (!manualFrequencyReady || (selectedEstimatedVid ?? 0) > vidMax))} onActivate={() => confirmCpu("detect")} /></ActionRow>
      </div>
      <div style={{ marginTop: 6, minHeight: 36 }}><ActionRow><Action label={text.install} disabled={busy || !activeMatchesTarget || Boolean(state.cpu_service_enabled)} onActivate={() => confirmCpu("install")} /><Action label={text.remove} danger disabled={busy || (!state.cpu_service_installed && !state.cpu_service_enabled)} onActivate={() => showModal(<ConfirmModal strTitle={text.remove} strDescription={text.serviceRemovedBootProfile} strOKButtonText={text.remove} bDestructiveWarning onOK={() => void execute("BC250 CPU", removeCpuService, "cpu")} />)} /></ActionRow></div>
    </section> : null}

    {boardSection === "fan" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="fan" title={text.fan} />
      <FanPresetRow state={state} busy={busy} execute={execute} />
      <PadButton disabled={busy} onActivate={() => setFanOpen(!fanOpen)} style={{ alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }}><span>{liveFan?.label ?? `PWM ${fanChannel}`} · {fanDetected ? text.detected : text.unavailable}</span><span style={{ color: accent.focus }}>{fanOpen ? "▴" : "▾"}</span></PadButton>
      {fanOpen ? <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", marginBottom: 7 }}>{fanChannels.map((channel) => { const option = state.fan_channel_options?.find((item) => item.channel === channel); const available = detectedFans.includes(channel); return <PadButton key={channel} disabled={busy || !available} preferredFocus={channel === fanChannel} onActivate={() => { selectionRef.current.fan = channel; setFanChannel(channel); setFanOpen(false); dirty.current.fan = false; const percent = option?.percent; if (percent != null) setFanDuty(percent); }} style={{ background: channel === fanChannel ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${channel === fanChannel ? accent.focus : tokens.colors.border}`, color: channel === fanChannel ? accent.focus : tokens.colors.text, fontSize: 10, height: 34, padding: 4, width: "100%" }}>PWM {channel} · {available ? `${option?.percent ?? "—"}%` : text.unavailable}</PadButton>; })}</Focusable> : null}
      {liveFan ? <div style={{ color: liveFan.rpm_observed ? tokens.colors.subtle : tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "0 2px 6px" }}>{liveFan.rpm_observed ? `${text.fanRpmObserved}: ${liveFan.rpm} RPM` : `${text.fanUnverified}. ${fanChannel === 2 ? text.fanWiring : ""}`}</div> : null}
      <SliderField label={text.speed} value={fanDuty} min={fanMin} max={fanMax} step={fanStep} minimumDpadGranularity={fanStep} showValue valueSuffix="%" disabled={busy || !fanDetected} onChange={(value: number) => { dirty.current.fan = true; setFanDuty(Math.max(20, Math.min(100, Math.round(value / 5) * 5))); }} />
      <Focusable flow-children="grid" style={{ display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr", marginTop: 6 }}><Action label={text.apply} primary disabled={busy || !fanDetected} onActivate={() => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, fanDuty), "fan")} /><Action label={text.automatic} disabled={busy || !fanDetected} onActivate={() => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, "automatic"), "fan")} /></Focusable>
    </section> : null}
    </> : null}

  </SettingsContext.Provider>
  </Focusable>;
}

// Read-only: whether the running game really uses the compute (ACE) queues,
// from the same amdgpu counter the desktop's Performance page reads. The
// counter is the driver's, so it works with MastaG's Mesa (async compute on by
// default) as well as with the app's own GFX1013 build.
function AceRow({ state }: { state: Status }) {
  const game = useRunningGame();
  const percent = state.ace_busy_percent;
  const available = Boolean(state.ace_available);
  const active = typeof percent === "number" && percent > 0;
  const who = active ? (game?.name || state.ace_process || "") : "";
  const value = !available ? "—"
    : percent == null ? text.aceMeasuring
    : active ? `${text.yes}, ${percent} %${who ? ` · ${who}` : ""}`
    : text.no;
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${active ? tokens.colors.green : tokens.colors.border}`, borderRadius: 6, marginBottom: 8, overflow: "hidden" }}>
    <StatusRow label={text.aceInUse} value={value} active={available ? active : null} />
    <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.35, padding: "0 9px 7px" }}>{text.aceHint}</div>
  </div>;
}

// Decky's system-fan presets, named and tuned from the desktop's Fans page
// when the player exported them there. They never touch the pump channel.
function FanPresetRow({ state, busy, execute }: { state: Status; busy: boolean; execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void> }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const presets = state.fan_profiles?.length ? state.fan_profiles : [
    { key: "quiet", name: "", percent: 40 }, { key: "balanced", name: "", percent: 60 }, { key: "boost", name: "", percent: 80 },
  ];
  const available = (state.system_fan_channels ?? []).length > 0;
  const options = [...presets.map((preset) => ({ key: preset.key, label: presetLabel(preset.key, presets), detail: `${preset.percent}%` })), { key: "automatic", label: text.automatic, detail: "BIOS" }];
  return <>
    <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 4px" }}>{text.fanPresets}</div>
    <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 5, gridTemplateColumns: "repeat(4,minmax(0,1fr))", marginBottom: 8 }}>
      {options.map((option) => {
        const current = state.system_fan_preset === option.key;
        return <PadButton key={option.key} disabled={busy || !available} preferredFocus={current} onActivate={() => { if (!current) void execute(`${text.fans} · ${option.label}`, () => applySystemFanPreset(option.key), "fan"); }}
          style={{ alignItems: "center", background: current ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, display: "flex", flexDirection: "column", gap: 1, height: 44, justifyContent: "center", minWidth: 0, padding: "4px 3px", width: "100%" }}>
          <span style={{ color: current ? accent.focus : tokens.colors.text, fontSize: 10, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{option.label}</span>
          <span style={{ color: current ? accent.focus : tokens.colors.subtle, fontSize: 9 }}>{option.detail}</span>
        </PadButton>;
      })}
    </Focusable>
  </>;
}

// The running game's own GPU profile and fan preset. Saved choices are names
// the panel already offers; Decky applies them when the game starts and puts
// the previous ones back when it ends, whether or not this panel is open.
function GameProfileCard({ state, busy }: { state: Status; busy: boolean }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const game = useRunningGame();
  const [store, setStore] = useState<GameStore>({});
  const [editing, setEditing] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [draftGpu, setDraftGpu] = useState<string | null>(null);
  const [draftFan, setDraftFan] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { const result = await getGameProfiles(); if (result.ok !== false) setStore(result); } catch { /* retried on the next change */ }
  }, []);
  useEffect(() => { void load(); gameStoreListeners.add(load); return () => { gameStoreListeners.delete(load); }; }, [load]);
  useEffect(() => { void load(); setEditing(false); }, [game?.appId, load]);
  const games = store.games ?? [];
  const saved = game ? games.find((entry) => entry.app_id === game.appId) : undefined;
  const active = Boolean(game && store.session?.app_id === game.appId);
  const enabled = store.enabled !== false;
  const gpuProfiles = state.gpu_profiles ?? [];
  const fanPresets = state.fan_profiles ?? [];
  const summary = (entry: { gpu: string | null; fan: string | null }) => `GPU ${gpuLabel(entry.gpu, gpuProfiles)} · ${text.fans} ${presetLabel(entry.fan, fanPresets)}`;
  const run = async (operation: () => Promise<GameStore | GameEvent>) => {
    if (working) return; setWorking(true);
    try { const result = await operation(); if (result.ok === false) toaster.toast({ title: text.perGameProfiles, body: localizedErrorSummary(result.error ?? text.error) }); }
    catch (error) { toaster.toast({ title: text.perGameProfiles, body: localizedErrorSummary(failed(error).error ?? text.error) }); }
    finally { setWorking(false); await load(); }
  };
  const beginEdit = () => { setDraftGpu(saved?.gpu ?? null); setDraftFan(saved?.fan ?? null); setEditing(true); };
  const save = () => {
    if (!game) return;
    void run(async () => {
      const result = await saveGameProfile(game.appId, game.name, draftGpu, draftFan);
      if (result.ok === false) return result;
      setEditing(false);
      // Playing it right now: the new choice takes effect at once.
      if (result.enabled !== false) await onGameStart(game.appId, game.name, true);
      return result;
    });
  };
  const remove = (appId: string) => void run(async () => {
    const result = await removeGameProfile(appId);
    if (store.session?.app_id === appId) await onGameStop(appId);
    if (runningGame?.appId === appId) setRunningGame(runningGame);
    return result;
  });
  const toggle = (next: boolean) => void run(async () => {
    const result = await setGameProfilesEnabled(next);
    if (!next && store.session) await gameStopped(store.session.app_id).then(notifyGameStore);
    if (next && game) await onGameStart(game.appId, game.name);
    return result;
  });
  const pill = (icon: ReactElement, label: string) => <span style={{ alignItems: "center", background: tokens.colors.panel_raised, borderRadius: 10, color: tokens.colors.muted, display: "inline-flex", fontSize: 9, gap: 4, maxWidth: "100%", padding: "2px 8px 2px 6px" }}>
    {icon}<span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span></span>;
  const profilePills = (entry: { gpu: string | null; fan: string | null }) => <span style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
    {pill(<LuMicrochip strokeWidth={1.75} />, gpuLabel(entry.gpu, gpuProfiles))}
    {pill(<LuFan strokeWidth={1.75} />, presetLabel(entry.fan, fanPresets))}
  </span>;
  const gpuOptions = [{ key: "none", label: text.unchanged }, ...gpuProfiles.map((profile) => ({ key: profile.key, label: gpuProfileName(profile) }))];
  const fanOptions = [{ key: "none", label: text.unchanged }, ...["quiet", "balanced", "boost", "automatic"].map((key) => ({ key, label: presetLabel(key, fanPresets) }))];
  return <section style={{ background: tokens.colors.panel_alt, border: `1px solid ${active ? accent.focus : tokens.colors.border}`, borderRadius: 10, marginBottom: 10, padding: "8px 8px 4px" }}>
    <SectionTitle kind="game" title={text.perGameProfiles} trailing={active ? <span style={{ background: accent.focus_soft, borderRadius: 8, color: accent.focus, fontSize: 8, fontWeight: 800, letterSpacing: .4, padding: "1px 6px" }}>{text.gameProfileActive}</span> : undefined} />
    <SwitchRow label={text.applyAutomatically} checked={enabled} disabled={working} onChange={toggle} />
    {!game ? <div style={{ color: tokens.colors.subtle, fontSize: 9.5, lineHeight: 1.4, margin: "0 8px 8px" }}>{text.gameNotRunning}</div> : <>
      <div style={{ background: tokens.colors.panel, borderRadius: 8, display: "flex", flexDirection: "column", gap: 5, margin: "2px 0 8px", padding: "8px 9px" }}>
        <div style={{ alignItems: "center", display: "flex", gap: 6 }}>
          <LuGamepad2 strokeWidth={1.5} color={active ? accent.focus : tokens.colors.subtle} />
          <span style={{ color: tokens.colors.text, flex: 1, fontSize: 12, fontWeight: 700, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{game.name}</span>
        </div>
        {saved ? profilePills(saved) : <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.gameNoProfile}</span>}
      </div>
      {!editing ? <ActionRow marginBottom={8}>
        <Action label={saved ? text.editProfile : text.assignProfile} primary={!saved} disabled={working || busy} onActivate={beginEdit} />
        {saved ? <Action label={text.removeGame} danger disabled={working} onActivate={() => remove(saved.app_id)} /> : null}
      </ActionRow> : <Drawer>
        <DrawerLabel>GPU</DrawerLabel>
        <Segmented disabled={working} value={draftGpu ?? "none"} columns={Math.min(4, gpuOptions.length)} onChange={(key) => setDraftGpu(key === "none" ? null : key)} options={gpuOptions} />
        <DrawerLabel>{text.fans}</DrawerLabel>
        <Segmented disabled={working} value={draftFan ?? "none"} columns={3} onChange={(key) => setDraftFan(key === "none" ? null : key)} options={fanOptions} />
        <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.35, margin: "0 2px 8px" }}>{text.gameCpuNote}</div>
        <ActionRow marginBottom={2}>
          <Action label={text.gameProfileSave} primary disabled={working || (!draftGpu && !draftFan)} onActivate={save} />
          <Action label={text.cancel} disabled={working} onActivate={() => setEditing(false)} />
        </ActionRow>
      </Drawer>}
    </>}
    <DisclosureRow label={text.savedGames} value={String(games.length)} open={listOpen} onActivate={() => setListOpen(!listOpen)} />
    {listOpen ? <div style={{ background: tokens.colors.panel, borderRadius: 8, marginBottom: 6, padding: "2px 8px" }}>
      <Focusable flow-children="down">
        {!games.length ? <div style={{ color: tokens.colors.subtle, fontSize: 9, padding: "7px 0" }}>{text.gamesEmpty}</div> : games.map((entry, index) => <Focusable key={entry.app_id} flow-children="row" style={{ alignItems: "center", borderTop: index ? `1px solid ${tokens.colors.border_soft}` : "none", display: "grid", gap: 8, gridTemplateColumns: "1fr 30px", padding: "6px 0" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
            <span style={{ fontSize: 10.5, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name || appName(Number(entry.app_id))}</span>
            {profilePills(entry)}
          </div>
          <PadButton label={text.removeGame} disabled={working} onActivate={() => remove(entry.app_id)} style={{ alignItems: "center", background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red_soft}`, color: tokens.colors.red, display: "flex", fontSize: 14, height: 30, justifyContent: "center", padding: 0, width: "100%" }}><LuTrash2 strokeWidth={1.75} /></PadButton>
        </Focusable>)}
      </Focusable>
    </div> : null}
  </section>;
}

function SettingsTab({ settings, setSettings, state, busy, execute }: {
  settings: QuickAccessSettings; setSettings: (next: QuickAccessSettings) => void;
  state: Status; busy: boolean;
  execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void>;
}) {
  const accent = ACCENT_SWATCHES[settings.accent];
  return <>
    <section style={{ marginBottom: 12 }}>
      <SectionTitle kind="settings" title={text.accentColor} />
      <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
        {ACCENT_KEYS.map((key) => {
          const swatch = ACCENT_SWATCHES[key];
          const active = settings.accent === key;
          return <PadButton key={key} preferredFocus={active} onActivate={() => setSettings({ ...settings, accent: key })} style={{ alignItems: "center", background: active ? swatch.focus_soft : tokens.colors.panel_raised, border: `1px solid ${active ? swatch.focus : tokens.colors.border}`, display: "flex", flexDirection: "column", gap: 4, height: 48, justifyContent: "center", width: "100%" }}>
            <span style={{ background: swatch.focus, border: `1px solid ${tokens.colors.border_strong}`, borderRadius: "50%", height: 14, width: 14 }} />
            <span style={{ color: active ? swatch.focus : tokens.colors.subtle, fontSize: 9, fontWeight: 650 }}>{swatch.label}</span>
          </PadButton>;
        })}
      </Focusable>
    </section>

    <section style={{ marginBottom: 12 }}>
      <SectionTitle kind="settings" title={text.refreshInterval} />
      <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
        {REFRESH_INTERVAL_OPTIONS.map((ms) => {
          const active = settings.refreshIntervalMs === ms;
          return <PadButton key={ms} preferredFocus={active} onActivate={() => setSettings({ ...settings, refreshIntervalMs: ms })} style={{ alignItems: "center", background: active ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${active ? accent.focus : tokens.colors.border}`, color: active ? accent.focus : tokens.colors.text, display: "flex", fontSize: 11, fontWeight: 650, height: 36, justifyContent: "center", width: "100%" }}>
            {ms / 1000}s
          </PadButton>;
        })}
      </Focusable>
      <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.4, margin: "6px 2px 0" }}>{text.refreshIntervalHint}</div>
    </section>

    <section style={{ marginBottom: 12 }}>
      <SectionTitle kind="settings" title={text.sensorLayout} />
      <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr" }}>
        {([["grid", text.layoutGrid], ["list", text.layoutList]] as [SensorLayout, string][]).map(([layout, label]) => {
          const active = settings.sensorLayout === layout;
          return <PadButton key={layout} preferredFocus={active} onActivate={() => setSettings({ ...settings, sensorLayout: layout })} style={{ alignItems: "center", background: active ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${active ? accent.focus : tokens.colors.border}`, color: active ? accent.focus : tokens.colors.text, display: "flex", fontSize: 11, fontWeight: 650, height: 36, justifyContent: "center", width: "100%" }}>
            {label}
          </PadButton>;
        })}
      </Focusable>
    </section>

  </>;
}

type SteamGlobals = typeof globalThis & {
  SteamClient?: { GameSessions?: { RegisterForAppLifetimeNotifications?: (callback: (update: { unAppID: number; nInstanceID: number; bRunning: boolean }) => void) => { unregister?: () => void } } };
};

export default definePlugin(() => {
  // Registered with the plugin, not the panel: per-game profiles follow
  // games while the Quick Access menu is closed, which is nearly always.
  const lifetime = (globalThis as SteamGlobals).SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.(onAppLifetime);
  // A game already running when Decky (re)loaded the plugin.
  const current = Router.MainRunningApp;
  if (current?.appid) {
    runningInstances.set(String(current.appid), new Set([0]));
    void onGameStart(String(current.appid), current.display_name || appName(Number(current.appid)));
  }
  return {
    name: "BC250 Quick Access",
    titleView: <div className={staticClasses.Title}>BC250 Quick Access</div>,
    content: <Content />,
    icon: <FaMicrochip />,
    onDismount() { lifetime?.unregister?.(); },
  };
});
