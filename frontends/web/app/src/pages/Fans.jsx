import DesktopFans from "./DesktopFans.jsx";
import { useEffect, useRef, useState } from "react";
import { keep, num, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Menu, Read, useMobile } from "../ui.jsx";

/* Fan control v2, the same channel board as the desktop Fans page: every
 * header with its own setting (Firmware, Fixed, Curve or Mix), fan or pump,
 * named profiles, and control from boot. The server decides every state and
 * rule (bc250cc.application.fan.board_view / board_actions); this page only
 * shows them and sends one closed action per change. */

export const MODES = [["firmware", keep("Firmware")], ["fixed", keep("Fixed")], ["curve", keep("Curve")], ["mix", keep("Mix")]];
export const ROLES = [["fan", keep("Fan")], ["pump", keep("Pump")]];
export const SOURCES = [["hottest", keep("Hottest chip")], ["gpu", "GPU"], ["cpu", "CPU"], ["vrm", "VRM"], ["board", keep("Board")]];
// Every state and notice the server may send, so the build collects them for translation.
keep("Pump stopped"); keep("Fan stopped"); keep("Error"); keep("Another program"); keep("Not detected"); keep("Pending");
keep("BIOS"); keep("Applied"); keep("Saved"); keep("Critical"); keep("Failsafe"); keep("Active"); keep("Paused");
keep("Waiting"); keep("Stopped"); keep("{count} curves"); keep("Quiet"); keep("Balanced"); keep("Performance");
keep("{program} controls the fan. Nothing here writes to it."); keep("The fan is handed to another program. Nothing here writes to it.");
keep("Checking the system fan service…"); keep("Needs the installed BC250 Control Center package and systemd or OpenRC.");
keep("Only the desktop follows the curve, and only after you log in."); keep("The service still follows an older curve or preset. Sync it to use the one on screen.");
keep("The system service follows {channels}."); keep("A fan was changed by hand or from Quick Access. Apply its setting again to resume.");
keep("Waiting for the NCT fan driver."); keep("Waiting for temperature sensors."); keep("The service reported an error.");
keep("No curve or preset to follow; the firmware drives the fan."); keep("The service is enabled but not running. The firmware drives the fan.");
keep("No NCT fan controller was found. Prepare the PWM driver to read and control the fans.");
keep("The fans are shown read-only. Prepare the nct6687 PWM driver to control them.");

const label = (pairs, key) => t((pairs.find(([k]) => k === key) || [key, key])[1]);
export const say = (text, values) => (values && Object.keys(values).length ? t(text, values) : t(text));
export const channelName = (row) => row.label || row.short_header;
export const editorTitle = (row) => row.label || row.header;
const ADVANCED = [["min_percent", keep("Minimum PWM"), 0, 100, "%"], ["max_percent", keep("Maximum PWM"), 0, 100, "%"],
  ["start_percent", keep("Spin-up kick"), 0, 100, "%"], ["hysteresis_c", keep("Hysteresis"), 0, 10, "°C"],
  ["response_delay_seconds", keep("Response delay"), 0, 30, "s"], ["max_up_step_percent", keep("Largest step up"), 1, 100, "%"],
  ["max_down_step_percent", keep("Largest step down"), 1, 100, "%"]];
const TONE_CLASS = { green: "ok", orange: "warn", red: "bad", blue: "info" };
export const toneClass = (tone) => TONE_CLASS[tone] || "";

/** A saved channel setting turned into another mode, keeping what it can (the desktop editor's entry()). */
export function withMode(entry, mode, defaultCurve) {
  if (mode === "firmware") return { mode: "firmware" };
  const role = entry.role || "fan", pump = role === "pump";
  const tuning = Object.fromEntries(ADVANCED.map(([key]) => [key, entry[key]]).filter(([, value]) => value !== undefined));
  const curve = entry.points || entry.mix?.[0]?.points || defaultCurve;
  if (mode === "fixed") return { mode, role, percent: entry.percent ?? (pump ? 90 : 60), preset: "", stall_detect: entry.stall_detect ?? true };
  const base = { mode, role, ...tuning, stall_detect: entry.stall_detect ?? true };
  if (pump && base.min_percent === undefined) base.min_percent = 50;
  if (mode === "curve") return { ...base, source: entry.source || "hottest", points: curve };
  return { ...base, mix: entry.mix || [{ source: "gpu", points: curve }, { source: "vrm", points: curve }] };
}

