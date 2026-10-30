import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import icons from "./icons.gen.js";
import { t } from "./lib.jsx";

export const Icon = ({ name }) => <svg className="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: icons[name] || "" }} />;

/** The desktop's SectionCard: title, subtitle, a status pill or an action at the right. */
export function Card({ title, sub, pill, tone, action, risk, children, className = "" }) {
  return (
    <section className={`card ${risk ? "risk" : ""} ${className}`}>
      {risk && <div className="risk-tag"><Icon name="warning_orange" />{t("DANGER ZONE")}</div>}
      {(title || action || pill) && (
        <div className="hd">
          {title && <h2>{title}</h2>}
          {pill && <Pill tone={tone}>{pill}</Pill>}
          {action}
        </div>
      )}
      {sub && <p className="sub">{sub}</p>}
      {children !== undefined && <div className="body">{children}</div>}
    </section>
  );
}

export const Pill = ({ tone = "", children }) => <span className={`pill ${tone}`}>{children}</span>;

export const Fold = ({ title, risk, children }) => <details className={`card fold ${risk ? "risk" : ""}`}><summary>{risk && <Icon name="warning_orange" />}<h2>{title}</h2><span>+</span></summary><div className="body">{children}</div></details>;

export function Modal({ onClose, children }) {
  const ref = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const shell = document.querySelector(".shell");
    const wasInert = shell?.inert;
    if (shell) shell.inert = true;
    const focusable = () => [...ref.current.querySelectorAll("button, input, select, [tabindex='0']")].filter((el) => !el.disabled && el.getClientRects().length);
    (focusable()[0] || ref.current).focus();
    const key = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close.current(); }
      if (e.key !== "Tab") return;
      const items = focusable(), first = items[0], last = items.at(-1);
      if (!items.length) { e.preventDefault(); return; }
      if (!ref.current.contains(document.activeElement)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
      else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); if (shell) shell.inert = wasInert; previous?.focus(); };
  }, []);
  return createPortal(<div className="scrim" ref={ref} tabIndex={-1} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>{children}</div>, document.body);
}

export const Btn = ({ kind = "", small, wide, children, ...rest }) => (
  <button type="button" className={`btn ${kind} ${small ? "small" : ""} ${wide ? "wide" : ""}`} {...rest}>{children}</button>
);

export const Check = ({ checked, onChange, children, disabled }) => (
  <label className="check"><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />{children}</label>
);

export const Tile = ({ label, value, note, tone, on, onClick, onEdit }) => {
  const inner = <><small>{label}</small><strong>{value}</strong>{note && <span>{note}</span>}</>;
  return onClick
    ? <div className={`profile-tile ${on ? "on" : ""}`}><button type="button" className={`tile ${tone || ""} ${on ? "on" : ""}`} aria-pressed={!!on} onClick={onClick}>{inner}</button>
        {onEdit && <button type="button" className="edit" aria-label={`${t("Edit")} ${label}`} onClick={onEdit}><Icon name="edit_gray" /></button>}</div>
    : <div className={`tile ${tone || ""}`}>{inner}</div>;
};

/** A reading: quiet name, the number, its unit, an optional word of context. */
export const Read = ({ label, value, unit, note, tone }) => (
  <div className={`read ${tone || ""}`}><span>{label}</span><div><b>{value ?? "--"}</b>{unit && value !== undefined && value !== "--" && <em>{unit}</em>}{note && <small>{note}</small>}</div></div>
);

export const Segments = ({ items, value, onChange }) => (
  <div className="seg" role="tablist">{items.map((item) => (
    <button key={item.key} role="tab" aria-selected={item.key === value} className={item.key === value ? "on" : ""} onClick={() => onChange(item.key)}>{item.title}</button>))}</div>
);

export function Number_({ value, onChange, min, max, step = 1, unit, label, disabled }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  return (
    <label className="field"><span>{label}</span>
      <div className="row"><input className="input num" type="number" inputMode="numeric" value={editing ? draft : value} min={min} max={max} step={step} disabled={disabled}
        onFocus={(e) => { setDraft(e.target.value); setEditing(true); }} onBlur={() => setEditing(false)}
        onChange={(e) => { setDraft(e.target.value); onChange(e.target.value === "" ? "" : Number(e.target.value)); }} />{unit && <span>{unit}</span>}</div></label>
  );
}

/** A dropdown made of buttons: large touch targets, closes on outside press. */
export function Menu({ label, items, value, onPick }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!box.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return (
    <div className="rel" ref={box}>
      <Btn small onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}>{label} ▾</Btn>
      {open && <div className="menu" role="menu">{items.map((item) => (
        <button key={item.key} role="menuitem" className={item.key === value ? "on" : ""} disabled={item.available === false}
          onClick={() => { setOpen(false); onPick(item.key); }}><b>{item.title}</b><small>{item.hint}</small></button>))}</div>}
    </div>
  );
}

// -- charts: our own SVG, a continuous line, round 1-2-5 axes -----------------------------------------
const WINDOW = 120;
const slot = (i) => `var(--c-series-${(i % 8) + 1})`;

