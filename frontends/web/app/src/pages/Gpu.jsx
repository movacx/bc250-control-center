import { useEffect, useRef, useState } from "react";
import { num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, Fold, Number_, Tile, useStored } from "../ui.jsx";
import { ProfileEditor } from "../ui.jsx";

const SAFE_CEILING = 2000; // the factory TOML's last point; past it the rail turns red
const int = (value, fallback) => (Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : fallback);

/** Two thumbs on the TOML's points: drag, or tap a mark. Everything snaps to a real point. */
function Rail({ stops, low, high, onChange }) {
  const box = useRef(null);
  const [drag, setDrag] = useState(null);
  const first = stops[0], last = stops[stops.length - 1];
  const labelled = new Map();  // labels that fit: alternate two rows, skip a mark that would sit on the last one
  let before = -1;
  const width = box.current?.clientWidth || 280;
  stops.forEach((f) => { if (before < 0 || ((f - before) / (last - first || 1) * width >= 48 && (last - f) / (last - first || 1) * width >= 36)) { labelled.set(f, labelled.size % 2); before = f; } });
  labelled.set(last, 0);
  const at = (f) => `${((f - first) / (last - first || 1)) * 100}%`;
  const near = (clientX) => {
    const rect = box.current.getBoundingClientRect();
    const f = first + Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * (last - first);
    return stops.reduce((a, b) => (Math.abs(b - f) < Math.abs(a - f) ? b : a));
  };
  const move = (e) => {
    if (!drag) return;
    const f = near(e.clientX);
    if (drag === "low") onChange(Math.min(f, high), high); else onChange(low, Math.max(f, low));
  };
  const key = (which) => (e) => {
    const index = stops.indexOf(which === "low" ? low : high), step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const f = stops[Math.max(0, Math.min(stops.length - 1, index + step))];
    if (which === "low") onChange(Math.min(f, high), high); else onChange(low, Math.max(f, low));
  };
  return (
    <div className="rail" ref={box} onPointerMove={move} onPointerUp={() => setDrag(null)} onPointerCancel={() => setDrag(null)}>
      <div className="track" /><div className="fill" style={{ left: at(low), width: `${((high - low) / (last - first || 1)) * 100}%` }} />
      {stops.map((f, i) => <span key={f}><span className={`tick ${f > SAFE_CEILING ? "hot" : ""}`} style={{ left: at(f) }} />
        {labelled.has(f) && <label className={`${labelled.get(f) ? "lo" : ""} ${f > SAFE_CEILING ? "hot" : ""}`} style={{ left: at(f) }}>{f}</label>}</span>)}
      {[["low", low], ["high", high]].map(([which, value]) => (
        <span key={which} className={`thumb ${which === "high" && value > SAFE_CEILING ? "hot" : ""}`} role="slider" tabIndex={0} aria-label={which === "low" ? t("Minimum frequency") : t("Maximum frequency")}
          aria-valuemin={first} aria-valuemax={last} aria-valuenow={value} aria-valuetext={`${value} MHz`} style={{ left: at(value) }} onKeyDown={key(which)}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag(which); }} />))}
    </div>
  );
}

const Select = ({ label, value, options, onChange }) => (
  <label className="field"><span>{label}</span><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
);

export default function Gpu() {
  const { act, live } = useApp();
  const raw = usePage("gpu");
  const [want, setWant] = useState(null);
  const [compat, setCompat] = useState(null);
  const [edited, setEdited] = useStored("gpu-profiles", {});
  const [editing, setEditing] = useState(null);
  const [advanced, setAdvanced] = useState(false);
  useEffect(() => { if (raw && !want) setWant([int(raw.current_min, 500), int(raw.current_max, 2000)]); }, [raw, want]);
  if (!raw || !want) return <Card title={t("GPU Governor")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const gpu = live?.metrics?.gpu || {};
  const lowest = int(raw.allowed_min, 500), highest = int(raw.allowed_max, 2000), cur = [int(raw.current_min, lowest), int(raw.current_max, highest)];
  const volts = Object.fromEntries((raw.safe_points || []).map((p) => [Number(p.frequency), p.voltage]));
  const stops = [...new Set([...Object.keys(volts).map(Number).filter((f) => f >= lowest && f <= highest), lowest, highest])].sort((a, b) => a - b);
  const [min, max] = [Math.max(lowest, Math.min(want[0], highest)), Math.max(lowest, Math.min(want[1], highest))];
  const backend = String(raw.governor_backend || ""), cyan = raw.cyan_telemetry || {}, high = raw.high_frequency_points || {};
  const unlocked = !!(high.enabled_frequencies || []).length, running = raw.service_active === "active";
  const profiles = (raw.profiles || []).map((p) => ({ ...p, ...(edited[p.key] || {}) }));
  const opts = compat || { set_method: cyan.set_method || "smu", usage_method: cyan.method || "busy-flag", temp_read: cyan.temp_read || "drm", metrics: cyan.fix_metrics ?? true, frequencies: !!cyan.fix_frequency };
  const busy = pick(gpu.usage_percent, gpu.compute_busy_percent);
  const control = (action, title, level = 1) => act({ action: "gpu.service", level, params: { action }, title });
  const dirty = min !== cur[0] || max !== cur[1];
  return (
    <>
      <div className="mobile-stats"><Tile label={t("Core clock")} value={`${num(gpu.frequency_mhz)} MHz`} /><Tile label={t("GPU load")} value={`${num(busy)} %`} /><Tile label={t("Thermal")} value={`${num(gpu.temperature_c, 1)} °C`} /></div>
      <div className="cols two">
        <div className="stack">
          <Card title={t("Operating profile")} sub={t("One click sets the range. The pencil changes name and frequencies.")}>
            <div className="tiles profiles">{profiles.map((p) => <Tile key={p.key} label={p.label} value={`${p.min} – ${p.max} MHz`} note={`${volts[p.max] ?? "--"} mV`} on={p.min === cur[0] && p.max === cur[1]}
              onClick={() => act({ action: "gpu.profile", level: p.max > SAFE_CEILING ? 2 : 1, params: { min: p.min, max: p.max }, title: p.label, body: `${p.min}–${p.max} MHz` })} onEdit={() => setEditing(p)} />)}</div>
          </Card>
          <Card title={t("Frequency range")} sub={t("Fine-tune over the TOML points · current ceiling {ceiling} MHz.", { ceiling: highest })} pill={`${min} – ${max} MHz`} tone={dirty ? "orange" : "blue"}>
            <Rail stops={stops} low={min} high={max} onChange={(a, b) => setWant([a, b])} />
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
              <Number_ label={t("Minimum frequency")} min={lowest} max={max} value={min} unit="MHz" onChange={(v) => setWant([Math.min(v || lowest, max), max])} />
              <Number_ label={t("Maximum frequency")} min={min} max={highest} value={max} unit="MHz" onChange={(v) => setWant([min, Math.max(v || min, min)])} />
            </div>
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
          <div className="row action-dock"><Btn wide onClick={() => act({ action: "gpu.save_boot", level: 1, title: t("Save active range for startup") })}>{t("Save for boot")}</Btn>
            <Btn kind="primary" wide disabled={!dirty} onClick={() => act({ action: "gpu.range", level: max > SAFE_CEILING ? 2 : 1, params: { min, max }, title: t("Apply range"), body: `${min}–${max} MHz` })}>{t("Review and apply range")}</Btn></div>
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