/** The desktop's FanCurvePlot: filled curve, numbered points to drag, the live operating point. */
export function CurvePlot({ points, onChange, temp, target, sensor, pwm, disabled }) {
  const svg = useRef(null), [drag, setDrag] = useState(-1);
  const w = 520, h = 230, lo = 30, hi = 95, left = 40, right = 12, top = 30, bottom = 26;
  const x = (v) => left + ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (w - left - right);
  const y = (v) => top + (1 - v / 100) * (h - top - bottom);
  const sorted = [...points].sort((a, b) => a[0] - b[0]);
  const line = [[lo, sorted[0]?.[1] ?? 0], ...sorted, [hi, sorted.at(-1)?.[1] ?? 100]];
  const path = line.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join("");
  const move = (event) => {
    if (drag < 0 || !onChange) return;
    const box = svg.current.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * w, py = ((event.clientY - box.top) / box.height) * h;
    const before = sorted[drag - 1], after = sorted[drag + 1];
    const temperature = Math.round(Math.max(before ? before[0] + 1 : 20, Math.min(after ? after[0] - 1 : 110, lo + ((px - left) / (w - left - right)) * (hi - lo))));
    const duty = Math.round(Math.max(0, Math.min(100, (1 - (py - top) / (h - top - bottom)) * 100)));
    onChange(sorted.map((point, index) => (index === drag ? [temperature, duty] : point)));
  };
  const live = temp != null && target != null;
  return (
    <svg ref={svg} className="fan-plot" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("Drag a point to move it.")} style={{ touchAction: "none" }}
      onPointerMove={move} onPointerUp={() => setDrag(-1)} onPointerLeave={() => setDrag(-1)}>
      <rect x={left} y={top} width={w - left - right} height={h - top - bottom} className="fan-plot-bg" />
      {[0, 20, 40, 60, 80, 100].map((v) => <g key={v}><line x1={left} x2={w - right} y1={y(v)} y2={y(v)} className="fan-plot-grid" /><text x={left - 6} y={y(v) + 3} textAnchor="end" className="fan-plot-axis">{v}%</text></g>)}
      {[30, 40, 50, 60, 70, 80, 90].map((v) => <g key={v}><line x1={x(v)} x2={x(v)} y1={top} y2={h - bottom} className="fan-plot-grid" /><text x={x(v)} y={h - 8} textAnchor="middle" className="fan-plot-axis">{v} °C</text></g>)}
      <path d={`${path}L${x(hi)},${y(0)}L${x(lo)},${y(0)}Z`} className="fan-plot-fill" />
      <path d={path} className="fan-plot-line" />
      {live && <>
        <line x1={x(temp)} x2={x(temp)} y1={top} y2={h - bottom} className="fan-plot-now" />
        <circle cx={x(temp)} cy={y(target)} r="4" className="fan-plot-dot" />
        <g transform={`translate(${Math.max(left + 72, Math.min(w - right - 72, x(temp)))},${top - 16})`}>
          <rect x="-72" y="-10" width="144" height="18" rx="4" className="fan-plot-tag" />
          <text textAnchor="middle" y="3" className="fan-plot-tag-text">{`PWM ${pwm} · ${sensor ? `${String(sensor).toUpperCase()} ` : ""}${temp.toFixed(1)} °C → ${target}%`}</text>
        </g></>}
      {sorted.map((p, i) => <g key={i} style={{ cursor: disabled ? "default" : "grab" }}
        onPointerDown={(event) => { if (disabled || !onChange) return; svg.current.setPointerCapture?.(event.pointerId); setDrag(i); }}>
        <circle cx={x(p[0])} cy={y(p[1])} r={drag === i ? 10 : 8} className="fan-plot-point" />
        <text x={x(p[0])} y={y(p[1]) + 3} textAnchor="middle" className="fan-plot-point-text">{i + 1}</text></g>)}
    </svg>
  );
}

const NumberCell = ({ value, min, max, unit, onChange, disabled, name }) => (
  <label className="fan-number"><input className="input" type="number" inputMode="numeric" aria-label={name} min={min} max={max} value={value} disabled={disabled}
    onChange={(event) => event.target.value !== "" && onChange(Math.max(min, Math.min(max, Number(event.target.value))))} /><span>{unit}</span></label>
);

