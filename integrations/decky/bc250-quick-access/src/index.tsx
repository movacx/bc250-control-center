import {
  Button,
  ConfirmModal,
  Focusable,
  NavEntryPositionPreferences,
  showModal,
  SliderField,
  staticClasses,
  ToggleField,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import {
  type CSSProperties,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  FaBolt,
  FaClock,
  FaExclamationTriangle,
  FaFan,
  FaMicrochip,
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
};

type Result = {
  ok?: boolean;
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
};
type Status = Result;
type DraftKind = "cu" | "fan" | "gpu" | "cpu" | "none";

const getStatus = callable<[], Status>("status");
const getCpuTelemetry = callable<[], Result>("cpu_telemetry");
const applyGpuProfile = callable<[profile: string], Result>("apply_gpu_profile");
const applyGpuSafePoint = callable<[frequency: number], Result>("apply_gpu_safe_point");
const applyCuTable = callable<[masks: number[]], Result>("apply_cu_table");
const saveCuTable = callable<[masks: number[]], Result>("save_cu_table");
const installCuService = callable<[], Result>("install_cu_service");
const removeCuService = callable<[], Result>("remove_cu_service");
const applyFanChannel = callable<[channel: number, target: number | "automatic"], Result>("apply_fan_channel");
const applyCpuTuning = callable<[frequency: number, vid: number], Result>("apply_cpu_tuning");
const applyCpuScale = callable<[frequency: number, scale: number], Result>("apply_cpu_scale");
const installCpuService = callable<[], Result>("install_cpu_service");
const removeCpuService = callable<[], Result>("remove_cpu_service");

const fanChannels = [2, 3, 4, 5] as const;
const cuRows = ["SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1"] as const;

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
function masksFromTarget(target: number, targets?: number[]) {
  const masks = [7, 7, 7, 7];
  // 12 WGPs are always on; the ladder decides how many more there can be.
  const lowest = targets && targets.length ? Math.min(...targets) : 24;
  const highest = targets && targets.length ? Math.max(...targets) : 40;
  let extra = Math.max(0, Math.min((highest - lowest) / 2, target / 2 - lowest / 2));
  for (let wgp = 3; wgp < 5 && extra > 0; wgp += 1) for (let row = 0; row < 4 && extra > 0; row += 1) { masks[row] |= 1 << wgp; extra -= 1; }
  return masks;
}
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

function SectionTitle({ kind, title, trailing }: { kind: "gpu" | "cu" | "cpu" | "fan"; title: string; trailing?: ReactNode }) {
  const data = {
    gpu: [<FaMicrochip />, tokens.colors.purple, tokens.colors.purple_soft],
    cu: [<FaTh />, tokens.colors.orange, tokens.colors.orange_soft],
    cpu: [<FaBolt />, tokens.colors.blue, tokens.colors.blue_soft],
    fan: [<FaFan />, tokens.colors.cyan, tokens.colors.cyan_soft],
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

function Action({ label, disabled, primary, danger, onActivate }: { label: string; disabled: boolean; primary?: boolean; danger?: boolean; onActivate: () => void }) {
  return <PadButton disabled={disabled} onActivate={onActivate} style={{
    background: danger ? tokens.colors.red_soft : primary ? tokens.colors.orange : tokens.colors.panel_raised,
    border: `1px solid ${danger ? tokens.colors.red_soft : primary ? tokens.colors.orange : tokens.colors.border}`,
    color: danger ? tokens.colors.red : primary ? tokens.colors.selection : tokens.colors.text,
    alignItems: "center", boxSizing: "border-box", display: "flex", flex: 1, fontSize: 10, fontWeight: primary ? 700 : 600, height: 36, justifyContent: "center", lineHeight: 1.15, minWidth: 0, padding: "4px 7px", textAlign: "center", whiteSpace: "normal", width: "100%",
  }}>{label}</PadButton>;
}

function ActionRow({ children, marginBottom = 0 }: { children: ReactNode; marginBottom?: number }) {
  return <Focusable flow-children="right" style={{ alignItems: "stretch", display: "flex", gap: 6, height: 36, marginBottom, minHeight: 36, width: "100%" }}>{children}</Focusable>;
}

function CompactSlider({ label, value, suffix, min, max, step, disabled, onChange }: {
  label: string; value: number; suffix: string; min: number; max: number; step: number; disabled: boolean; onChange: (value: number) => void;
}) {
  return <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginBottom: 6, padding: "7px 8px 3px" }}>
    <div style={{ alignItems: "baseline", display: "flex", justifyContent: "space-between", marginBottom: 1 }}><span style={{ color: tokens.colors.subtle, fontSize: 10 }}>{label}</span><b style={{ color: tokens.colors.text, fontSize: 12 }}>{value}{suffix}</b></div>
    <SliderField label="" layout="below" childrenContainerWidth="max" bottomSeparator="none" highlightOnFocus value={value} min={min} max={max} step={step} minimumDpadGranularity={step} validValues="steps" showValue={false} disabled={disabled} onChange={onChange} />
  </div>;
}

function CpuMetric({ label, value }: { label: string; value: string }) {
  return <div style={{ minWidth: 0, padding: "7px 8px" }}>
    <div style={{ color: tokens.colors.subtle, fontSize: 8 }}>{label}</div>
    <div style={{ fontSize: 12, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
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

function Content() {
  const [state, setState] = useState<Status>({});
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
  const dirty = useRef({ cu: false, fan: false, gpu: false, cpu: false });
  const selectionRef = useRef({ fan: 2 });
  useEffect(() => { selectionRef.current.fan = fanChannel; }, [fanChannel]);

  const refresh = useCallback(async (reason: "initial" | "poll" | "after" = "initial") => {
    if (refreshing.current || (reason === "poll" && busyRef.current)) return;
    refreshing.current = true;
    try {
      const result = await getStatus();
      if (result.ok === false) { setLoaded(true); setStale(true); if (reason === "initial") setFeedback(result.error ?? text.error); return; }
      setState(result); setLoaded(true); setStale(false);
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
  const detectedCpuSummary = detectedCpu
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
    onOK={() => void execute("BC250 CPU", mode === "detect" ? (cpuManual ? () => applyCpuScale(cpuFrequency, cpuScale) : () => applyCpuTuning(cpuFrequency, cpuVid)) : installCpuService, "cpu", mode === "detect" ? { target: cpuFrequency, manual: cpuManual } : undefined)}
  />);

  return <Focusable flow-children="down" style={{ background: tokens.colors.panel, border: `1px solid ${tokens.colors.border}`, borderRadius: 12, boxSizing: "border-box", color: tokens.colors.text, padding: "12px 14px 72px", width: "100%" }}>
    {stale ? <div style={{ alignItems: "center", background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, display: "flex", fontSize: 10, gap: 6, marginBottom: 10, padding: "6px 9px" }}><FaClock />{text.stale}</div> : null}
    {feedback ? <Notice value={feedback} dismiss={() => setFeedback(null)} /> : null}

    <section style={{ marginBottom: 12 }}><SectionTitle kind="gpu" title="GPU" trailing={governorName ? <span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{governorName}</span> : undefined} />
    {!gpuReady && loaded ? <div style={{ color: state.gpu_governor === "conflict" ? tokens.colors.red : tokens.colors.amber, fontSize: 9, marginBottom: 6 }}>{state.gpu_governor === "conflict" ? text.governorConflict : text.governorMissing}</div> : null}
    <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr", marginBottom: 6 }}>
      <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, boxSizing: "border-box", display: "flex", flexDirection: "column", height: 48, justifyContent: "center", padding: "5px 9px", width: "100%" }}><span style={{ color: tokens.colors.subtle, fontSize: 9, fontWeight: 650 }}>{text.gpuLive}</span><b style={{ color: tokens.colors.text, fontSize: 12, lineHeight: 1.25 }}>{state.gpu_core_mhz ?? "—"} MHz</b><span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.gpuVoltage} · {state.gpu_voltage_mv ?? "—"} mV</span></div>
      {activeGpuProfiles.map((profile) => { const current = state.gpu_range?.[0] === profile.min && state.gpu_range?.[1] === profile.max && (state.gpu_governor !== "cyan" || state.gpu_performance_enabled === false); const allowed = Boolean(state.gpu_allowed_range && state.gpu_allowed_range[0] <= profile.min && profile.max <= state.gpu_allowed_range[1]); return <PadButton key={profile.key} disabled={busy || !gpuReady || !allowed} preferredFocus={profile.key === (state.gpu_governor === "oberon" ? "oberon-1850" : "balanced")} onActivate={() => { void execute(`GPU · ${profile.name}`, () => applyGpuProfile(profile.key), "gpu"); }} style={{ alignItems: "flex-start", background: current ? tokens.colors.orange_soft : tokens.colors.panel_raised, border: `1px solid ${current ? tokens.colors.orange : tokens.colors.border}`, display: "flex", flexDirection: "column", height: 48, justifyContent: "center", padding: "6px 9px", textAlign: "left", width: "100%" }}><span style={{ color: current ? tokens.colors.orange : tokens.colors.text, fontSize: 12, fontWeight: 650 }}>{profile.name}</span><span style={{ color: current ? tokens.colors.orange : tokens.colors.subtle, fontSize: 10 }}>{profile.min}–{profile.max} MHz{current ? ` · ${text.current}` : ""}</span></PadButton>; })}
    </Focusable>
    {points.length ? <><PadButton onActivate={() => setHighOpen(!highOpen)} disabled={busy || !gpuReady} style={{ alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }}><span>{text.more}</span><span style={{ color: tokens.colors.orange }}>{highOpen ? "▴" : "▾"}</span></PadButton>{highOpen ? <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", padding: 6 }}>{points.map((point, index) => { const current = point.frequency === liveHighPoint?.frequency; const allowed = Boolean(state.gpu_allowed_range && point.frequency <= state.gpu_allowed_range[1]); return <PadButton key={point.frequency} disabled={busy || !gpuReady || !allowed} preferredFocus={current || (!liveHighPoint && index === 0)} onActivate={() => { if (!current) void execute(`GPU · ${governorName || text.advanced}`, () => applyGpuSafePoint(point.frequency), "gpu"); }} style={{ background: current ? tokens.colors.orange_soft : tokens.colors.panel_alt, border: `1px solid ${current ? tokens.colors.orange : tokens.colors.border}`, color: current ? tokens.colors.orange : tokens.colors.text, fontSize: 10, height: 34, padding: 4, textAlign: "center", width: "100%" }}>{point.frequency} MHz · {point.voltage} mV{current ? ` · ${text.current}` : ""}</PadButton>; })}</Focusable> : null}</> : null}
    </section>

    <section style={{ marginBottom: 12 }}><SectionTitle kind="cu" title={text.compute} trailing={<b style={{ color: tokens.colors.orange, fontSize: 11 }}>{draftCUs}/40 {text.target}</b>} />
      {state.cu_snapshot_warning ? <div style={{ color: tokens.colors.amber, fontSize: 10, marginBottom: 6 }}>{text.snapshotWarning}</div> : null}
      {cuConflict ? <div style={{ background: tokens.colors.amber_soft, border: `1px solid ${tokens.colors.amber}`, borderRadius: 6, color: tokens.colors.amber, fontSize: 10, marginBottom: 6, padding: 6 }}>{text.external}<div style={{ marginTop: 5 }}><ActionRow><Action label={text.restore} disabled={busy} onActivate={() => { dirty.current.cu = false; setCuConflict(false); setCuDraft(liveMasks); }} /><Action label={text.keep} disabled={busy} onActivate={() => setCuConflict(false)} /></ActionRow></div></div> : null}
      {topology ? <CuMatrix live={liveMasks} driver={driverMasks} draft={cuDraft} disabled={busy || !state.cu_backend_ready} change={(masks) => { dirty.current.cu = true; setCuConflict(false); setCuDraft(masks); }} minimum={() => setFeedback(text.safeCuMinimum)} /> : <div style={{ color: loaded ? tokens.colors.amber : tokens.colors.subtle, fontSize: 10, marginBottom: 6 }}>{loaded ? text.topologyUnavailable : text.loadingTopology}</div>}
      <div style={{ minHeight: 78, width: "100%" }}>
        <ActionRow marginBottom={6}><Action label={text.applyChanges} primary disabled={busy || !topology || !state.cu_backend_ready || sameMasks(cuDraft, liveMasks)} onActivate={() => void execute("BC250 CU", () => applyCuTable(cuDraft), "cu")} /><Action label={text.save} disabled={busy || !topology || !state.cu_backend_ready} onActivate={() => void execute("BC250 CU", () => saveCuTable(cuDraft), "cu")} /></ActionRow>
        <ActionRow><Action label={text.install} disabled={busy || Boolean(state.cu_service_installed) || !validMasks(state.cu_saved_masks ?? undefined)} onActivate={() => void execute("BC250 CU", installCuService, "cu")} /><Action label={text.remove} danger disabled={busy || !state.cu_service_installed} onActivate={() => showModal(<ConfirmModal strTitle={text.remove} strDescription={text.liveRoutingUnchanged} strOKButtonText={text.remove} bDestructiveWarning onOK={() => void execute("BC250 CU", removeCuService, "cu")} />)} /></ActionRow>
      </div>
    </section>

    <section style={{ marginBottom: 12 }}><SectionTitle kind="cpu" title="CPU" />
      {cpuError ? <div style={{ background: tokens.colors.red_soft, border: `1px solid ${tokens.colors.red}`, borderRadius: 6, color: tokens.colors.red, fontSize: 9, lineHeight: 1.35, marginBottom: 7, overflowWrap: "anywhere", padding: "6px 8px" }}>{localizedErrorSummary(cpuError)}</div> : null}
      {cpuOperation ? <div role="status" aria-live="polite" style={{ background: tokens.colors.blue_soft, border: `1px solid ${tokens.colors.blue}`, borderRadius: 7, marginBottom: 7, padding: "8px 9px" }}>
        <div style={{ alignItems: "center", display: "flex", gap: 7 }}><span style={{ background: tokens.colors.blue, borderRadius: "50%", boxShadow: `0 0 0 3px ${tokens.colors.blue_soft}`, height: 7, width: 7 }} /><b style={{ color: tokens.colors.blue, flex: 1, fontSize: 11 }}>{text.cpuApplying}</b><span style={{ color: tokens.colors.subtle, fontSize: 9 }}>{text.elapsed}: {cpuElapsed}s</span></div>
        <div style={{ color: tokens.colors.subtle, fontSize: 9, margin: "4px 0 7px 14px" }}>{text.cpuPleaseWait}</div>
        <div style={{ display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr" }}><div style={{ background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }}><span style={{ color: tokens.colors.muted, display: "block", fontSize: 8 }}>{text.cpuLiveClock}</span><b style={{ fontSize: 12 }}>{state.cpu_frequency_mhz ?? "—"} MHz</b></div><div style={{ background: tokens.colors.panel_alt, borderRadius: 5, padding: "5px 7px" }}><span style={{ color: tokens.colors.muted, display: "block", fontSize: 8 }}>{text.cpuTarget}</span><b style={{ fontSize: 12 }}>{cpuOperation.target} MHz</b></div></div>
      </div> : null}
      <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border}`, borderRadius: 6, display: "grid", gridTemplateColumns: "1fr 1fr", marginBottom: 6, overflow: "hidden" }}>
        <CpuMetric label="CLOCK" value={`${state.cpu_frequency_mhz ?? "—"} MHz`} />
        <div style={{ borderLeft: `1px solid ${tokens.colors.border}` }}><CpuMetric label="TCTL" value={`${state.cpu_temperature_c?.toFixed(1) ?? "—"} °C`} /></div>
        <div style={{ borderTop: `1px solid ${tokens.colors.border}` }}><CpuMetric label="VID EST." value={activeCpu ? `${activeCpu.estimated_vid} mV` : "—"} /></div>
        <div style={{ borderLeft: `1px solid ${tokens.colors.border}`, borderTop: `1px solid ${tokens.colors.border}` }}><CpuMetric label="SCALE" value={activeCpu ? String(activeCpu.scale) : "—"} /></div>
      </div>
      {detectedCpu?.ready ? <div style={{ alignItems: "center", background: tokens.colors.green_soft, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, display: "flex", fontSize: 9, gap: 6, justifyContent: "space-between", marginBottom: 6, padding: "6px 8px" }}><span style={{ color: tokens.colors.subtle }}>{text.cpuDetected}</span><b style={{ color: tokens.colors.green }}>{detectedCpuSummary}</b></div> : null}
      <div style={{ color: !loaded || cpuReady || state.cpu_tuning_source === "detector-required" ? tokens.colors.subtle : tokens.colors.red, fontSize: 9, margin: "0 2px 7px" }}>{!loaded ? text.loadingCpu : cpuReady ? `${text.cpuTrial}: ${cpuLimit}°C · ${text.cpuDetectHelp}` : (state.cpu_tuning_source === "stress-unavailable" ? text.stressMissing : (state.cpu_tuning_source === "detector-required" ? text.cpuNeedsDetection : (state.cpu_tuning_source === "helper-unavailable" ? text.cpuHelperUnavailable : text.cpuStatusUnavailable)))}</div>
      {loaded && !cpuReady && state.cpu_tuning_error && state.cpu_tuning_source !== "detector-required" ? <div style={{ color: tokens.colors.muted, fontSize: 8, margin: "-3px 2px 7px", overflowWrap: "anywhere" }}>{localizedErrorSummary(state.cpu_tuning_error)}</div> : null}
      <div style={{ borderTop: `1px solid ${tokens.colors.border_soft}`, paddingTop: 7 }}>
        <CompactSlider label={text.cpuFrequency} value={cpuFrequency} suffix=" MHz" min={cpuMin} max={cpuMax} step={cpuStep} disabled={busy || !cpuReady} onChange={(value) => { setCpuFrequency(Math.max(cpuMin, Math.min(cpuMax, Math.round(value / cpuStep) * cpuStep))); dirty.current.cpu = true; }} />
        <CompactSlider label={text.cpuVoltage} value={cpuVid} suffix=" mV" min={vidMin} max={vidMax} step={vidStep} disabled={busy || !cpuReady || cpuManual} onChange={(value) => { setCpuVid(Math.max(vidMin, Math.min(vidMax, Math.round(value / 5) * 5))); dirty.current.cpu = true; }} />
        {!cpuManual && cpuVid >= vidMax - 25 ? <div style={{ color: tokens.colors.amber, fontSize: 8, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuVidCeiling}</div> : null}
        <div style={{ background: tokens.colors.panel_alt, border: `1px solid ${tokens.colors.border_soft}`, borderRadius: 6, marginBottom: 6, overflow: "hidden" }}><ToggleField label={text.cpuManual} description={manualScaleDescription} layout="inline" bottomSeparator="none" highlightOnFocus checked={cpuManual} disabled={busy || !manualReady} onChange={(checked: boolean) => { setCpuManual(checked); if (checked && detectedCpu) { setCpuScale(activeCpu?.frequency === detectedCpu.frequency ? (activeCpu.scale ?? detectedCpu.scale) : detectedCpu.scale); } dirty.current.cpu = true; }} /></div>
        {cpuManual && detectedCpu && !manualFrequencyReady ? <div style={{ color: tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "-2px 2px 7px" }}>{text.cpuManualHelp} · {detectedCpu.frequency} MHz</div> : null}
        <CompactSlider label={text.cpuScale} value={cpuScale} suffix="" min={scaleMin} max={scaleMax} step={1} disabled={busy || !cpuManual || !manualFrequencyReady} onChange={(value) => { setCpuScale(Math.max(-50, Math.min(0, Math.round(value)))); dirty.current.cpu = true; }} />
        <div style={{ color: tokens.colors.disabled_text, display: "flex", fontSize: 9, justifyContent: "space-between", margin: "0 2px 7px" }}><span>{cpuManual ? `${text.cpuScale}: ${scaleMin}…${scaleMax}` : `${text.voltageHint} · ${vidMin}–${vidMax} mV`}</span><span>{cpuManual ? `~${selectedEstimatedVid ?? "—"} mV` : `${text.safeRange}: ${cpuMin}–${cpuMax} MHz`}</span></div>
        <ActionRow><Action label={cpuManual ? text.cpuApplyManual : text.cpuApplyAuto} primary disabled={busy || !cpuReady || (cpuManual && (!manualFrequencyReady || (selectedEstimatedVid ?? 0) > vidMax))} onActivate={() => confirmCpu("detect")} /></ActionRow>
      </div>
      <div style={{ marginTop: 6, minHeight: 36 }}><ActionRow><Action label={text.install} disabled={busy || !activeMatchesTarget || Boolean(state.cpu_service_enabled)} onActivate={() => confirmCpu("install")} /><Action label={text.remove} danger disabled={busy || (!state.cpu_service_installed && !state.cpu_service_enabled)} onActivate={() => showModal(<ConfirmModal strTitle={text.remove} strDescription={text.serviceRemovedBootProfile} strOKButtonText={text.remove} bDestructiveWarning onOK={() => void execute("BC250 CPU", removeCpuService, "cpu")} />)} /></ActionRow></div>
    </section>

    <section style={{ marginBottom: 12 }}><SectionTitle kind="fan" title={text.fan} />
      <PadButton disabled={busy} onActivate={() => setFanOpen(!fanOpen)} style={{ alignItems: "center", display: "flex", fontSize: 11, height: 34, justifyContent: "space-between", marginBottom: 6, padding: "5px 9px", width: "100%" }}><span>{liveFan?.label ?? `PWM ${fanChannel}`} · {fanDetected ? text.detected : text.unavailable}</span><span style={{ color: tokens.colors.cyan }}>{fanOpen ? "▴" : "▾"}</span></PadButton>
      {fanOpen ? <Focusable flow-children="grid" navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD} style={{ display: "grid", gap: 5, gridTemplateColumns: "1fr 1fr", marginBottom: 7 }}>{fanChannels.map((channel) => { const option = state.fan_channel_options?.find((item) => item.channel === channel); const available = detectedFans.includes(channel); return <PadButton key={channel} disabled={busy || !available} preferredFocus={channel === fanChannel} onActivate={() => { selectionRef.current.fan = channel; setFanChannel(channel); setFanOpen(false); dirty.current.fan = false; const percent = option?.percent; if (percent != null) setFanDuty(percent); }} style={{ background: channel === fanChannel ? tokens.colors.cyan_soft : tokens.colors.panel_raised, border: `1px solid ${channel === fanChannel ? tokens.colors.cyan : tokens.colors.border}`, color: channel === fanChannel ? tokens.colors.cyan : tokens.colors.text, fontSize: 10, height: 34, padding: 4, width: "100%" }}>PWM {channel} · {available ? `${option?.percent ?? "—"}%` : text.unavailable}</PadButton>; })}</Focusable> : null}
      {liveFan ? <div style={{ color: liveFan.rpm_observed ? tokens.colors.subtle : tokens.colors.amber, fontSize: 9, lineHeight: 1.3, margin: "0 2px 6px" }}>{liveFan.rpm_observed ? `${text.fanRpmObserved}: ${liveFan.rpm} RPM` : `${text.fanUnverified}. ${fanChannel === 2 ? text.fanWiring : ""}`}</div> : null}
      <SliderField label={text.speed} value={fanDuty} min={fanMin} max={fanMax} step={fanStep} minimumDpadGranularity={fanStep} showValue valueSuffix="%" disabled={busy || !fanDetected} onChange={(value: number) => { dirty.current.fan = true; setFanDuty(Math.max(20, Math.min(100, Math.round(value / 5) * 5))); }} />
      <Focusable flow-children="grid" style={{ display: "grid", gap: 6, gridTemplateColumns: "1fr 1fr", marginTop: 6 }}><Action label={text.apply} primary disabled={busy || !fanDetected} onActivate={() => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, fanDuty), "fan")} /><Action label={text.automatic} disabled={busy || !fanDetected} onActivate={() => void execute(`PWM ${fanChannel}`, () => applyFanChannel(fanChannel, "automatic"), "fan")} /></Focusable>
    </section>

  </Focusable>;
}

export default definePlugin(() => ({
  name: "BC250 Quick Access",
  titleView: <div className={staticClasses.Title}>BC250 Quick Access</div>,
  content: <Content />,
  icon: <FaMicrochip />,
  onDismount() {},
}));
