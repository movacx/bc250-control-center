import { useEffect, useState } from "react";
import { keep, t, useApp } from "../lib.jsx";
import { Btn, Number_ } from "../ui.jsx";

/** Curves and limits come from the same model as the desktop laboratory. */
export default function VoltageLab({ data }) {
  const { act, running, again, cancelReview } = useApp();
  const lab = data.voltage_lab || {};
  const [selection, setSelection] = useState(null);
  const [draft, setDraft] = useState({});
  useEffect(() => { setDraft({}); setSelection(null); }, [again]);
  const level = selection ?? ([1, 2, 3].includes(lab.applied_level) ? lab.applied_level : -1);
  const points = lab.points || [];
  const custom = level === -1;
  const preset = (lab.levels || []).find((p) => p.level === level)?.values || {};
  const values = Object.fromEntries(points.map(([f, v]) => [f, Object.hasOwn(draft, f) ? draft[f] : v]));
  const proposed = custom ? values : preset;
  const originals = (lab.levels || []).find((p) => p.level === 0)?.values || {};
  const displayPoints = points; // same active rows as the desktop drawer
  const changed = points.filter(([f, v]) => Number.isInteger(proposed[f]) && proposed[f] !== v).length;
  const added = points.filter(([f]) => Number.isInteger(proposed[f]) && Number.isInteger(originals[f])).map(([f]) => proposed[f] - originals[f]);
  const deltaText = (delta) => !Number.isInteger(delta) || delta === 0 ? "—" : delta > 0 ? `+${delta}` : String(delta);

  const curve = Object.entries(proposed).map(([f, v]) => [Number(f), v]).sort((a, b) => a[0] - b[0]);
  const invalid = curve.some(([, v], i) => !Number.isInteger(v) || v < lab.minimum_mv || v > lab.maximum_mv || (i && v < curve[i - 1][1]));
  const falling = curve.findIndex(([, v], i) => i > 0 && Number.isInteger(v) && v < curve[i - 1][1]);
  const maximum = Math.max(0, ...curve.map(([, v]) => Number(v) || 0));
  const unavailable = lab.is_oberon || !points.length;
  const apply = (restore = false) => act({
    inline: true,
    action: custom && !restore ? "gpu.voltage_custom" : "gpu.voltage", level: 2,
    params: custom && !restore ? { values } : { level: restore ? 0 : level },
    title: restore ? t("Restore governor defaults") : t("Apply voltage curve"),
    body: restore ? t("This restores every packaged original voltage and disables the +2000 MHz TOML points. If the current range exceeds 2000 MHz, it is safely limited after the governor restarts. A backup is created first.")
      : custom ? t("A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation.")
      : t("This restores the complete packaged governor curve, then adds +{added} mV to every safe-point from {start} MHz. A backup is created before the governor restarts.", { added: level * 10, start: 2000 }),
    summary: restore ? [] : [[t("Profile"), custom ? t("Custom") : t({ 1: "Gentle", 2: "Moderate", 3: "High" }[level])], [t("Active points"), curve.length], [t("Maximum voltage"), `${maximum} mV`]],
    warning: t("Stop every game, benchmark, and 3D workload before continuing."),
  });
  return <section className="voltage-workspace" role="region" aria-label={t("Voltage laboratory")}>
    <section className="voltage-lab">
    {lab.is_oberon && <p className="notice">{t("Oberon has only two YAML endpoints, not a validated voltage curve. No voltage was written. Use a protected Oberon frequency profile while the GPU is idle, or switch to Cyan for voltage-curve testing.")}</p>}
    <div className="lab-presets" aria-label={t("Curve boost")}>{[[1, keep("Gentle")], [2, keep("Moderate")], [3, keep("High")], [-1, keep("Custom")]].map(([l, label]) => <button key={l} className={level === l ? "selected" : ""} aria-pressed={level === l} disabled={unavailable || running} onClick={() => { cancelReview?.(); setSelection(l); }}><b>{l === -1 ? t("Custom") : `+${l * 10} mV`}</b><span>{l === -1 ? t("Custom\nEdit active points").split("\n").at(-1) : t(label)}</span></button>)}</div>
    {custom && <p className="note">{lab.minimum_mv}–{lab.maximum_mv} mV · {t("Active points")}: {points.length}</p>}
    <div className="voltage-table"><div className="voltage-row voltage-head"><span>{t("Frequency")}</span><span>{t("Current")}</span><span>{t("Selected")}</span><span>Δ</span></div>
      {displayPoints.map(([f, current]) => <div className={`voltage-row ${proposed[f] !== current ? "changed" : ""}`} key={f}>
        <b>{f} <small>MHz</small></b><span>{current ?? "—"} <small>mV</small></span>
        {custom ? <Number_ label={`${f} MHz`} value={values[f]} min={lab.minimum_mv} max={lab.maximum_mv} step={5} disabled={unavailable || running} onChange={(v) => { cancelReview?.(); setDraft((d) => ({ ...d, [f]: v })); }} /> : <b>{proposed[f]} <small>mV</small></b>}
        <span className="voltage-delta" title={t("Above governor default")}>{deltaText(Number.isInteger(proposed[f]) && Number.isInteger(originals[f]) ? proposed[f] - originals[f] : null)}</span>
      </div>)}</div>
    {invalid && <p className="notice" role="status">{t("Invalid voltage curve")} · {lab.minimum_mv}–{lab.maximum_mv} mV{falling > 0 && <span className="curve-error">{t("{frequency} MHz uses {voltage} mV, below {previous_frequency} MHz at {previous_voltage} mV. Voltage cannot decrease while frequency increases.", { frequency: curve[falling][0], voltage: curve[falling][1], previous_frequency: curve[falling - 1][0], previous_voltage: curve[falling - 1][1] })}</span>}</p>}
    </section><footer className="voltage-footer"><p className="note">{changed === 1 ? t("1 point changed") : t("{count} points changed", { count: changed })} · {t("peak {value} mV", { value: maximum })}{added.length > 0 ? ` · ${t("max {value} mV", { value: deltaText(Math.max(...added)) })}` : ""}</p><div className="action-dock"><Btn disabled={unavailable || running} onClick={() => apply(true)}>{t("Restore governor defaults")}</Btn><Btn kind="primary" disabled={unavailable || invalid || running || !curve.length} onClick={() => apply()}>{t("Review and apply")}</Btn></div></footer>
  </section>;
}