/** The desktop's point table: temperature, PWM, Remove; Add point under it. */
function Points({ points, onChange, disabled }) {
  const sorted = [...points].sort((a, b) => a[0] - b[0]);
  const edit = (index, column, value) => onChange(sorted.map((point, j) => (j === index ? (column ? [point[0], value] : [value, point[1]]) : point)));
  return <div className="fan-points">
    <div className="fan-points-head"><span>{t("Temperature")} (°C)</span><span>{t("PWM %")}</span><span /></div>
    {sorted.map((point, index) => <div className="fan-points-row" key={index}>
      <NumberCell name={`#${index + 1} ${t("Temperature")}`} min={20} max={110} value={point[0]} unit="°C" disabled={disabled} onChange={(value) => edit(index, 0, value)} />
      <NumberCell name={`#${index + 1} ${t("PWM %")}`} min={0} max={100} value={point[1]} unit="%" disabled={disabled} onChange={(value) => edit(index, 1, value)} />
      <Btn small disabled={disabled || sorted.length <= 2} onClick={() => onChange(sorted.filter((_, j) => j !== index))}>{t("Remove")}</Btn></div>)}
    <div><Btn small disabled={disabled || sorted.length >= 8} onClick={() => { const last = sorted.at(-1) || [50, 50]; onChange([...sorted, [Math.min(110, last[0] + 5), Math.min(100, last[1] + 5)]]); }}>{t("Add point")}</Btn></div>
  </div>;
}

const Select = ({ title, value, options, onChange, disabled }) => (
  <label className="fan-form-row"><span>{title}</span><select className="input" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    {options.map(([key, text]) => <option key={key} value={key}>{t(text)}</option>)}</select></label>
);

