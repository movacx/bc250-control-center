import { useState } from "react";
import { num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, ControlTabs, Fold, ProfileDeck, Read, useStored } from "../ui.jsx";
import VoltageLab from "./VoltageLab.jsx";
import { ProfileEditor } from "../ui.jsx";

const SAFE_CEILING = 2000; // the factory TOML's last point; past it the rail turns red
const int = (value, fallback) => (Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : fallback);

const Select = ({ label, value, options, onChange }) => (
  <label className="field"><span>{label}</span><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
);

export default function Gpu() {
  const { act, live, running: actionBusy } = useApp();
  const raw = usePage("gpu");
  const [tab, setTab] = useState("profiles"), [chosen, setChosen] = useState(null);
  const [compat, setCompat] = useState(null);
  const [edited, setEdited] = useStored("gpu-profiles", {});
  const [editing, setEditing] = useState(null);
  const [advanced, setAdvanced] = useState(false);
  if (!raw) return <Card title={t("GPU Governor")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const gpu = live?.metrics?.gpu || {};
  const lowest = int(raw.allowed_min, 500), highest = int(raw.profile_max, int(raw.allowed_max, 2000)), cur = [int(raw.current_min, lowest), int(raw.current_max, highest)];
  const volts = Object.fromEntries((raw.safe_points_with_voltage || raw.safe_points || []).map((p) => [Number(p.frequency), p.voltage]));
  const stops = [...new Set([...Object.keys(volts).map(Number).filter((f) => f >= lowest && f <= highest), lowest, highest])].sort((a, b) => a - b);
  const backend = String(raw.governor_backend || ""), cyan = raw.cyan_telemetry || {}, high = raw.high_frequency_points || {};
  const unlocked = !!(high.enabled_frequencies || []).length, running = raw.service_active === "active";
  const profiles = (raw.profiles || []).map((p) => ({ ...p, ...(edited[p.key] || {}), min: Math.max(lowest, Math.min(highest, edited[p.key]?.min ?? p.min)), max: Math.max(lowest, Math.min(highest, edited[p.key]?.max ?? p.max)) }));
  const opts = compat || { set_method: cyan.set_method || "smu", usage_method: cyan.method || "busy-flag", temp_read: cyan.temp_read || "drm", metrics: cyan.fix_metrics ?? true, frequencies: !!cyan.fix_frequency };
  const busy = pick(gpu.usage_percent, gpu.compute_busy_percent);
  const control = (action, title, level = 1) => act({ action: "gpu.service", level, params: { action }, title });
  const selected = profiles.find((p) => p.key === chosen) || profiles.find((p) => p.min === cur[0] && p.max === cur[1]) || profiles[0];
  const pending = selected.min !== cur[0] || selected.max !== cur[1];
  return <div className="control-workspace gpu-workspace">
    <ControlTabs items={[["profiles", t("Profiles"), "nav_gpu"], ["monitor", t("Monitoring"), "nav_performance"], ["voltage", t("Voltage laboratory"), "nav_settings"]]} value={tab} onChange={setTab} />
    {tab === "profiles" && <>
      <Card className="control-primary"><ProfileDeck profiles={profiles.map((p) => ({ ...p, name: p.label, voltage: volts[p.max] }))} selected={{ ...selected, name: selected.label }} onSelect={setChosen} onEdit={(key) => setEditing(profiles.find((p) => p.key === key))} />
        <div className="profile-parameters"><Read label={t("Active range")} value={`${cur[0]}–${cur[1]}`} unit="MHz" /></div>
        {editing && <ProfileEditor key={editing.key} profile={{ name: editing.label, min: editing.min, max: editing.max }} fields={[["min", t("Minimum frequency"), lowest, highest, "MHz"], ["max", t("Maximum frequency"), lowest, highest, "MHz"]]} onClose={() => setEditing(null)} onSave={(p) => { setEdited({ ...edited, [editing.key]: { label: p.name, min: Math.min(p.min, p.max), max: Math.max(p.min, p.max) } }); setChosen(editing.key); setEditing(null); }} />}
        {pending && <p className="note">{t("Selected in the UI (not applied yet)")}</p>}
        <Btn kind="primary" wide disabled={actionBusy} onClick={() => act({ action: "gpu.profile", level: selected.max > SAFE_CEILING ? 2 : 1, params: { min: selected.min, max: selected.max }, title: selected.label, body: `${selected.min}–${selected.max} MHz` })}>{t("Review and apply")}</Btn>
        <Btn disabled={pending || actionBusy} onClick={() => act({ action: "gpu.save_boot", level: 1, title: t("Save active range for startup") })}>{t("Save for boot")}</Btn>
      </Card>
      <Card title={t("Governor service")} className="governor-control" pill={running ? t("Active") : t("Not connected")} tone={running ? "green" : ""}>
        <div className="service-actions"><Btn onClick={() => act({ action: "gpu.status", title: t("View status") })}>{t("View status")}</Btn><Btn onClick={() => control("reiniciar", t("Restart service"))}>{t("Restart")}</Btn>{running ? <Btn onClick={() => control("desactivar", t("Stop governor"), 2)}>{t("Stop governor")}</Btn> : <Btn onClick={() => control("activar", t("Start governor"))}>{t("Start governor")}</Btn>}</div>
        {backend.startsWith("cyan") && <section className="service-compat" aria-label={t("Cyan kernel compatibility")}>
          <div className="compat-fields"><Select label={t("Governor method")} value={opts.set_method} options={[["smu", "SMU"], ["kernel", "Kernel"]]} onChange={(v) => setCompat({ ...opts, set_method: v })} /><Select label={t("Usage reading")} value={opts.usage_method} options={[["busy-flag", "busy-flag"], ["process", "process"], ["kernel", "kernel"]]} onChange={(v) => setCompat({ ...opts, usage_method: v })} /><Select label={t("Temperature reading")} value={opts.temp_read} options={[["drm", "DRM"], ["sysfs", "sysfs"]]} onChange={(v) => setCompat({ ...opts, temp_read: v })} /></div>
          <div className="compat-checks"><Check checked={opts.metrics} onChange={(v) => setCompat({ ...opts, metrics: v })}>{raw.fix_labels.metrics}</Check><Check checked={opts.frequencies} onChange={(v) => setCompat({ ...opts, frequencies: v })}>{raw.fix_labels.frequency}</Check></div>
          <Btn kind="primary" wide disabled={actionBusy} onClick={() => act({ action: "gpu.compat", level: opts.set_method === "kernel" ? 2 : 1, params: { set_method: opts.set_method, usage_method: opts.usage_method, metrics: opts.metrics, frequencies: opts.frequencies, temp_read: opts.temp_read }, title: t("Cyan kernel compatibility") })}>{t("Apply compatibility")}</Btn>
        </section>}
      </Card>
      <details className="gpu-advanced"><summary>{t("Additional settings")}</summary>
          {high.available && <Fold risk title={t("TOML points above 2000 MHz")}>
            <div className="reads"><div className="read"><span>{t("Requested state")}</span><b>{unlocked ? t("Enabled") : t("Commented")}</b></div><div className="read"><span>{t("Safe-points")}</span><b>{(high.frequencies || []).join(" · ")} MHz</b></div></div>
            <p className="note">{t("No restart or clock change")}</p>
            {unlocked && cur[1] > 2000 && <p className="notice">{t("Apply a range at or below 2000 MHz before disabling the +2000 MHz TOML points. The live GPU range was not changed.")}</p>}
            <Btn kind={unlocked ? "" : "danger"} disabled={unlocked && cur[1] > 2000} onClick={() => act({ action: "gpu.high_points", level: 2, params: { enable: !unlocked }, title: unlocked ? t("Re-comment the +2000 MHz points") : t("Uncomment +2000 MHz points"), body: t("This edits only the TOML safe-point blocks above 2000 MHz and validates the complete file. These frequencies are experimental, are not guaranteed stable, and can crash the display or system. This does not reload Cyan or change the live GPU range; use Apply active range explicitly after selecting a point.") })}>
              {unlocked ? t("Re-comment the +2000 MHz points") : t("Uncomment +2000 MHz points")}</Btn>
          </Fold>}      <Card title={t("Advanced GPU diagnostics")} action={<Btn kind="link" onClick={() => setAdvanced(!advanced)}>{advanced ? t("Hide") : t("Show")} ›</Btn>}>
        {advanced && <div className="reads">{stops.map((f) => volts[f] != null && <div className="read" key={f}><span>{f} MHz</span><b>{volts[f]} mV</b></div>)}
          <div className="read"><span>{t("Frequency range")}</span><b>{lowest}–{highest} MHz</b></div><div className="read"><span>{t("Active range")}</span><b>{cur[0]}–{cur[1]} MHz</b></div><div className="read"><span>{t("Backend")}</span><b>{backend || "--"}</b></div><div className="read"><span>config.toml</span><b>{raw.config_path || "--"}</b></div></div>}
      </Card>
      </details>
    </>}
    {tab === "monitor" && <><Card title={t("Runtime status")}><Read label={t("Core clock")} value={num(pick(raw.sclk_actual, gpu.frequency_mhz))} unit="MHz" /><Read label={t("GPU voltage")} value={num(pick(raw.voltaje_actual, gpu.voltage_mv))} unit="mV" /><Read label={t("Thermal")} value={num(gpu.temperature_c, 1)} unit="°C" /><Read label={t("GPU load")} value={num(busy)} unit="%" /><Read label={t("Memory clock")} value={num(pick(raw.mclk_actual, gpu.memory_frequency_mhz))} unit="MHz" /><Read label={t("Active range")} value={`${cur[0]}–${cur[1]}`} unit="MHz" /></Card></>}
    {tab === "voltage" && <Card className="voltage-panel"><VoltageLab data={raw} /></Card>}
  </div>;
}
