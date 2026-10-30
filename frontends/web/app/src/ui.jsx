import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import icons from "./icons.gen.js";
import { t } from "./lib.jsx";

export function useMobile() {
  const [mobile, setMobile] = useState(() => matchMedia("(max-width: 820px)").matches);
  useEffect(() => { const media = matchMedia("(max-width: 820px)"); const update = () => setMobile(media.matches); media.addEventListener("change", update); return () => media.removeEventListener("change", update); }, []);
  return mobile;
}

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
  const [cursor, setCursor] = useState(null);
  const drag = useRef(false), clip = useId().replace(/:/g, "");
  const { series, ages = [], min, max, ticks = [] } = chart;
  const mobile = w < 560;
  const left = mobile ? Math.max(40, Math.min(70, Math.max(0, ...ticks.map((tick) => tick.label.length)) * 5 + 8)) : 12, right = mobile ? 14 : 64, top = 12, bottom = 30;
  const pw = Math.max(10, w - left - right), ph = Math.max(10, h - top - bottom);
  const span = mobile ? Math.max(5, Math.min(WINDOW, Math.ceil(Math.max(0, ...ages)))) : WINDOW;
  const x = (age) => left + pw * (1 - age / span), y = (v) => top + ph * (1 - (v - min) / (max - min || 1));
  const marks = mobile ? [span, Math.round(span / 2), 0] : [120, 90, 60, 30, 0];
  const shownTicks = mobile && ticks.length > 3 ? [ticks[0], ticks[Math.floor((ticks.length - 1) / 2)], ticks.at(-1)] : ticks;
  const index = cursor == null ? Math.max(0, ages.length - 1) : Math.min(cursor, Math.max(0, ages.length - 1));
  const format = (value) => {
    if (!Number.isFinite(value)) return "—";
    let unit = chart.unit || "", scaled = value;
    if (unit === "B" || unit === "B/s") {
      const n = Math.min(4, Math.max(0, Math.floor(Math.log2(Math.max(Math.abs(value), 1)) / 10)));
      scaled = value / 1024 ** n; unit = ["B", "KiB", "MiB", "GiB", "TiB"][n] + (chart.rate ? "/s" : "");
    }
    return `${new Intl.NumberFormat(document.documentElement.lang, { maximumFractionDigits: 1 }).format(scaled)}${unit ? ` ${unit}` : ""}`;
  };
  const nearest = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const age = span * (1 - Math.max(0, Math.min(1, ((event.clientX - rect.left) * w / rect.width - left) / pw)));
    let best = 0;
    for (let i = 1; i < ages.length; i++) if (Math.abs(ages[i] - age) < Math.abs(ages[best] - age)) best = i;
    setCursor(best);
  };
  const path = (values) => values.map((v, i) => `${i ? "L" : "M"}${x(ages[i] ?? 0).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return <div className="chart-shell">
    <div className="chart-readout"><span>{cursor == null ? t("Live") : ageLabel(Math.round(ages[index] || 0))}</span><output aria-live="off">{series.length === 1 ? format(series[0].values[index]) : t("Graphs")}</output>{cursor != null && <button onClick={() => setCursor(null)} aria-label={t("Live")}><Icon name="refresh_gray" /></button>}</div>
    <div ref={ref} className={`chart ${small ? "small" : ""}`}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" tabIndex={0} aria-label={series.map((s) => s.name).join(", ")}
        onPointerDown={(e) => { drag.current = true; e.currentTarget.setPointerCapture(e.pointerId); nearest(e); }}
        onPointerMove={(e) => { if (drag.current) nearest(e); }} onPointerUp={() => { drag.current = false; }} onPointerCancel={() => { drag.current = false; }}
        onKeyDown={(e) => { if (e.key === "Escape") setCursor(null); if (["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); setCursor(Math.max(0, Math.min(ages.length - 1, index + (e.key === "ArrowLeft" ? -1 : 1)))); } }}>
        <defs><clipPath id={clip}><rect x={left} y={top} width={pw} height={ph} /></clipPath></defs>
        {shownTicks.map((tick) => <g key={tick.value}><line x1={left} x2={left + pw} y1={y(tick.value)} y2={y(tick.value)} stroke="var(--c-chart-grid)" /><text x={mobile ? left - 8 : left + pw + 8} textAnchor={mobile ? "end" : "start"} y={y(tick.value) + 4} fontSize={mobile ? 10 : 11} fill="var(--c-muted)">{tick.label}</text></g>)}
        {marks.map((age) => <text key={age} x={x(age)} y={h - 8} fontSize="10" textAnchor={age === (mobile ? span : WINDOW) ? "start" : age === 0 ? "end" : "middle"} fill="var(--c-muted)">{ageLabel(age)}</text>)}
        <g clipPath={`url(#${clip})`}>{series.map((s, i) => {
          const color = single || series.length === 1 ? "var(--c-blue)" : slot(i), d = path(s.values);
          return <g key={s.name}>{series.length === 1 && s.values.length > 1 && <path d={`${d}L${x(ages[s.values.length - 1] ?? 0)},${top + ph}L${x(ages[0] ?? 120)},${top + ph}Z`} fill={color} opacity=".07" />}<path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />{cursor != null && Number.isFinite(s.values[index]) && <circle cx={x(ages[index] || 0)} cy={y(s.values[index])} r="4" fill={color} />}</g>;
        })}{cursor != null && <line x1={x(ages[index] || 0)} x2={x(ages[index] || 0)} y1={top} y2={top + ph} stroke="var(--c-muted)" strokeDasharray="3 4" />}</g>
      </svg>
    </div>
    {cursor != null && series.length > 1 && <div className="chart-values">{series.map((s, i) => <span key={s.name}><i style={{ background: slot(i) }} />{s.name}<b>{format(s.values[index])}</b></span>)}</div>}
  </div>;
}

