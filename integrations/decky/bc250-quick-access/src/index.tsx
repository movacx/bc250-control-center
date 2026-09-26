import {
  Button,
  ConfirmModal,
  Focusable,
  NavEntryPositionPreferences,
  Router,
  showModal,
  SliderField,
  staticClasses,
  ToggleField,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import {
  type CSSProperties,
  type ReactNode,
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
  FaChartLine,
  FaClock,
  FaCog,
  FaExclamationTriangle,
  FaFan,
  FaGamepad,
  FaHdd,
  FaLayerGroup,
  FaMemory,
  FaMicrochip,
  FaSlidersH,
  FaTh,
} from "react-icons/fa";
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
type CpuPreset = { key: string; name: string; frequency: number; vid: number };
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
type VramState = { supported: boolean; reason: string; uma_size_mb: number | null; boot_id: string | null };

type Result = {
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
  gpu_service_conflict?: boolean;
  cu_backend_ready?: boolean;
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
  cpu_cores?: { core: number; percent: number | null; frequency_mhz: number | null }[];
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
type Status = Result;
type VoltagePoint = { frequency: number; voltage: number; default: number };
type DraftKind = "cu" | "fan" | "gpu" | "cpu" | "none";

const getStatus = callable<[], Status>("status");
const getCpuTelemetry = callable<[], Result>("cpu_telemetry");
const getMonitorSnapshot = callable<[], Result>("monitor_snapshot");
const getGddr6Sensors = callable<[], Result>("gddr6_sensors");
const applyGpuProfile = callable<[profile: string], Result>("apply_gpu_profile");
const applyGpuSafePoint = callable<[frequency: number], Result>("apply_gpu_safe_point");
const setGpuHighFrequencyPoints = callable<[enabled: boolean], Result>("set_gpu_high_frequency_points");
const setGpuGovernorService = callable<[enabled: boolean], Result>("set_gpu_governor_service");
const applyGpuVoltageLevel = callable<[level: number], Result>("apply_gpu_voltage_level");
const applyGpuVoltagePoints = callable<[points: { frequency: number; voltage: number }[]], Result>("apply_gpu_voltage_points");
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
  return sizeMb < 1024 ? `${sizeMb} MiB` : `${sizeMb / 1024} GiB`;
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
function gpuLabel(key: string | null | undefined, profiles?: GpuProfile[]): string {
  if (!key) return text.unchanged;
  const named = profiles?.find((profile) => profile.key === key)?.name;
  if (named) return named;
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

const SettingsContext = createContext<{ settings: QuickAccessSettings; setSettings: (next: QuickAccessSettings) => void }>({
  settings: DEFAULT_SETTINGS, setSettings: () => {},
});

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
  const summary = conflict ? text.governorConflict
    : !installed ? text.serviceNotInstalled
    : running ? (atBoot ? text.serviceRunningBoot : text.serviceRunningNoBoot)
    : (atBoot ? text.serviceStoppedBoot : text.serviceStopped);
  const tone = conflict ? tokens.colors.red : !installed ? tokens.colors.amber : running ? accent.focus : tokens.colors.subtle;
  const confirm = (enable: boolean) => showModal(<ConfirmModal
    strTitle={enable ? text.enableService : text.disableService}
    strDescription={(enable ? text.enableServiceHint : text.disableServiceHint).replace("{name}", name)}
    strOKButtonText={enable ? text.enableService : text.disableService}
    bDestructiveWarning={!enable}
    onOK={() => void execute(`GPU · ${text.governorService}`, () => setGpuGovernorService(enable), "gpu")}
  />);
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginTop: 6, padding: "7px 8px 8px" }}>
    <div style={{ alignItems: "baseline", display: "flex", gap: 6, justifyContent: "space-between", marginBottom: 6 }}>
      <span style={{ color: tokens.colors.text, fontSize: 10, fontWeight: 650 }}>{text.governorService}{name ? <span style={{ color: tokens.colors.subtle, fontWeight: 500 }}> · {name}</span> : null}</span>
      <span style={{ color: tone, fontSize: 9, fontWeight: 650, textAlign: "right" }}>{summary}</span>
    </div>
    <ActionRow>
      <Action label={text.enableService} primary={installed && !running} disabled={busy || !installed || conflict || (running && atBoot)} onActivate={() => confirm(true)} />
      <Action label={text.disableService} danger disabled={busy || !installed || conflict || (!running && !atBoot)} onActivate={() => confirm(false)} />
    </ActionRow>
  </div>;
}

