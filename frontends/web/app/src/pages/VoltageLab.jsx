import { useEffect, useState } from "react";
import { t, useApp } from "../lib.jsx";
import { Btn, Number_, Pill } from "../ui.jsx";

function VoltageCurve({ current, selected, min, max }) {
  const frequencies = [...current, ...selected].map(([f]) => f);
  const low = Math.min(...frequencies), high = Math.max(...frequencies);
  if (!frequencies.length || high === low) return null;
  const x = (f) => 44 + (f - low) * 356 / (high - low);
  const y = (v) => 174 - (Math.max(min, Math.min(max, v)) - min) * 154 / (max - min);
  const path = (points) => points.filter(([, v]) => Number.isInteger(v)).map(([f, v], i) => `${i ? "L" : "M"}${x(f)},${y(v)}`).join(" ");
  return <figure className="voltage-curve"><figcaption><span>{t("GPU voltage curve")}</span><span><i />{t("Current")}<i className="selected" />{t("Selected")}</span></figcaption>
    <svg viewBox="0 0 420 210" role="img" aria-label={t("GPU voltage curve")}>
      {[min, Math.round((min + max) / 2), max].map((v) => <g key={v}><line x1="44" x2="400" y1={y(v)} y2={y(v)} className="grid-line" /><text x="36" y={y(v) + 4} textAnchor="end">{v}</text></g>)}
      {[low, Math.round((low + high) / 2), high].map((f) => <text key={f} x={x(f)} y="194" textAnchor="middle">{f}</text>)}
      <text x="400" y="208" textAnchor="end">MHz</text><text x="8" y="12">mV</text>
      <path d={path(current)} className="current-curve" /><path d={path(selected)} className="selected-curve" />
    </svg></figure>;
}

/** Curves and limits come from the same model as the desktop laboratory. */
export default function VoltageLab({ data }) {
  const { act, running, again } = useApp();
  const lab = data.voltage_lab || {};
  const [selection, setSelection] = useState(null);
  const [draft, setDraft] = useState({});
  useEffect(() => { setDraft({}); setSelection(null); }, [again]);
  const level = selection ?? lab.applied_level ?? -1;
  const points = lab.points || [];
  const custom = level === -1;
  const preset = (lab.levels || []).find((p) => p.level === level)?.values || {};
  const values = Object.fromEntries(points.map(([f, v]) => [f, Object.hasOwn(draft, f) ? draft[f] : v]));
  const proposed = custom ? values : preset;
  const curve = Object.entries(proposed).map(([f, v]) => [Number(f), v]).sort((a, b) => a[0] - b[0]);
  const invalid = curve.some(([, v], i) => !Number.isInteger(v) || v < lab.minimum_mv || v > lab.maximum_mv || (i && v < curve[i - 1][1]));
  const falling = curve.findIndex(([, v], i) => i > 0 && Number.isInteger(v) && v < curve[i - 1][1]);
  const maximum = Math.max(0, ...curve.map(([, v]) => Number(v) || 0));
  const unavailable = lab.is_oberon || !points.length;
  const apply = (restore = false) => act({
    action: custom && !restore ? "gpu.voltage_custom" : "gpu.voltage", level: 2,
    params: custom && !restore ? { values } : { level: restore ? 0 : level },
    title: restore ? t("Restore governor defaults") : custom ? t("Apply voltage curve") : t("Apply GPU voltage Level {level}", { level }),
    body: restore ? t("This restores every packaged original voltage and disables the +2000 MHz TOML points. If the current range exceeds 2000 MHz, it is safely limited after the governor restarts. A backup is created first.")
      : custom ? t("A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation.")
      : t("This restores the complete packaged governor curve, then adds +{added} mV to every safe-point from {start} MHz. A backup is created before the governor restarts.", { added: level * 10, start: 2000 }),
    summary: restore ? [] : [[t("Profile"), custom ? t("Custom") : t("Level {level}", { level })], [t("Active points"), curve.length], [t("Maximum voltage"), `${maximum} mV`]],
    warning: t("Stop every game, benchmark, and 3D workload before continuing."),
  });
  return <div className="voltage-lab">
    <div className="lab-status"><span>{t("GPU voltage curve")}</span><Pill>{lab.applied_level == null ? t("Custom") : t("Level {level}", { level: lab.applied_level })}</Pill></div>
    {lab.is_oberon && <p className="notice">{t("Oberon has only two YAML endpoints, not a validated voltage curve. No voltage was written. Use a protected Oberon frequency profile while the GPU is idle, or switch to Cyan for voltage-curve testing.")}</p>}
    <label className="field"><span>{t("Curve boost")}</span><select className="input" value={level} disabled={unavailable || running} onChange={(e) => { setSelection(Number(e.target.value)); setDraft({}); }}>
      <option value={-1}>{t("Custom")}</option>
      {(lab.levels || []).map(({ level: l }) => <option key={l} value={l}>{t("Level {level}", { level: l })}{l ? ` · +${l * 10} mV ≥ 2000 MHz` : ` · ${t("Restore governor defaults")}`}</option>)}
    </select></label>
    <VoltageCurve current={points} selected={curve} min={lab.minimum_mv} max={lab.maximum_mv} />
    {custom && <p className="note">{lab.minimum_mv}–{lab.maximum_mv} mV · {t("Active points")}: {points.length}</p>}
    <div className="voltage-table"><div className="voltage-row voltage-head"><span>{t("Frequency")}</span><span>{t("Current")}</span><span>{t("Selected")}</span></div>
      {(custom ? points : curve.map(([f]) => [f, points.find(([frequency]) => frequency === f)?.[1]])).map(([f, current]) => <div className={`voltage-row ${proposed[f] !== current ? "changed" : ""}`} key={f}>
        <b>{f} <small>MHz</small></b><span>{current ?? "—"} <small>mV</small></span>
        {custom ? <Number_ label={`${f} MHz`} value={values[f]} min={lab.minimum_mv} max={lab.maximum_mv} disabled={unavailable || running} onChange={(v) => setDraft((d) => ({ ...d, [f]: v }))} /> : <b>{proposed[f]} <small>mV</small></b>}
      </div>)}</div>
    {invalid && <p className="notice" role="status">{t("Invalid voltage curve")} · {lab.minimum_mv}–{lab.maximum_mv} mV{falling > 0 && <span className="curve-error">{t("{frequency} MHz uses {voltage} mV, below {previous_frequency} MHz at {previous_voltage} mV. Voltage cannot decrease while frequency increases.", { frequency: curve[falling][0], voltage: curve[falling][1], previous_frequency: curve[falling - 1][0], previous_voltage: curve[falling - 1][1] })}</span>}</p>}
    <div className="action-dock"><Btn disabled={unavailable || running} onClick={() => apply(true)}>{t("Restore governor defaults")}</Btn><Btn kind="primary" disabled={unavailable || invalid || running || !curve.length} onClick={() => apply()}>{t("Apply voltage curve")}</Btn></div>
  </div>;
}
