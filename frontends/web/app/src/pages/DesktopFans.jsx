import { useState } from "react";
import { num, t, useApp } from "../lib.jsx";
import { Btn, Card, Check, ControlTabs, Number_, Read, Segments, Tile } from "../ui.jsx";

/** PC layout only; commands and curve drafts are shared with the mobile page. */
export default function DesktopFans({ data, rows, row, pwm, setPwm, writable, ready, duty, tab, setTab, percent, setPercent, presets, sorted, edit, setPoints, auto, setAuto, plot, service, serviceAction, bootOperation, bootTitle, names, curves, serviceStates, lowDuty }) {
  const [view, setView] = useState("control");
  const { act, live, running } = useApp();
  const { gpu = {}, cpu = {}, sensors = {} } = live?.metrics || {};
  const mode = fan => fan.pwm_enable === 2 ? "Firmware (BIOS)" : fan.pwm_enable === 1 ? t("Manual") : t("Automatic");
  const locked = !ready || running;
  const readings = [["GPU", gpu.temperature_c, "°C"], ["CPU", cpu.temperature_c, "°C"], [t("Board"), sensors.board_temperature_c, "°C"], ["VRM MOS", sensors.vrm_mos_temperature_c, "°C"], ["M.2 SSD", sensors.nvme_temperature_c, "°C"], [t("Fan speed"), row.rpm, "RPM"]];
  return <div className="desktop-layout desktop-fans">
    <ControlTabs items={[["control", t("Hardware control"), "nav_fans"], ["sensors", t("Sensors"), "nav_performance"]]} value={view} onChange={setView} />
    {view === "control" ? <>
      <section className="card desktop-fan-channel">
        <label className="field"><span>{t("PWM channel")}</span><select className="input" value={pwm} onChange={event => setPwm(Number(event.target.value))}>{(writable.length ? writable : rows).map(fan => <option key={fan.index} value={fan.index}>PWM {fan.index} · {fan.label}</option>)}</select></label>
        <div className="desktop-fan-reading"><span>{t("Speed")}</span><b>{num(row.rpm)} <small>RPM</small></b></div>
        <div className="desktop-fan-reading"><span>{t("Current duty")}</span><b>{duty ?? "--"} <small>%</small></b></div>
        <div className="desktop-fan-reading"><span>{t("PWM mode")}</span><b>{mode(row)}</b></div>
      </section>
      <div className="desktop-fan-columns">
        <Card className="desktop-fan-tuning">
          <Segments items={[{ key: "manual", title: t("Manual") }, { key: "curve", title: t("Automatic curve") }]} value={tab} onChange={setTab} />
          {tab === "manual" ? <>
            <div className="desktop-fan-duty"><span>{t("Fan speed")}</span><Number_ label={t("Selection")} min={0} max={100} value={percent} unit="%" onChange={value => setPercent(Math.max(0, Math.min(100, value || 0)))} /></div>
            <input className="range" type="range" min="0" max="100" step="5" value={percent} aria-label={t("Fan speed")} onChange={event => setPercent(Number(event.target.value))} />
            <p className="note">{t("Raw PWM {raw} / 255", { raw: Math.round(percent * 255 / 100) })}</p>
            <div className="tiles desktop-fan-presets">{presets.map(([key, value]) => <Tile key={key} label={t(names[key] || key)} value={`${value} %`} on={percent === value} onClick={() => setPercent(value)} />)}</div>
            <div className="desktop-action-row"><Btn disabled={locked} onClick={() => act({ action: "fan.auto", level: 1, params: { pwm }, title: t("Restore automatic mode") })}>{t("Restore automatic mode")}</Btn><Btn kind="primary" disabled={locked} onClick={() => act({ action: "fan.pwm", level: percent < lowDuty ? 2 : 1, params: { pwm, percent }, title: percent < lowDuty ? t("Apply a low fan speed") : t("Apply PWM"), body: `PWM ${pwm} · ${percent} %` })}>{t("Apply PWM")}</Btn></div>
          </> : <>
            <div className="desktop-fan-curve-presets"><Check checked={auto} onChange={setAuto}>{t("Automatic curve")}</Check><div className="row">{Object.entries(curves).map(([name, values]) => <Btn key={name} small onClick={() => { setPoints(values); setAuto(true); }}>{t(names[name])}</Btn>)}</div></div>
            <div className="desktop-fan-curve"><div>{plot}</div><div className="desktop-fan-points"><div className="desktop-fan-points-head"><span /><span>{t("Temperature")}</span><span>{t("PWM duty")}</span></div>{sorted.map((point, index) => <div key={index}><b>#{index + 1}</b><Number_ label={t("Temperature")} min={20} max={110} value={point[0]} unit="°C" onChange={value => edit(index, 0, value)} /><Number_ label={t("PWM duty")} min={0} max={100} value={point[1]} unit="%" onChange={value => edit(index, 1, value)} /></div>)}</div></div>
            <div className="desktop-fan-curve-actions"><Btn small disabled={sorted.length >= 8} onClick={() => { const last = sorted.at(-1) || [50, 50]; setPoints([...sorted, [Math.min(110, last[0] + 5), Math.min(100, last[1] + 5)]]); }}>{t("Add point")}</Btn><Btn small disabled={sorted.length <= 2} onClick={() => setPoints(sorted.slice(0, -1))}>{t("Remove point")}</Btn><Btn kind="primary" disabled={locked} onClick={() => act({ action: "fan.curve", level: 1, params: { pwm, enabled: auto, points: sorted }, title: t("Save curve") })}>{t("Save curve")}</Btn></div>
          </>}
          {!ready && <p className="note">{data.external ? t("The fan is handed to another program. Nothing here writes to it.") : t("PWM control is not ready")}</p>}
        </Card>
        <div className="desktop-fan-side"><Card className="desktop-fan-policy" title={t("Boot persistence")}>
          <div className="reads"><Read label={t("State")} value={data.external ? t("Another program") : service.out_of_date ? t("Out of date") : t(serviceStates[service.state] || "Stopped")} /><Read label={t("Boot persistence")} value={t(service.enabled ? "Enabled" : "Disabled")} /><Read label={t("Fan controlled by")} value={data.owner} /></div>
          {tab === "curve" && !service.enabled && <Btn kind="primary" disabled={locked || !auto || !service.available} onClick={() => act({ action: "fan.curve", level: 1, params: { pwm, enabled: auto, points: sorted, start_service: true }, title: `${t("Save curve")} + ${t("Turn on control from boot")}` })}>{t("Save curve")} + {t("Turn on control from boot")}</Btn>}
          <div className="desktop-action-row"><Btn disabled={running || data.external || !service.enabled && (!service.available || !service.has_policy)} onClick={() => serviceAction(bootOperation, bootTitle)}>{bootTitle}</Btn><Btn disabled={running || data.external || !service.enabled || !service.has_policy} onClick={() => serviceAction("sync", t("Sync now"))}>{t("Sync now")}</Btn></div>
          {data.external ? <p className="note">{t("The fan is handed to another program. Nothing here writes to it.")}</p> : !service.available && !service.enabled ? <p className="note">{t("Needs the installed BC250 Control Center package and systemd or OpenRC.")}</p> : !service.has_policy && <p className="note">{t("Choose a curve or a preset first")}</p>}
        </Card><Card className="desktop-fan-thermal" title={t("Thermal detail")}><div className="desktop-specs">{readings.slice(0, 4).map(([label, value, unit]) => <Read key={label} label={label} value={num(value, 1)} unit={unit} />)}</div></Card></div>
      </div>
    </> : <>
      <Card title={t("Thermal detail")}><div className="desktop-sensor-tiles">{readings.map(([label, value, unit]) => <div className="tile" key={label}><small>{label}</small><strong>{num(value, unit === "RPM" ? 0 : 1)} {unit}</strong></div>)}</div></Card>
      <Card title={t("PWM channel")}><div className="desktop-fan-channels">{rows.map(fan => <section className="desktop-inset" key={fan.index}><h3>PWM {fan.index} · {fan.label}</h3><Read label={t("Speed")} value={num(fan.rpm)} unit="RPM" /><Read label={t("PWM duty")} value={Number.isInteger(fan.pwm) ? Math.round(fan.pwm * 100 / 255) : "--"} unit="%" /><Read label={t("PWM mode")} value={mode(fan)} /></section>)}</div></Card>
    </>}
  </div>;
}