/** One row per series, colour = value (the desktop's heat map for per-thread views). */
export function HeatChart({ chart }) {
  const mobile = useMobile();
  const { series, min, max } = chart;
  if (mobile) return <div className="core-histories">{series.map((s, i) => <div key={s.name}><span>{s.name}</span><svg viewBox="0 0 120 30" role="img" aria-label={s.name}><path d={s.values.map((v, n) => `${n ? "L" : "M"}${n * 120 / Math.max(1, s.values.length - 1)},${28 - 26 * (v - min) / (max - min || 1)}`).join(" ")} fill="none" stroke={slot(i)} strokeWidth="2" /></svg><b>{s.values.at(-1)?.toFixed(0)} {chart.unit}</b></div>)}</div>;
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
  const host = useRef(null);
  const [draft, setDraft] = useState(profile);
  useEffect(() => { host.current?.scrollIntoView({ block: "center" }); host.current?.querySelector("input")?.focus({ preventScroll: true }); }, []);
  const valid = String(draft.name || "").trim() && fields.every(([key, _label, min, max]) => Number.isInteger(draft[key]) && draft[key] >= min && draft[key] <= max);
  return (
    <section ref={host} className="inline-editor" aria-label={t("Profile name")}>
      <header><h3>{t("Edit")} · {profile.name}</h3><Btn kind="link" onClick={onClose}>{t("Close")}</Btn></header>
      <form onSubmit={(e) => { e.preventDefault(); if (valid) onSave(draft); }}>
      <label className="field"><span>{t("Profile name")}</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
      <div className="editor-fields">{fields.map(([key, label, min, max, unit]) => <Number_ key={key} label={`${label} · ${unit}`} min={min} max={max} step={key === "frequency" ? 50 : key === "vid" ? 5 : 1} value={draft[key]}
        onChange={(v) => setDraft({ ...draft, [key]: v })} />)}</div>
      <footer><Btn onClick={onClose}>{t("Cancel")}</Btn><Btn kind="primary" type="submit" disabled={!valid}>{t("Save")}</Btn></footer></form>
    </section>
  );
}

/** Profiles live in this browser: the desktop keeps its own copy. */
export function useStored(key, initial) {
  const [value, setValue] = useState(() => { try { return JSON.parse(localStorage.getItem(key)) ?? initial; } catch { return initial; } });
  const set = (next) => { setValue(next); try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* private window */ } };
  return [value, set];
}