/** One channel's editor, as the desktop's: name, mode, function, its setting, Advanced, Revert / Apply. */
export function ChannelEditor({ data, row, draft, setDraft, dirty, onApply, onRevert, onRename, locked }) {
  const { live } = useApp();
  const [advanced, setAdvanced] = useState(false);
  const [member, setMember] = useState(0);
  const [name, setName] = useState(row.label);
  useEffect(() => setName(row.label), [row.pwm, row.label]);
  const set = (changes) => setDraft({ ...draft, ...changes });
  const mode = draft.mode, curve = draft.points || [], members = draft.mix || [];
  const metrics = live?.metrics || {};
  const reading = { gpu: metrics.gpu?.temperature_c, cpu: metrics.cpu?.temperature_c, vrm: metrics.sensors?.vrm_temperature_c, board: metrics.sensors?.board_temperature_c };
  const fallback = mode === "curve" ? (draft.source === "hottest" ? Math.max(...Object.values(reading).filter((v) => typeof v === "number")) : reading[draft.source]) : null;
  const temp = row.temperature ?? (typeof fallback === "number" && isFinite(fallback) ? fallback : null);
  const disabled = locked || data.external;
  const note = data.external ? t("The fan is handed to another program. Nothing here writes to it.")
    : !row.writable ? t("This channel is read-only until the PWM driver is prepared.")
      : !data.service.enabled && (mode === "curve" || mode === "mix") ? t("Curves are followed by control from boot. Without it, only the desktop follows one curve, after you log in.") : "";
  const rename = () => { const text = name.trim().replace(/\s+/g, " "); if (text !== row.label) onRename(text); };
  const floor = draft.role === "pump" ? 30 : 0;
  return <div className="fan-editor">
    <div className="fan-editor-card">
      <div className="fan-editor-head"><h3>{editorTitle(row)}</h3><b>{num(row.rpm)} RPM · {row.duty ?? "--"} %</b></div>
      <p className="fan-editor-sub">PWM {row.pwm} · {row.header}{row.bios ? ` · ${t("BIOS Fan {number}", { number: row.bios })}` : ""}</p>
      <label className="fan-form-row"><span>{t("Name")}</span><input className="input" maxLength={40} value={name} placeholder={t("Name this fan")} disabled={disabled}
        onChange={(event) => setName(event.target.value)} onBlur={rename} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} /></label>
      <Select title={t("Mode")} value={mode} options={MODES} disabled={disabled} onChange={(key) => setDraft(withMode(draft, key, data.default_curve))} />
      {mode !== "firmware" && <Select title={t("Function")} value={draft.role || "fan"} options={ROLES} disabled={disabled}
        onChange={(role) => set({ role, ...(role === "pump" && mode === "fixed" && draft.percent < 30 ? { percent: 30 } : {}), ...(role === "pump" && mode !== "fixed" && (draft.min_percent ?? 0) < 30 ? { min_percent: 50 } : {}) })} />}
      {mode === "firmware" && <p className="note">{t("The BIOS fan curve drives this header. BC250 Control Center does not write to it.")}</p>}
      {mode === "fixed" && <>
        <label className="fan-form-row"><span>{t("Speed")}</span><div className="fan-speed">
          <input className="range" type="range" min={floor} max="100" step="5" value={draft.percent} disabled={disabled} aria-label={t("Speed")} onChange={(event) => set({ percent: Number(event.target.value) })} />
          <NumberCell name={t("Speed")} min={floor} max={100} value={draft.percent} unit="%" disabled={disabled} onChange={(percent) => set({ percent })} /></div></label>
        <p className="note">{t("Raw PWM {raw} / 255", { raw: Math.round(draft.percent * 255 / 100) })}</p>
      </>}
      {mode === "curve" && <>
        <Select title={t("Follows")} value={draft.source} options={SOURCES} disabled={disabled} onChange={(source) => set({ source })} />
        <CurvePlot points={curve} onChange={(points) => set({ points })} temp={temp} target={row.target} sensor={row.sensor} pwm={row.pwm} disabled={disabled} />
        <Points points={curve} onChange={(points) => set({ points })} disabled={disabled} />
      </>}
      {mode === "mix" && <>
        <p className="note">{t("The fan takes the highest PWM of these curves, each on its own sensor.")}</p>
        {(() => {
          const index = Math.min(member, members.length - 1), current = members[index];
          if (!current) return null;
          const update = (changes) => set({ mix: members.map((item, j) => (j === index ? { ...item, ...changes } : item)) });
          return <>
            <label className="fan-form-row"><span>{t("Curve")}</span><select className="input" value={index} disabled={disabled} onChange={(event) => setMember(Number(event.target.value))}>
              {members.map((item, j) => <option key={j} value={j}>{`${j + 1} · ${label(SOURCES, item.source)}`}</option>)}</select></label>
            <Select title={t("Follows")} value={current.source} options={SOURCES} disabled={disabled} onChange={(source) => update({ source })} />
            <CurvePlot points={current.points} onChange={(points) => update({ points })} pwm={row.pwm} disabled={disabled} />
            <Points points={current.points} onChange={(points) => update({ points })} disabled={disabled} />
          </>;
        })()}
        <div className="row"><Btn small disabled={disabled || members.length >= 4} onClick={() => { set({ mix: [...members, { source: "board", points: data.default_curve }] }); setMember(members.length); }}>{t("Add curve")}</Btn>
          <Btn small disabled={disabled || members.length <= 2} onClick={() => { set({ mix: members.filter((_, j) => j !== Math.min(member, members.length - 1)) }); setMember(0); }}>{t("Remove curve")}</Btn></div>
      </>}
      {mode !== "firmware" && <div className="row"><Btn small aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{t("Advanced")}</Btn></div>}
      {mode !== "firmware" && advanced && <div className="fan-advanced">
        {(mode === "curve" || mode === "mix") && ADVANCED.map(([key, text, low, high, unit]) => (
          <div className="fan-form-row" key={key}><span>{t(text)}</span><NumberCell name={t(text)} min={key === "min_percent" ? Math.max(low, floor) : low} max={high} unit={unit} disabled={disabled}
            value={draft[key] ?? ""} onChange={(value) => set({ [key]: value })} /></div>))}
        <label className="check"><input type="checkbox" checked={draft.stall_detect ?? true} disabled={disabled} onChange={(event) => set({ stall_detect: event.target.checked })} />{t("Warn when the fan stops while it should turn")}</label>
      </div>}
      {note && <p className="note warn">{note}</p>}
    </div>
    <div className="fan-editor-actions"><Btn disabled={disabled || !dirty} onClick={onRevert}>{t("Revert")}</Btn>
      <Btn kind="soft" disabled={disabled || !dirty || (!row.writable && (mode === "fixed" || mode === "firmware") && !data.service.enabled)} onClick={onApply}>{t("Apply")}</Btn></div>
  </div>;
}

/** The desktop's on/off switch. */
const Switch = ({ on, disabled, onChange, children }) => (
  <button type="button" role="switch" aria-checked={on} className={`fan-switch ${on ? "on" : ""}`} disabled={disabled} onClick={onChange}><i /><span>{children}</span></button>
);