export function useWidth() {
  const ref = useRef(null);
  const [size, setSize] = useState({ w: 600, h: 260 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const watch = new ResizeObserver(([entry]) => setSize({ w: Math.max(240, entry.contentRect.width), h: Math.max(120, entry.contentRect.height) }));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  return [ref, size];
}

const ageLabel = (age) => (age === 0 ? t("Now") : age >= 60 ? `-${Math.floor(age / 60)}:${String(age % 60).padStart(2, "0")}` : `-${age} s`);

export function LineChart({ chart, small, single }) {
  const [ref, { w, h }] = useWidth();
  const { series, ages, min, max, ticks } = chart;
  const left = 10, right = 58, top = 14, bottom = 26, pw = Math.max(10, w - left - right), ph = Math.max(10, h - top - bottom);
  const x = (age) => left + pw * (1 - age / WINDOW), y = (v) => top + ph * (1 - (v - min) / (max - min || 1));
  const step = w < 420 ? 60 : w < 700 ? 30 : 15, marks = [];
  for (let age = WINDOW; age >= 0; age -= step) marks.push(age);
  const first = series[0]?.values || [];
  const mean = first.length ? first.reduce((a, b) => a + b, 0) / first.length : 0;
  const peak = first.length ? Math.max(...first) : 0;
  const path = (values) => values.map((v, i) => `${i ? "L" : "M"}${x(ages[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <div ref={ref} className={`chart ${small ? "small" : ""}`}>
      <svg width={w} height={h} role="img" aria-label={series.map((s) => s.name).join(", ")}>
        {ticks.map((tick) => <g key={tick.value}><line x1={left} x2={left + pw} y1={y(tick.value)} y2={y(tick.value)} stroke="var(--c-chart-grid)" />
          <text x={left + pw + 8} y={y(tick.value) + 4} fontSize="11" fill="var(--c-muted)">{tick.label}</text></g>)}
        {marks.map((age) => <g key={age}><line x1={x(age)} x2={x(age)} y1={top} y2={top + ph} stroke="var(--c-chart-grid)" />
          <text x={Math.min(x(age), left + pw - 14)} y={h - 8} fontSize="11" textAnchor={age === WINDOW ? "start" : age === 0 ? "end" : "middle"} fill="var(--c-muted)">{ageLabel(age)}</text></g>)}
        <line x1={left} x2={left + pw} y1={top + ph} y2={top + ph} stroke="var(--c-chart-axis)" />
        {series.map((s, i) => {
          const color = single ? "var(--c-blue)" : slot(i);
          const d = path(s.values);
          return <g key={s.name}>
            {series.length === 1 && s.values.length > 1 && <path d={`${d}L${x(ages[s.values.length - 1])},${top + ph}L${x(ages[0])},${top + ph}Z`} fill={color} opacity=".1" />}
            <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></g>;
        })}
        {series.length === 1 && first.length > 1 && <>
          <line x1={left} x2={left + pw} y1={y(mean)} y2={y(mean)} stroke="var(--c-muted)" strokeDasharray="4 3" />
          <text x={left + 6} y={y(mean) - 5} fontSize="11" fill="var(--c-text)">{t("avg {value}", { value: chart.avg ?? "" })}</text>
          <g transform={`translate(${left + pw + 4},${y(first[first.length - 1]) - 10})`}><rect width="52" height="20" rx="4" fill="var(--c-blue)" />
            <text x="26" y="14" fontSize="11" textAnchor="middle" fill="var(--c-on-accent)" fontWeight="700">{chart.last}</text></g>
          <text x={Math.max(left + 44, Math.min(x(ages[first.indexOf(peak)]), left + pw - 44))} y={Math.max(y(peak) - 8, 12)} fontSize="11" textAnchor="middle" fill="var(--c-text)">{t("peak {value}", { value: chart.peak ?? "" })}</text></>}
      </svg>
    </div>
  );
}

/** One row per series, colour = value (the desktop's heat map for per-thread views). */
export function HeatChart({ chart }) {
  const { series, min, max } = chart;
  return (
    <div className="chart" style={{ overflow: "auto", padding: 8 }}>
      {series.map((s) => (
        <div key={s.name} className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
          <small style={{ width: 70, flex: "none", color: "var(--c-muted)" }}>{s.name}</small>
          <div style={{ display: "flex", flex: 1, height: 16, gap: 1 }}>{s.values.map((v, i) => (
            <i key={i} style={{ flex: 1, background: `color-mix(in srgb, var(--c-blue) ${Math.round(100 * Math.max(0, Math.min(1, (v - min) / (max - min || 1))))}%, var(--c-panel-alt))` }} />))}</div>
        </div>))}
    </div>
  );
}

export const Dialog = ({ title, onClose, children, footer }) => (
  <Modal onClose={onClose}><div className="dialog" role="dialog" aria-label={title} aria-modal="true">
    <header><h3>{title}</h3></header><section>{children}</section><footer>{footer}</footer></div></Modal>
);

/** The pencil of a profile card: name and numbers, kept in this browser. */
export function ProfileEditor({ profile, fields, onSave, onClose }) {
  const [draft, setDraft] = useState(profile);
  const valid = String(draft.name || "").trim() && fields.every(([key, _label, min, max]) => Number.isInteger(draft[key]) && draft[key] >= min && draft[key] <= max);
  return (
    <Dialog title={t("Profile name")} onClose={onClose} footer={<><Btn onClick={onClose}>{t("Cancel")}</Btn><Btn kind="primary" disabled={!valid} onClick={() => onSave(draft)}>{t("Save")}</Btn></>}>
      <label className="field"><span>{t("Profile name")}</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
      {fields.map(([key, label, min, max, unit]) => <Number_ key={key} label={`${label} · ${min}–${max} ${unit}`} min={min} max={max} step={key === "frequency" ? 50 : key === "vid" ? 5 : 1} value={draft[key]}
        onChange={(v) => setDraft({ ...draft, [key]: v })} />)}
    </Dialog>
  );
}

/** Profiles live in this browser: the desktop keeps its own copy. */
export function useStored(key, initial) {
  const [value, setValue] = useState(() => { try { return JSON.parse(localStorage.getItem(key)) ?? initial; } catch { return initial; } });
  const set = (next) => { setValue(next); try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* private window */ } };
  return [value, set];
}
