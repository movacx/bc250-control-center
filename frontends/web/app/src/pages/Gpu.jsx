import { useState } from "react";
import { num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, Fold, Tile, useStored } from "../ui.jsx";
import { ProfileEditor } from "../ui.jsx";

const SAFE_CEILING = 2000; // the factory TOML's last point; past it the rail turns red
const int = (value, fallback) => (Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : fallback);

const Select = ({ label, value, options, onChange }) => (
  <label className="field"><span>{label}</span><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
);

export default function Gpu() {
  const { act, live } = useApp();
  const raw = usePage("gpu");
  const [compat, setCompat] = useState(null);
  const [edited, setEdited] = useStored("gpu-profiles", {});
  const [editing, setEditing] = useState(null);
  const [advanced, setAdvanced] = useState(false);
  if (!raw) return <Card title={t("GPU Governor")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const gpu = live?.metrics?.gpu || {};
  const lowest = int(raw.allowed_min, 500), highest = int(raw.allowed_max, 2000), cur = [int(raw.current_min, lowest), int(raw.current_max, highest)];
  const volts = Object.fromEntries((raw.safe_points || []).map((p) => [Number(p.frequency), p.voltage]));
  const stops = [...new Set([...Object.keys(volts).map(Number).filter((f) => f >= lowest && f <= highest), lowest, highest])].sort((a, b) => a - b);
  const backend = String(raw.governor_backend || ""), cyan = raw.cyan_telemetry || {}, high = raw.high_frequency_points || {};
  const unlocked = !!(high.enabled_frequencies || []).length, running = raw.service_active === "active";
  const profiles = (raw.profiles || []).map((p) => ({ ...p, ...(edited[p.key] || {}) }));
  const opts = compat || { set_method: cyan.set_method || "smu", usage_method: cyan.method || "busy-flag", temp_read: cyan.temp_read || "drm", metrics: cyan.fix_metrics ?? true, frequencies: !!cyan.fix_frequency };
  const busy = pick(gpu.usage_percent, gpu.compute_busy_percent);
  const control = (action, title, level = 1) => act({ action: "gpu.service", level, params: { action }, title });
  return (
    <>
      <div className="mobile-stats"><Tile label={t("Core clock")} value={`${num(gpu.frequency_mhz)} MHz`} /><Tile label={t("GPU load")} value={`${num(busy)} %`} /><Tile label={t("Thermal")} value={`${num(gpu.temperature_c, 1)} °C`} /></div>
      <div className="cols two">
        <div className="stack">
          <Card title={t("Operating profile")} sub={t("One click sets the range. The pencil changes name and frequencies.")}>
            <div className="tiles profiles">{profiles.map((p) => <Tile key={p.key} label={p.label} value={`${p.min} – ${p.max} MHz`} note={`${volts[p.max] ?? "--"} mV`} on={p.min === cur[0] && p.max === cur[1]}
              onClick={() => act({ action: "gpu.profile", level: p.max > SAFE_CEILING ? 2 : 1, params: { min: p.min, max: p.max }, title: p.label, body: `${p.min}–${p.max} MHz` })} onEdit={() => setEditing(p)} />)}</div>
          </Card>
          {backend.startsWith("cyan") && <Fold title={t("Cyan kernel compatibility")}>
            <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))" }}>
              <Select label={t("Governor method")} value={opts.set_method} options={[["smu", "SMU"], ["kernel", "Kernel"]]} onChange={(v) => setCompat({ ...opts, set_method: v })} />
              <Select label={t("Usage reading")} value={opts.usage_method} options={[["busy-flag", "busy-flag"], ["process", "process"], ["kernel", "kernel"]]} onChange={(v) => setCompat({ ...opts, usage_method: v })} />
              <Select label={t("Temperature reading")} value={opts.temp_read} options={[["drm", "DRM"], ["sysfs", "sysfs"]]} onChange={(v) => setCompat({ ...opts, temp_read: v })} /></div>
            <div className="row"><Check checked={opts.metrics} onChange={(v) => setCompat({ ...opts, metrics: v })}>{raw.fix_labels.metrics}</Check>
              <Check checked={opts.frequencies} onChange={(v) => setCompat({ ...opts, frequencies: v })}>{raw.fix_labels.frequency}</Check><span style={{ flex: 1 }} />
              <Btn onClick={() => act({ action: "gpu.compat", level: opts.set_method === "kernel" ? 2 : 1, params: { set_method: opts.set_method, usage_method: opts.usage_method, metrics: opts.metrics, frequencies: opts.frequencies, temp_read: opts.temp_read }, title: t("Cyan kernel compatibility") })}>{t("Apply compatibility")}</Btn></div>
          </Fold>}
          <Btn onClick={() => act({ action: "gpu.save_boot", level: 1, title: t("Save active range for startup") })}>{t("Save for boot")}</Btn>
        </div>
        <div className="stack">
          <div className="tiles t3">
            <Tile label={t("Core clock")} value={`${num(pick(raw.sclk_actual, gpu.frequency_mhz))} MHz`} note={t("Current SCLK state")} />
            <Tile label={t("GPU voltage")} value={`${num(pick(raw.voltaje_actual, gpu.voltage_mv))} mV`} note={t("OD / SMU telemetry")} />
            <Tile label={t("Thermal")} value={`${num(gpu.temperature_c, 1)} °C`} tone={gpu.temperature_c >= 95 ? "bad" : gpu.temperature_c >= 85 ? "warn" : ""} />
            <Tile label={t("GPU load")} value={`${num(busy)} %`} />
            <Tile label={t("Memory clock")} value={`${num(pick(raw.mclk_actual, gpu.memory_frequency_mhz))} MHz`} />
            <Tile label={t("Active range")} value={`${cur[0]}–${cur[1]} MHz`} /></div>
          <Card title={t("Governor service")} sub={t("Start governor runs it now and saves it for startup (enables the service). Stop governor stops it and removes it from startup (disables the service).")} pill={backend || t("Not detected")} tone={running ? "green" : "orange"}>
            <div className="row">
              <Btn wide onClick={() => act({ action: "gpu.status", title: t("View status") })}>{t("View status")}</Btn>
              <Btn wide onClick={() => control("reiniciar", t("Restart service"))}>{t("Restart")}</Btn>
              {running ? <Btn kind="danger" wide onClick={() => control("desactivar", t("Stop governor"), 2)}>{t("Stop governor")}</Btn>
                : <Btn kind="primary" wide onClick={() => control("activar", t("Start governor"))}>{t("Start governor")}</Btn>}</div>
          </Card>
          <Fold title={t("Voltage laboratory")}>
            <div className="row">{[[1, t("Gentle")], [2, t("Moderate")], [3, t("High")]].map(([level, label]) => (
              <Btn key={level} wide onClick={() => act({ action: "gpu.voltage", level: 2, params: { level }, title: t("Apply voltage curve"), body: `+${level * 10} mV ${label}`, warning: t("Stop every game, benchmark, and 3D workload before continuing.") })}>+{level * 10} mV {label}</Btn>))}</div>
            <Btn onClick={() => act({ action: "gpu.voltage", level: 2, params: { level: 0 }, title: t("Restore governor defaults"), warning: t("Stop every game, benchmark, and 3D workload before continuing.") })}>{t("Restore governor defaults")}</Btn>
          </Fold>
          {high.available && <Fold risk title={t("TOML points above 2000 MHz")}>
            <Btn kind="danger" onClick={() => act({ action: "gpu.high_points", level: 2, params: { enable: !unlocked }, title: unlocked ? t("Re-comment the +2000 MHz points") : t("Uncomment +2000 MHz points") })}>
              {unlocked ? t("Re-comment the +2000 MHz points") : t("Uncomment +2000 MHz points")}</Btn>
          </Fold>}
        </div>
      </div>
      <Card title={t("Advanced GPU diagnostics")} action={<Btn kind="link" onClick={() => setAdvanced(!advanced)}>{advanced ? t("Hide") : t("Show")} ›</Btn>}>
        {advanced && <div className="reads">{stops.map((f) => volts[f] != null && <div className="read" key={f}><span>{f} MHz</span><b>{volts[f]} mV</b></div>)}
          <div className="read"><span>{t("Backend")}</span><b>{backend || "--"}</b></div><div className="read"><span>config.toml</span><b>{raw.config_path || "--"}</b></div></div>}
      </Card>
      {editing && <ProfileEditor profile={{ name: editing.label, min: editing.min, max: editing.max }} fields={[["min", t("Minimum frequency"), lowest, highest, "MHz"], ["max", t("Maximum frequency"), lowest, highest, "MHz"]]}
        onClose={() => setEditing(null)} onSave={(p) => { setEdited({ ...edited, [editing.key]: { label: p.name, min: Math.min(p.min, p.max), max: Math.max(p.min, p.max) } }); setEditing(null); }} />}
    </>
  );
}