/** The desktop's top bar: Profile, Apply profile, Save as…, Control from boot, More. */
export function ProfileBar({ data, selected, draft, dirty, locked }) {
  const { act } = useApp();
  const { profiles, service } = data;
  const initial = profiles.active || (profiles.custom ? "" : "Balanced");
  const [choice, setChoice] = useState(initial);
  useEffect(() => setChoice(initial), [initial]);
  const [naming, setNaming] = useState(null);
  const options = [...(profiles.custom ? [["", keep("Custom")]] : []), ...profiles.builtin.map((name) => [name, name]), ...profiles.saved.map((name) => [name, name])];
  const on = service.enabled;
  const boot = t(on ? "Turn off control from boot" : "Turn on control from boot");
  const canToggle = !locked && !data.external && (on || (service.available && service.has_policy));
  const save = () => {
    const name = (naming || "").trim().replace(/\s+/g, " ");
    if (!name) return;
    const replace = profiles.saved.some((item) => item.toLowerCase() === name.toLowerCase());
    act({ action: "fan.profile", level: 1, title: t("Save as…"), body: replace ? t("Replace fan profile?") : name,
      params: { operation: "save", name, replace, ...(dirty ? { draft: { pwm: selected, entry: draft.mode === "firmware" ? null : draft } } : {}) } });
    setNaming(null);
  };
  const more = [
    ...(on ? [{ key: "sync", title: t("Sync now"), available: !locked && service.has_policy }] : []),
    ...(profiles.saved.includes(choice) ? [{ key: "delete", title: `${t("Delete")} · ${choice}`, available: !locked }] : []),
  ];
  return <div className="fan-bar">
    <div className="fan-bar-row">
      <label className="fan-bar-profile"><span>{t("Profile")}</span><select className="input" value={choice} disabled={locked || data.external} onChange={(event) => setChoice(event.target.value)}>
        {options.map(([key, text]) => <option key={key} value={key}>{t(text)}</option>)}</select></label>
      <Btn kind="soft" disabled={locked || data.external || !choice} onClick={() => act({ action: "fan.profile", level: 1, title: t("Apply profile"), body: t(choice),
        warning: dirty ? t("The changes to this fan were not applied.") : undefined, params: { operation: "apply", name: choice, selected } })}>{t("Apply profile")}</Btn>
      <Btn disabled={locked || data.external} onClick={() => setNaming(naming === null ? "" : null)}>{t("Save as…")}</Btn>
      <span className="fan-bar-gap" />
      <Switch on={on} disabled={!canToggle} onChange={() => act({ action: "fan.service", level: 1, title: boot, params: { operation: on ? "disable" : "enable" } })}>{t("Control from boot")}</Switch>
      {more.length > 0 && <Menu label={t("More")} items={more} onPick={(key) => key === "sync"
        ? act({ action: "fan.service", level: 1, title: t("Sync now"), params: { operation: "sync" } })
        : act({ action: "fan.profile", level: 1, title: t("Delete"), body: choice, params: { operation: "delete", name: choice } })} />}
    </div>
    {naming !== null && <div className="fan-bar-row"><input className="input" autoFocus maxLength={32} value={naming} placeholder={t("Profile")} onChange={(event) => setNaming(event.target.value)}
      onKeyDown={(event) => { if (event.key === "Enter") save(); if (event.key === "Escape") setNaming(null); }} /><Btn kind="soft" disabled={!naming.trim()} onClick={save}>{t("Save")}</Btn><Btn onClick={() => setNaming(null)}>{t("Cancel")}</Btn></div>}
    <p className={`fan-status ${toneClass(service.tone)}`}>{say(service.summary, service.summary_values)}</p>
  </div>;
}