// Cyan's commented TOML points above 2000 MHz, as the switch it is. It lives
// in Settings: it is a one-time decision about what the GPU tab offers, not
// a control used while playing. It asks first, and a cancelled question puts
// the switch back where the file is.
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
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${enabled ? tokens.colors.red : tokens.colors.border_soft}`, borderRadius: 6, fontSize: 11, marginBottom: 6, overflow: "hidden" }}>
    <ToggleField key={`${revision}-${enabled}`} label={text.highFrequencyPoints} description={cyanActive ? undefined : text.highFrequencyCyanOnly} layout="inline" bottomSeparator="none" highlightOnFocus checked={enabled} disabled={busy || !cyanActive} onChange={request} />
  </div>;
}

function Action({ label, disabled, primary, danger, onActivate }: { label: string; disabled: boolean; primary?: boolean; danger?: boolean; onActivate: () => void }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  return <PadButton disabled={disabled} onActivate={onActivate} style={{
    background: danger ? tokens.colors.red_soft : primary ? accent.focus : tokens.colors.panel_raised,
    border: `1px solid ${danger ? tokens.colors.red_soft : primary ? accent.focus : tokens.colors.border}`,
    color: danger ? tokens.colors.red : primary ? tokens.colors.selection : tokens.colors.text,
    alignItems: "center", boxSizing: "border-box", display: "flex", flex: 1, fontSize: 10, fontWeight: primary ? 700 : 600, height: 36, justifyContent: "center", lineHeight: 1.15, minWidth: 0, padding: "4px 7px", textAlign: "center", whiteSpace: "normal", width: "100%",
  }}>{label}</PadButton>;
}

function ActionRow({ children, marginBottom = 0 }: { children: ReactNode; marginBottom?: number }) {
  return <Focusable flow-children="right" style={{ alignItems: "stretch", display: "flex", gap: 6, height: 36, marginBottom, minHeight: 36, width: "100%" }}>{children}</Focusable>;
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

function CoreGrid({ cores }: { cores: { core: number; percent: number | null; frequency_mhz: number | null }[] }) {
  if (!cores.length) return null;
  const columns = cores.length > 6 ? 4 : cores.length > 2 ? 3 : 2;
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gap: 1, gridTemplateColumns: `repeat(${columns},minmax(0,1fr))`, marginBottom: 10, overflow: "hidden" }}>
    {cores.map((entry) => <div key={entry.core} style={{ background: tokens.colors.panel_raised, padding: "6px 7px" }}>
      <div style={{ color: tokens.colors.subtle, fontSize: 8 }}>N{entry.core + 1}</div>
      <div style={{ fontSize: 10, fontWeight: 650 }}>{entry.frequency_mhz != null ? `${(entry.frequency_mhz / 1000).toFixed(2)} GHz` : "—"}</div>
      <div style={{ color: tokens.colors.subtle, fontSize: 9 }}>{entry.percent != null ? `${entry.percent}%` : "—"}</div>
    </div>)}
  </div>;
}

type MonitorSection = "cpu" | "gpu" | "cooling" | "all";

function SubNav<T extends string>({ value, onChange, items }: { value: T; onChange: (next: T) => void; items: { key: T; label: string; icon: ReactNode; color: string; colorSoft: string }[] }) {
  return <Focusable flow-children="row" style={{ display: "grid", gap: 5, gridTemplateColumns: `repeat(${items.length},minmax(0,1fr))`, marginBottom: 10 }}>
    {items.map((item) => {
      const active = item.key === value;
      return <PadButton key={item.key} onActivate={() => onChange(item.key)} style={{ alignItems: "center", background: active ? item.colorSoft : tokens.colors.panel_alt, border: `1px solid ${active ? item.color : tokens.colors.border}`, color: active ? item.color : tokens.colors.subtle, display: "flex", flexDirection: "column", fontSize: 9, fontWeight: 650, gap: 3, height: 40, justifyContent: "center", padding: "4px 2px" }}>
        {item.icon}<span>{item.label}</span>
      </PadButton>;
    })}
  </Focusable>;
}

function Gddr6Panel({ state }: { state: Status }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const chips = state.gddr6_chips ?? [];
  const available = Boolean(state.gddr6_available) && chips.length > 0;
  return <div style={{ margin: "2px 0 6px" }}>
    <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "4px 2px 4px", textTransform: "uppercase" }}>GDDR6</div>
    {!available
      ? <div style={{ color: tokens.colors.amber, fontSize: 10, lineHeight: 1.4, margin: "0 2px 6px" }}>{text.gddr6Unavailable}</div>
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

const VOLTAGE_LEVELS = [0, 1, 2, 3] as const;
const VOLTAGE_STEP_MV = 5;
const VOLTAGE_MAX_ABOVE_DEFAULT_MV = 60;

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
    <PadButton onActivate={() => setOpen(!open)} disabled={!points.length} style={{ alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }}>
      <span>{text.voltageLab}</span>
      <span style={{ color: accent.focus }}>{points.length ? levelLabel : text.unavailable} {open ? "▴" : "▾"}</span>
    </PadButton>
    {open ? <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, marginBottom: 6, padding: 6 }}>
      {!cyanRunning ? <div style={{ color: tokens.colors.amber, fontSize: 9, marginBottom: 6 }}>{text.voltageNeedsCyan}</div> : null}
      <Focusable flow-children="row" style={{ display: "grid", gap: 5, gridTemplateColumns: "repeat(4,minmax(0,1fr))", marginBottom: 6 }}>
        {VOLTAGE_LEVELS.map((value) => {
          const current = level === value;
          return <PadButton key={value} preferredFocus={current || (level == null && value === 0)} disabled={busy || !cyanRunning} onActivate={() => { if (!current) confirmLevel(value); }} style={{ background: current ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, color: current ? accent.focus : tokens.colors.text, fontSize: 10, fontWeight: 650, height: 32, padding: 2, textAlign: "center", width: "100%" }}>{value === 0 ? text.voltageGovernor : `+${value * 10} mV`}</PadButton>;
        })}
      </Focusable>
      <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.35, margin: "0 2px 7px" }}>{text.voltageHint}</div>
      <Focusable flow-children="down">
        {points.map((point) => {
          const value = valueOf(point);
          const moved = value !== point.voltage;
          return <Focusable key={point.frequency} flow-children="row" style={{ alignItems: "center", display: "grid", gap: 5, gridTemplateColumns: "1fr 30px 70px 30px", marginBottom: 4 }}>
            <span style={{ color: tokens.colors.subtle, fontSize: 10 }}>{point.frequency} MHz</span>
            <PadButton label="-5 mV" disabled={busy || !cyanRunning || value <= floorOf(point)} onActivate={() => nudge(point, -VOLTAGE_STEP_MV)} style={{ fontSize: 12, height: 28, padding: 0, width: "100%" }}>−</PadButton>
            <span style={{ color: moved ? accent.focus : tokens.colors.text, fontSize: 11, fontWeight: 650, textAlign: "center" }}>{value} mV</span>
            <PadButton label="+5 mV" disabled={busy || !cyanRunning || value >= floorOf(point) + VOLTAGE_MAX_ABOVE_DEFAULT_MV} onActivate={() => nudge(point, VOLTAGE_STEP_MV)} style={{ fontSize: 12, height: 28, padding: 0, width: "100%" }}>+</PadButton>
          </Focusable>;
        })}
      </Focusable>
      <ActionRow><Action label={text.voltageApplyPoints} primary disabled={busy || !cyanRunning || !changed.length} onActivate={confirmPoints} /><Action label={text.voltageDiscard} disabled={busy || !changed.length} onActivate={() => setDraft({})} /></ActionRow>
    </div> : null}
  </>;
}

function MonitorTab({ state }: { state: Status }) {
  const accent = ACCENT_SWATCHES[useContext(SettingsContext).settings.accent];
  const [section, setSection] = useState<MonitorSection>("cpu");
  const gpuVramKnown = typeof state.gpu_vram_used_mib === "number" && typeof state.gpu_vram_total_mib === "number";
  const gpuGttKnown = typeof state.gpu_gtt_used_mib === "number" && typeof state.gpu_gtt_total_mib === "number";
  const fanOptions = state.fan_channel_options ?? [];
  const vrmAvailable = Boolean(state.vrm_available);
  const activeCpu = state.cpu_active_profile ?? state.cpu_detected_profile?.active_profile;
  const ocModeLabel = !activeCpu ? "—" : activeCpu.mode === "manual" ? text.cpuManual : activeCpu.mode === "boot" ? text.install : text.automatic;
  const ocDetailLabel = activeCpu?.mode === "manual" ? text.cpuScale.toUpperCase() : text.gpuVoltage.toUpperCase();
  const ocDetail = !activeCpu ? text.disabled : activeCpu.mode === "manual" ? String(activeCpu.scale) : `${activeCpu.estimated_vid} mV`;
  const defaultFan = fanOptions.find((option) => option.channel === 2) ?? fanOptions[0];

  // Built once and reused by both each module's own tab and the "All" tab,
  // so the two views can never drift into showing different numbers for the
  // same sensor.
  const cpuTiles = [
    { label: text.cpuFrequency.toUpperCase(), value: `${state.cpu_frequency_mhz ?? "—"} MHz` },
    { label: "TCTL", value: `${state.cpu_temperature_c?.toFixed(1) ?? "—"} °C` },
    { label: text.gpuVoltage.toUpperCase(), value: state.cpu_voltage_mv != null ? `${state.cpu_voltage_mv} mV` : "—" },
    { label: text.usage.toUpperCase(), value: state.cpu_usage_percent != null ? `${state.cpu_usage_percent}%` : "—" },
    { label: "OC", value: activeCpu ? `${activeCpu.frequency} MHz` : text.disabled },
    { label: text.mode.toUpperCase(), value: ocModeLabel },
    { label: ocDetailLabel, value: ocDetail },
    { label: text.persistent.toUpperCase(), value: activeCpu?.persistable ? text.enabled : text.disabled },
  ];
  const cpuVrmTiles = [
    { label: "VRM CPU · TEMP", value: vrmAvailable && state.vrm_cpu_temperature_c != null ? `${state.vrm_cpu_temperature_c.toFixed(1)} °C` : "—" },
    { label: `VRM CPU · ${text.gpuVoltage.toUpperCase()}`, value: state.vrm_cpu_voltage_v != null ? `${state.vrm_cpu_voltage_v.toFixed(2)} V` : "—" },
    { label: "VRM CPU · A", value: state.vrm_cpu_current_a != null ? `${state.vrm_cpu_current_a.toFixed(2)} A` : "—" },
    { label: "VRM CPU · W", value: state.vrm_cpu_power_w != null ? `${state.vrm_cpu_power_w.toFixed(1)} W` : "—" },
  ];
  const gpuTiles = [
    { label: text.gpuLive.toUpperCase(), value: `${state.gpu_core_mhz ?? "—"} MHz` },
    { label: text.gpuVoltage.toUpperCase(), value: `${state.gpu_voltage_mv ?? "—"} mV` },
    { label: "BUSY", value: state.gpu_busy_percent != null ? `${state.gpu_busy_percent}%` : "—" },
    { label: "TEMP", value: state.gpu_temperature_c != null ? `${state.gpu_temperature_c.toFixed(1)} °C` : "—" },
    { label: "MCLK", value: state.gpu_memory_clock_mhz != null ? `${state.gpu_memory_clock_mhz} MHz` : "—" },
    { label: "SOCCLK", value: state.gpu_soc_clock_mhz != null ? `${state.gpu_soc_clock_mhz} MHz` : "—" },
    { label: "FCLK", value: state.gpu_fabric_clock_mhz != null ? `${state.gpu_fabric_clock_mhz} MHz` : "—" },
    { label: "VRAM", value: gpuVramKnown ? `${formatBytes((state.gpu_vram_used_mib ?? 0) * 1024 * 1024)} / ${formatBytes((state.gpu_vram_total_mib ?? 0) * 1024 * 1024)}` : "—" },
    { label: "GTT", value: gpuGttKnown ? `${formatBytes((state.gpu_gtt_used_mib ?? 0) * 1024 * 1024)} / ${formatBytes((state.gpu_gtt_total_mib ?? 0) * 1024 * 1024)}` : "—" },
    { label: "PCIE", value: state.gpu_pcie_link || "—" },
    { label: text.governor.toUpperCase(), value: state.gpu_governor_label || "—" },
    { label: "CU", value: state.cu_active_cus != null && state.cu_total_cus != null ? `${state.cu_active_cus} / ${state.cu_total_cus}` : "—" },
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
  const boardSensorTiles = [
    { label: text.board.toUpperCase(), value: state.board_temperature_c != null ? `${state.board_temperature_c.toFixed(1)} °C` : "—" },
    { label: "M.2", value: state.nvme_temperature_c != null ? `${state.nvme_temperature_c.toFixed(1)} °C` : "—" },
    { label: "M.2 HOTSPOT", value: state.nvme_hotspot_temperature_c != null ? `${state.nvme_hotspot_temperature_c.toFixed(1)} °C` : "—" },
    { label: "VRM MOS", value: state.vrm_mos_temperature_c != null ? `${state.vrm_mos_temperature_c.toFixed(1)} °C` : "—" },
  ];
  const fanControlTiles = [
    { label: `PWM ${text.mode.toUpperCase()}`, value: typeof defaultFan?.mode === "string" ? defaultFan.mode : defaultFan?.mode != null ? String(defaultFan.mode) : "—" },
    { label: text.controller.toUpperCase(), value: defaultFan?.label ?? "—" },
  ];
  const powerTiles = [
    { label: text.inputVoltage.toUpperCase(), value: state.vrm_input_voltage_v != null ? `${state.vrm_input_voltage_v.toFixed(2)} V` : "—" },
    { label: text.totalPower.toUpperCase(), value: state.vrm_total_power_w != null ? `${state.vrm_total_power_w.toFixed(1)} W` : "—" },
  ];
  const fanChannelList = <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, marginBottom: 8, overflow: "hidden" }}>
    {fanChannels.map((channel, index) => {
      const option = fanOptions.find((item) => item.channel === channel);
      const label = option?.label ?? `PWM ${channel}`;
      const detail = option?.available
        ? `${option?.percent ?? "—"}%${option?.rpm_observed ? ` · ${option.rpm} RPM` : ""}`
        : text.unavailable;
      return <div key={channel} style={{ alignItems: "center", borderTop: index > 0 ? `1px solid ${tokens.colors.border}` : "none", display: "flex", fontSize: 10, justifyContent: "space-between", padding: "6px 9px" }}>
        <span style={{ color: tokens.colors.subtle }}>{label}</span>
        <span style={{ color: option?.available ? tokens.colors.text : tokens.colors.disabled_text, fontWeight: 650 }}>{detail}</span>
      </div>;
    })}
  </div>;
  const vrmNotice = !vrmAvailable ? <div style={{ color: tokens.colors.amber, fontSize: 10, lineHeight: 1.4, margin: "0 2px 8px" }}>{text.vrmUnavailable}</div> : null;

  return <>
    <SubNav<MonitorSection> value={section} onChange={setSection} items={[
      { key: "cpu", label: "CPU", icon: <FaBolt />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "gpu", label: "GPU", icon: <FaMicrochip />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "cooling", label: text.fan, icon: <FaFan />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "all", label: text.allSensors, icon: <FaLayerGroup />, color: accent.focus, colorSoft: accent.focus_soft },
    ]} />

    {section === "cpu" ? <Focusable flow-children="down">
      <ScrollStop><MetricGrid tiles={cpuTiles} />
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "-3px 2px 8px" }}>{text.cpuTrial}: {state.cpu_tuning_temperature ?? "—"}°C</div></ScrollStop>
      <ScrollStop><CoreGrid cores={state.cpu_cores ?? []} /></ScrollStop>
      <ScrollStop>{vrmNotice}<MetricGrid tiles={cpuVrmTiles} /></ScrollStop>
      <ScrollStop end />
    </Focusable> : null}

    {section === "gpu" ? <Focusable flow-children="down">
      <ScrollStop><AceRow state={state} /></ScrollStop>
      <ScrollStop><MetricGrid tiles={gpuTiles} />
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "-3px 2px 2px" }}>VBIOS · {state.gpu_vbios_version || "—"}</div>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 6px" }}>{state.gpu_range ? `${state.gpu_range[0]}–${state.gpu_range[1]} MHz` : "—"}{state.gpu_allowed_range ? ` · ${text.safeRange} ${state.gpu_allowed_range[0]}–${state.gpu_allowed_range[1]} MHz` : ""}</div></ScrollStop>
      <ScrollStop>{vrmNotice}<MetricGrid tiles={gpuVrmTiles} /></ScrollStop>
      <ScrollStop><Gddr6Panel state={state} /></ScrollStop>
      <ScrollStop end />
    </Focusable> : null}

    {section === "cooling" ? <Focusable flow-children="down">
      <ScrollStop>{fanChannelList}</ScrollStop>
      <ScrollStop><MetricGrid tiles={fanControlTiles} /></ScrollStop>
      <ScrollStop end />
    </Focusable> : null}

    {section === "all" ? <section>
      {/* Every sensor from every module, stacked in one screen, purely so a
          player can take a single screenshot instead of one per tab. Each
          block is a ScrollStop so the D-pad can walk down to the last one. */}
      <Focusable flow-children="down">
        <ScrollStop><SectionTitle kind="cpu" title="CPU" /><MetricGrid tiles={cpuTiles} /></ScrollStop>
        <ScrollStop><CoreGrid cores={state.cpu_cores ?? []} /></ScrollStop>
        <ScrollStop><MetricGrid tiles={cpuVrmTiles} /></ScrollStop>

        <ScrollStop><SectionTitle kind="gpu" title="GPU" /><AceRow state={state} /><MetricGrid tiles={gpuTiles} /></ScrollStop>
        <ScrollStop>
          <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "-3px 2px 8px" }}>VBIOS · {state.gpu_vbios_version || "—"} · {state.gpu_range ? `${state.gpu_range[0]}–${state.gpu_range[1]} MHz` : "—"}{state.gpu_allowed_range ? ` · ${text.safeRange} ${state.gpu_allowed_range[0]}–${state.gpu_allowed_range[1]} MHz` : ""}</div>
          <MetricGrid tiles={gpuVrmTiles} />
        </ScrollStop>
        <ScrollStop><Gddr6Panel state={state} /></ScrollStop>

        <ScrollStop><SectionTitle kind="fan" title={text.fan} />{fanChannelList}</ScrollStop>
        <ScrollStop><MetricGrid tiles={boardSensorTiles} /></ScrollStop>
        <ScrollStop><MetricGrid tiles={fanControlTiles} /></ScrollStop>

        <ScrollStop><SectionTitle kind="power" title={text.power} />{vrmNotice}<MetricGrid tiles={powerTiles} /></ScrollStop>
        <ScrollStop end />
      </Focusable>
    </section> : null}
  </>;
}

function MemoryTab({ state, busy, execute }: { state: Status; busy: boolean; execute: (title: string, operation: () => Promise<Result>, kind?: DraftKind) => Promise<void> }) {
  const vram = state.vram;
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
  const vramRebootPending = Boolean(
    vramPending && vram?.boot_id === vramPending.bootId && vram?.uma_size_mb === vramPending.mb,
  );
  const confirmVram = () => showModal(<ConfirmModal
    strTitle={text.vramApply}
    strDescription={`${vramSizeLabel(vramTarget)}. ${text.vramApplyDescription} ${text.vramRebootRequired}`}
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
          <StatusRow label={text.vramCurrentSize} active={null} value={vram?.uma_size_mb != null ? vramSizeLabel(vram.uma_size_mb) : "—"} />
          {vramRebootPending ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.vramPending}</span><b style={{ color: tokens.colors.amber }}>{vramSizeLabel(vramPending?.mb ?? vramTarget)} · {text.vramRebootRequired}</b></div> : null}
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
  </>;
}

type PanelTab = "board" | "monitor" | "memory" | "settings";
type BoardSection = "gpu" | "cu" | "cpu" | "fan";

function Content() {
  const [state, setState] = useState<Status>({});
  const [settings, setSettingsState] = useState<QuickAccessSettings>(() => loadSettings());
  const setSettings = useCallback((next: QuickAccessSettings) => { setSettingsState(next); saveSettings(next); }, []);
  const accent = ACCENT_SWATCHES[settings.accent];
  const [activeTab, setActiveTab] = useState<PanelTab>("board");
  const [boardSection, setBoardSection] = useState<BoardSection>("gpu");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
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
      setState((current) => ({ ...current, ...result })); setLoaded(true); setStale(false);
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
    void sampleGddr6();
    const timer = globalThis.setInterval(() => void sampleGddr6(), settings.refreshIntervalMs * 2);
    return () => globalThis.clearInterval(timer);
  }, [sampleGddr6, settings.refreshIntervalMs]);

  const execute = async (title: string, operation: () => Promise<Result>, kind: DraftKind = "none", cpuProgress?: { target: number; manual: boolean }) => {
    if (busyRef.current) return; busyRef.current = true; setBusy(true);
    if (kind === "cpu") setCpuError(null);
    if (cpuProgress) setCpuOperation({ ...cpuProgress, startedAt: Date.now() });
    try { const result = await operation(); if (result.ok === false) { const message = result.error ?? text.error; if (kind === "cpu") setCpuError(message); setFeedback(message); toaster.toast({ title, body: localizedErrorSummary(message) }); } else { setState((current) => ({ ...current, ...result })); if (kind === "gpu" && Array.isArray(result.gpu_range) && result.gpu_range[0] === 1000 && result.gpu_range[1] > 2000) setHighSelection(result.gpu_range[1]); else if (kind === "gpu") setHighSelection(0); setFeedback(null); if (kind !== "none") dirty.current[kind] = false; toaster.toast({ title, body: text.success }); if (kind !== "gpu") await refresh("after"); } }
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
      // Jump straight to the live view so the player watches the trial
      // happen instead of staring at a frozen GPU/CU screen (see
      // "operationInProgress" — this is the same tab that stays fed by
      // monitor_snapshot() regardless of how long the trial takes).
      if (mode === "detect") setActiveTab("monitor");
      void execute("BC250 CPU", mode === "detect" ? (cpuManual ? () => applyCpuScale(cpuFrequency, cpuScale) : () => applyCpuTuning(cpuFrequency, cpuVid)) : installCpuService, "cpu", mode === "detect" ? { target: cpuFrequency, manual: cpuManual } : undefined);
    }}
  />);

  return <Focusable flow-children="down" style={{ background: tokens.colors.panel, border: `1px solid ${tokens.colors.border}`, borderRadius: 12, boxSizing: "border-box", color: tokens.colors.text, minHeight: "100vh", padding: "12px 14px 72px", width: "100%" }}>
  <SettingsContext.Provider value={{ settings, setSettings }}>
    {stale ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "6px 9px" }}><FaClock />{text.stale}</div> : null}
    {feedback ? <Notice value={feedback} dismiss={() => setFeedback(null)} /> : null}

    <Focusable flow-children="row" style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 8, display: "grid", gap: 4, gridTemplateColumns: "repeat(4,minmax(0,1fr))", marginBottom: 12, padding: 4 }}>
      {([
        ["board", text.boardSetup, <FaSlidersH />],
        ["monitor", text.monitoring, <FaChartLine />],
        ["memory", text.memoryAndVideo, <FaMemory />],
        ["settings", text.settingsTab, <FaCog />],
      ] as [PanelTab, string, ReactNode][]).map(([tab, label, tabIcon]) => {
        const active = activeTab === tab;
        return <PadButton key={tab} onActivate={() => setActiveTab(tab)} style={{ alignItems: "center", background: active ? accent.focus_soft : "transparent", border: active ? `1px solid ${accent.focus}` : "1px solid transparent", color: active ? accent.focus : tokens.colors.subtle, display: "flex", flexDirection: "column", fontSize: 9, fontWeight: 650, gap: 3, height: 44, justifyContent: "center", padding: "4px 2px", textAlign: "center", width: "100%" }}>
          {tabIcon}<span style={{ lineHeight: 1.1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{label}</span>
        </PadButton>;
      })}
    </Focusable>

    {activeTab === "monitor" ? <MonitorTab state={state} /> : null}
    {activeTab === "memory" ? <MemoryTab state={state} busy={busy} execute={execute} /> : null}
    {activeTab === "settings" ? <SettingsTab settings={settings} setSettings={setSettings} state={state} busy={busy} execute={execute} /> : null}
    {activeTab === "board" ? <>
    <GameProfileCard state={state} busy={busy} />
    <SubNav<BoardSection> value={boardSection} onChange={setBoardSection} items={[
      { key: "gpu", label: "GPU", icon: <FaMicrochip />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "cu", label: text.compute, icon: <FaTh />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "cpu", label: "CPU", icon: <FaBolt />, color: accent.focus, colorSoft: accent.focus_soft },
      { key: "fan", label: text.fan, icon: <FaFan />, color: accent.focus, colorSoft: accent.focus_soft },
    ]} />

    {busy && boardSection !== "cpu" ? <div style={{ alignItems: "center", background: accent.focus_soft, border: `1px solid ${accent.focus}`, borderRadius: 7, color: accent.focus, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "7px 9px" }}><FaClock />{text.operationInProgress}</div> : null}

    {boardSection === "gpu" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="gpu" title="GPU" trailing={governorName ? <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{governorName}</span> : undefined} />
    {!loaded ? <div style={{ color: tokens.colors.subtle, fontSize: 10, marginBottom: 6 }}>{text.loadingGpu}</div> : <>
    {!gpuReady ? <div style={{ color: state.gpu_governor === "conflict" ? tokens.colors.red : tokens.colors.amber, fontSize: 9, marginBottom: 6 }}>{state.gpu_governor === "conflict" ? text.governorConflict : text.governorMissing}</div> : null}
    <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: `repeat(${activeGpuProfiles.length || 1},minmax(0,1fr))`, marginBottom: 6 }}>
      {activeGpuProfiles.map((profile) => { const current = state.gpu_range?.[0] === profile.min && state.gpu_range?.[1] === profile.max && (state.gpu_governor !== "cyan" || state.gpu_performance_enabled === false); const allowed = Boolean(state.gpu_allowed_range && state.gpu_allowed_range[0] <= profile.min && profile.max <= state.gpu_allowed_range[1]); return <PadButton key={profile.key} disabled={busy || !gpuReady || !allowed} preferredFocus={profile.key === (state.gpu_governor === "oberon" ? "oberon-1850" : "balanced")} onActivate={() => { void execute(`GPU · ${profile.name}`, () => applyGpuProfile(profile.key), "gpu"); }} style={{ alignItems: "center", background: current ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, display: "flex", flexDirection: "column", gap: 2, height: 60, justifyContent: "center", minWidth: 0, padding: "6px 6px", textAlign: "center", width: "100%" }}><span style={{ color: current ? accent.focus : tokens.colors.text, fontSize: 11, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{profile.name}</span><span style={{ color: current ? accent.focus : tokens.colors.subtle, fontSize: 9, lineHeight: 1.3 }}>{profile.min}–{profile.max}<br />MHz{current ? ` · ${text.current}` : ""}</span></PadButton>; })}
    </Focusable>
    {points.length ? <><PadButton onActivate={() => setHighOpen(!highOpen)} disabled={busy || !gpuReady} style={{ alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }}><span>{text.more}</span><span style={{ color: accent.focus }}>{highOpen ? "▴" : "▾"}</span></PadButton>{highOpen ? <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", padding: 6 }}>{points.map((point, index) => { const current = point.frequency === liveHighPoint?.frequency; const allowed = Boolean(state.gpu_allowed_range && point.frequency <= state.gpu_allowed_range[1]); return <PadButton key={point.frequency} disabled={busy || !gpuReady || !allowed} preferredFocus={current || (!liveHighPoint && index === 0)} onActivate={() => { if (!current) void execute(`GPU · ${governorName || text.advanced}`, () => applyGpuSafePoint(point.frequency), "gpu"); }} style={{ background: current ? accent.focus_soft : tokens.colors.panel_alt, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, color: current ? accent.focus : tokens.colors.text, fontSize: 10, height: 34, padding: 4, textAlign: "center", width: "100%" }}>{point.frequency} MHz · {point.voltage} mV{current ? ` · ${text.current}` : ""}</PadButton>; })}</Focusable> : null}</> : null}
    <VoltageLab state={state} busy={busy} execute={execute} />
    <GovernorServiceRow state={state} busy={busy} execute={execute} />
    </>}
    </section> : null}

    {boardSection === "cu" ? <section style={{ marginBottom: 12 }}><SectionTitle kind="cu" title={text.compute} trailing={<b style={{ color: accent.focus, fontSize: 11 }}>{draftCUs}/40 {text.target}</b>} />
      {state.cu_snapshot_warning ? <div style={{ color: tokens.colors.amber, fontSize: 10, marginBottom: 6 }}>{text.snapshotWarning}</div> : null}
      {cuConflict ? <div style={{ background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, fontSize: 10, marginBottom: 6, padding: 6 }}>{text.external}<div style={{ marginTop: 5 }}><ActionRow><Action label={text.restore} disabled={busy} onActivate={() => { dirty.current.cu = false; setCuConflict(false); setCuDraft(liveMasks); }} /><Action label={text.keep} disabled={busy} onActivate={() => setCuConflict(false)} /></ActionRow></div></div> : null}
      {topology ? <CuMatrix live={liveMasks} driver={driverMasks} draft={cuDraft} disabled={busy || !state.cu_backend_ready} change={(masks) => { dirty.current.cu = true; setCuConflict(false); setCuDraft(masks); }} minimum={() => setFeedback(text.safeCuMinimum)} /> : <div style={{ color: loaded ? tokens.colors.amber : tokens.colors.subtle, fontSize: 10, marginBottom: 6 }}>{loaded ? text.topologyUnavailable : text.loadingTopology}</div>}
      <div style={{ minHeight: 78, width: "100%" }}>
        <ActionRow marginBottom={6}><Action label={text.applyChanges} primary disabled={busy || !topology || !state.cu_backend_ready || sameMasks(cuDraft, liveMasks)} onActivate={() => void execute("BC250 CU", () => applyCuTable(cuDraft), "cu")} /><Action label={text.save} disabled={busy || !topology || !state.cu_backend_ready} onActivate={() => void execute("BC250 CU", () => saveCuTable(cuDraft), "cu")} /></ActionRow>
        <ActionRow><Action label={text.install} disabled={busy || Boolean(state.cu_service_installed) || !validMasks(state.cu_saved_masks ?? undefined)} onActivate={() => void execute("BC250 CU", installCuService, "cu")} /><Action label={text.remove} danger disabled={busy || !state.cu_service_installed} onActivate={() => showModal(<ConfirmModal strTitle={text.remove} strDescription={text.liveRoutingUnchanged} strOKButtonText={text.remove} bDestructiveWarning onOK={() => void execute("BC250 CU", removeCuService, "cu")} />)} /></ActionRow>
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
          return <PadButton key={preset.key} disabled={busy || !cpuReady} onActivate={() => { setCpuFrequency(preset.frequency); setCpuVid(preset.vid); setCpuManual(false); dirty.current.cpu = true; }} style={{ alignItems: "center", background: current ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${current ? accent.focus : tokens.colors.border}`, display: "flex", flexDirection: "column", gap: 2, height: 52, justifyContent: "center", minWidth: 0, padding: "6px 6px", textAlign: "center", width: "100%" }}>
            <span style={{ color: current ? accent.focus : tokens.colors.text, fontSize: 11, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{preset.name}</span>
            <span style={{ color: current ? accent.focus : tokens.colors.subtle, fontSize: 9 }}>{preset.frequency} MHz</span>
          </PadButton>;
        })}
      </Focusable> : null}
      {detectedCpu?.ready ? <div style={{ alignItems: "center", background: tokens.colors.green_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.cpuDetected}</span><b style={{ color: tokens.colors.green }}>{detectedCpuSummary}</b></div> : null}
      <div style={{ borderTop: `1px solid ${tokens.colors.border_soft}`, paddingTop: 7 }}>
        <CompactSlider label={text.cpuFrequency} value={cpuFrequency} suffix=" MHz" min={cpuMin} max={cpuMax} step={cpuStep} disabled={busy || !cpuReady} onChange={(value) => { setCpuFrequency(Math.max(cpuMin, Math.min(cpuMax, Math.round(value / cpuStep) * cpuStep))); dirty.current.cpu = true; }} />
        <CompactSlider label={text.cpuVoltage} value={cpuVid} suffix=" mV" min={vidMin} max={vidMax} step={vidStep} disabled={busy || !cpuReady || cpuManual} onChange={(value) => { setCpuVid(Math.max(vidMin, Math.min(vidMax, Math.round(value / 5) * 5))); dirty.current.cpu = true; }} />
        {!cpuManual && cpuVid >= vidMax - 25 ? <div style={{ color: tokens.colors.amber, fontSize: 8, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuVidCeiling}</div> : null}
        <div title={manualScaleDescription} style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, fontSize: 11, marginBottom: 4, overflow: "hidden" }}><ToggleField label={text.cpuManual} layout="inline" bottomSeparator="none" highlightOnFocus checked={cpuManual} disabled={busy || !manualReady} onChange={(checked: boolean) => { setCpuManual(checked); if (checked && detectedCpu) { setCpuScale(activeCpu?.frequency === detectedCpu.frequency ? (activeCpu.scale ?? detectedCpu.scale) : detectedCpu.scale); } dirty.current.cpu = true; }} /></div>
        {cpuManual && detectedCpu && !manualFrequencyReady ? <div style={{ color: tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuManualHelp} · {detectedCpu.frequency} MHz</div> : null}
        <CompactSlider label={text.cpuScale} value={cpuScale} suffix="" min={scaleMin} max={scaleMax} step={1} disabled={busy || !cpuManual || !manualFrequencyReady} onChange={(value) => { setCpuScale(Math.max(-50, Math.min(0, Math.round(value)))); dirty.current.cpu = true; }} />
        <div style={{ color: tokens.colors.disabled_text, display: "flex", fontSize: 9, justifyContent: "space-between", margin: "0 2px 7px" }}><span>{cpuManual ? `${text.cpuScale}: ${scaleMin}…${scaleMax}` : `${text.voltageHint} · ${vidMin}–${vidMax} mV`}</span><span>{cpuManual ? `~${selectedEstimatedVid ?? "—"} mV` : `${text.safeRange}: ${cpuMin}–${cpuMax} MHz`}</span></div>
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
// from the same amdgpu counter the desktop's Performance page reads. Turning
// async compute on or off needs a new session, so that stays on the desktop.
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
  const choice = (value: string | null, current: string | null, label: string, pick: () => void, key: string) => {
    const selected = value === current;
    return <PadButton key={key} disabled={working} onActivate={pick} style={{ background: selected ? accent.focus_soft : tokens.colors.panel_raised, border: `1px solid ${selected ? accent.focus : tokens.colors.border}`, color: selected ? accent.focus : tokens.colors.text, fontSize: 9, fontWeight: 650, height: 30, overflow: "hidden", padding: "2px 4px", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "100%" }}>{label}</PadButton>;
  };
  return <section style={{ background: tokens.colors.panel_alt, border: `1px solid ${active ? accent.focus : tokens.colors.border}`, borderRadius: 8, marginBottom: 10, padding: "8px 9px" }}>
    <SectionTitle kind="game" title={text.perGameProfiles} trailing={active ? <span style={{ color: accent.focus, fontSize: 9, fontWeight: 700 }}>{text.gameProfileActive}</span> : undefined} />
    <div style={{ fontSize: 11, overflow: "hidden" }}><ToggleField label={text.applyAutomatically} layout="inline" bottomSeparator="none" highlightOnFocus checked={enabled} disabled={working} onChange={toggle} /></div>
    {!game ? <div style={{ color: tokens.colors.subtle, fontSize: 10, lineHeight: 1.4, margin: "4px 2px 6px" }}>{text.gameNotRunning}</div> : <>
      <div style={{ margin: "4px 2px 6px" }}>
        <div style={{ color: tokens.colors.text, fontSize: 12, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{game.name}</div>
        <div style={{ color: saved ? tokens.colors.muted : tokens.colors.subtle, fontSize: 9, marginTop: 2 }}>{saved ? summary(saved) : text.gameNoProfile}</div>
      </div>
      {!editing ? <ActionRow marginBottom={6}>
        <Action label={saved ? text.editProfile : text.assignProfile} primary={!saved} disabled={working || busy} onActivate={beginEdit} />
        {saved ? <Action label={text.removeGame} danger disabled={working} onActivate={() => remove(saved.app_id)} /> : null}
      </ActionRow> : <div style={{ borderTop: `1px solid ${tokens.colors.border_soft}`, paddingTop: 6 }}>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 4px" }}>GPU</div>
        <Focusable flow-children="grid" style={{ display: "grid", gap: 4, gridTemplateColumns: `repeat(${Math.min(4, gpuProfiles.length + 1)},minmax(0,1fr))`, marginBottom: 6 }}>
          {choice(null, draftGpu, text.unchanged, () => setDraftGpu(null), "gpu-none")}
          {gpuProfiles.map((profile) => choice(profile.key, draftGpu, profile.name, () => setDraftGpu(profile.key), `gpu-${profile.key}`))}
        </Focusable>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "0 2px 4px" }}>{text.fans}</div>
        <Focusable flow-children="grid" style={{ display: "grid", gap: 4, gridTemplateColumns: "repeat(3,minmax(0,1fr))", marginBottom: 6 }}>
          {choice(null, draftFan, text.unchanged, () => setDraftFan(null), "fan-none")}
          {["quiet", "balanced", "boost", "automatic"].map((key) => choice(key, draftFan, presetLabel(key, fanPresets), () => setDraftFan(key), `fan-${key}`))}
        </Focusable>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, lineHeight: 1.35, margin: "0 2px 6px" }}>{text.gameCpuNote}</div>
        <ActionRow marginBottom={6}>
          <Action label={text.gameProfileSave} primary disabled={working || (!draftGpu && !draftFan)} onActivate={save} />
          <Action label={text.cancel} disabled={working} onActivate={() => setEditing(false)} />
        </ActionRow>
      </div>}
    </>}
    <PadButton onActivate={() => setListOpen(!listOpen)} style={{ alignItems: "center", display: "flex", fontSize: 10, height: 30, justifyContent: "space-between", padding: "4px 8px", width: "100%" }}>
      <span>{text.savedGames} · {games.length}</span><span style={{ color: accent.focus }}>{listOpen ? "▴" : "▾"}</span>
    </PadButton>
    {listOpen ? <Focusable flow-children="down" style={{ marginTop: 5 }}>
      {!games.length ? <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "2px 2px 0" }}>{text.gamesEmpty}</div> : games.map((entry) => <Focusable key={entry.app_id} flow-children="row" style={{ alignItems: "center", borderTop: `1px solid ${tokens.colors.border_soft}`, display: "grid", gap: 6, gridTemplateColumns: "1fr 72px", padding: "5px 0" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name || appName(Number(entry.app_id))}</div>
          <div style={{ color: tokens.colors.subtle, fontSize: 8, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{summary(entry)}</div>
        </div>
        <Action label={text.removeGame} danger disabled={working} onActivate={() => remove(entry.app_id)} />
      </Focusable>)}
    </Focusable> : null}
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
      <SectionTitle kind="gpu" title="GPU" />
      <HighPointsSwitch state={state} busy={busy} execute={execute} />
    </section>

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