/** Selection, the draft of the selected channel and the guarded switch between channels. */
export function useFanBoard(data) {
  const { act } = useApp();
  const rows = data?.channels || [];
  const [selected, setSelected] = useState(null);
  const [draft, setDraftState] = useState(null);
  const [asking, setAsking] = useState(null);
  const row = rows.find((item) => item.pwm === selected) || rows.find((item) => item.detected && item.rpm > 0) || rows.find((item) => item.detected) || rows[0];
  const saved = JSON.stringify(row?.entry || {});
  const [edited, setEdited] = useState(false);
  // A new channel, or its saved setting changed (after an Apply or a profile): the draft starts again.
  useEffect(() => { if (row) { setDraftState(row.entry); setEdited(false); } }, [row?.pwm, saved]);  // eslint-disable-line react-hooks/exhaustive-deps
  const setDraft = (value) => { setDraftState(value); setEdited(true); };
  const discard = () => { setDraftState(row?.entry || null); setEdited(false); };
  const current = draft || row?.entry || { mode: "firmware" };
  const dirty = edited && JSON.stringify(current) !== saved;
  const apply = () => {
    if (!row) return;
    const entry = current.mode === "firmware" ? null : current;
    const low = !data.service.enabled && current.mode === "fixed" && current.percent < data.low_duty;
    act({ action: "fan.channel", level: low ? 2 : 1, title: low ? t("Apply a low fan speed") : t("Apply"),
      body: low ? t("A fan this slow can let the board overheat under load.") : `PWM ${row.pwm} · ${channelName(row)}`,
      summary: [[t("Channel"), `PWM ${row.pwm}`], [t("Mode"), label(MODES, current.mode)], ...(current.mode === "fixed" ? [[t("Speed"), `${current.percent} %`]] : [])],
      params: { pwm: row.pwm, entry } });
  };
  const choose = (pwm) => { if (pwm === row?.pwm) return; if (dirty) { setAsking(pwm); return; } setSelected(pwm); };
  const answer = (choice) => {
    const target = asking;
    setAsking(null);
    if (choice === "cancel") return;
    if (choice === "apply") apply();
    setSelected(target);
  };
  const editor = (locked) => row && <>
    {asking !== null && <div className="notice fan-unapplied" role="alert"><b>{t("Unapplied changes")}</b><span>{t("The changes to this fan were not applied.")}</span>
      <div className="row"><Btn small onClick={() => answer("cancel")}>{t("Cancel")}</Btn><Btn small onClick={() => answer("discard")}>{t("Discard")}</Btn><Btn small kind="soft" onClick={() => answer("apply")}>{t("Apply")}</Btn></div></div>}
    <ChannelEditor key={row.pwm} data={data} row={row} draft={current} setDraft={setDraft} dirty={dirty} locked={locked}
      onApply={apply} onRevert={discard}
      onRename={(text) => act({ action: "fan.label", level: 0, title: t("Name"), params: { pwm: row.pwm, label: text } })} />
  </>;
  return { rows, row, selected: row?.pwm ?? null, choose, draft: current, dirty, discard, editor };
}

export const modeText = (item) => `${t(item.mode_label)}${item.role === "pump" && item.mode !== "firmware" ? ` · ${t("Pump")}` : ""}`;
export const footer = (data) => [t("{count} channels", { count: data.counts.channels }), t("{count} turning", { count: data.counts.turning }), t("{count} controlled", { count: data.counts.controlled }), data.chip].filter(Boolean).join(" · ");

export default function Fans() {
  const mobile = useMobile();
  const { live, running } = useApp();
  const data = usePage("fans");
  const board = useFanBoard(data);
  if (!data?.channels) return <Card title={t("Fans")}><p className="note">{t("Waiting for data…")}</p></Card>;
  if (!mobile) return <DesktopFans data={data} board={board} />;
  const m = live?.metrics || {}, gpu = m.gpu || {}, cpu = m.cpu || {}, sensors = m.sensors || {};
  const { rows, row } = board;
  return (
    <div className="fan-page fan-phone">
      <Card>
        <ProfileBar data={data} selected={board.selected} draft={board.draft} dirty={board.dirty} locked={running} />
        {data.driver && <p className="note warn">{t(data.driver)}</p>}
        <div className="fan-list" role="listbox" aria-label={t("Channel")}>{rows.map((item) => (
          <button key={item.pwm} type="button" role="option" aria-selected={item.pwm === row?.pwm} className={`fan-list-row ${item.pwm === row?.pwm ? "on" : ""}`} onClick={() => board.choose(item.pwm)}>
            <span className="fan-list-name"><b>{channelName(item)}</b><small>PWM {item.pwm}{item.bios ? ` · BIOS ${item.bios}` : ""}</small></span>
            <span className="fan-list-mode">{modeText(item)}<small className={toneClass(item.tone)}>{say(item.state)}</small></span>
            <span className="fan-list-num"><b>{item.duty ?? "--"}</b> %<small>{num(item.rpm)} RPM</small></span>
          </button>))}</div>
        <p className="fan-footer">{footer(data)}</p>
      </Card>
      {row && board.editor(running)}
      <Card title={t("Thermal detail")}><div className="reads">
        <Read label="GPU" value={num(gpu.temperature_c, 1)} unit="°C" /><Read label="CPU" value={num(cpu.temperature_c, 1)} unit="°C" />
        <Read label={t("Board")} value={num(sensors.board_temperature_c, 1)} unit="°C" /><Read label="VRM MOS" value={num(sensors.vrm_mos_temperature_c, 1)} unit="°C" />
        <Read label="M.2 SSD" value={num(sensors.nvme_temperature_c, 1)} unit="°C" /></div></Card>
    </div>
  );
}
