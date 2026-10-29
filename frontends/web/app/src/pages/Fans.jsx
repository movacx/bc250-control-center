import { useEffect, useState } from "react";
import { keep, num, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, Number_, Read, Segments, Tile } from "../ui.jsx";

const LOW_DUTY = 30;
const NAMES = { quiet: keep("Quiet"), balanced: keep("Balanced"), cooling: keep("Cooling"), maximum: keep("Maximum"), silent: keep("Silent"), aggressive: keep("Aggressive"), performance: keep("Performance") };
const CURVES = { silent: [[45, 40], [55, 50], [65, 65], [72, 85], [78, 100]], balanced: [[40, 50], [50, 60], [60, 75], [67, 90], [74, 100]], aggressive: [[40, 60], [48, 70], [56, 82], [63, 92], [70, 100]] };

function CurvePlot({ points, temp }) {
  const w = 480, h = 180, lo = Math.min(...points.map((p) => p[0])) - 5, hi = Math.max(...points.map((p) => p[0])) + 5;
  const x = (v) => 34 + ((v - lo) / (hi - lo)) * (w - 44), y = (v) => 10 + (1 - v / 100) * (h - 34);
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t("Automatic curve")} style={{ height: "auto" }}>
      {[0, 25, 50, 75, 100].map((v) => <g key={v}><line x1="34" x2={w - 10} y1={y(v)} y2={y(v)} stroke="var(--c-chart-grid)" /><text x="28" y={y(v) + 4} fontSize="10" textAnchor="end" fill="var(--c-muted)">{v}</text></g>)}
      <path d={points.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join("")} fill="none" stroke="var(--c-blue)" strokeWidth="2" />
      {points.map((p, i) => <circle key={i} cx={x(p[0])} cy={y(p[1])} r="4" fill="var(--c-blue)" />)}
      {temp != null && temp >= lo && temp <= hi && <line x1={x(temp)} x2={x(temp)} y1="10" y2={h - 24} stroke="var(--c-orange)" strokeDasharray="4 3" />}
      {[lo, hi].map((v) => <text key={v} x={x(v)} y={h - 8} fontSize="10" textAnchor="middle" fill="var(--c-muted)">{Math.round(v)} °C</text>)}
    </svg>
  );
}

export default function Fans() {
  const { act, live } = useApp();
  const data = usePage("fans");
  const [tab, setTab] = useState("manual");
  const [pwm, setPwm] = useState(null);
  const [percent, setPercent] = useState(60);
  const [points, setPoints] = useState(null);
  const [auto, setAuto] = useState(false);
  useEffect(() => { if (data && pwm === null) { setPwm(data.curve.pwm || data.rows[0]?.index || 2); setPoints((data.curve.points || []).map((p) => [p.temperature, p.speed])); setAuto(!!data.curve.enabled); } }, [data, pwm]);
  if (!data || pwm === null) return <Card title={t("Fans")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const m = live?.metrics || {}, gpu = m.gpu || {}, cpu = m.cpu || {}, sensors = m.sensors || {};
  const rows = data.rows, row = rows.find((r) => r.index === pwm) || rows[0] || {};
  const writable = rows.filter((r) => r.pwm_root_writable || r.pwm_writable), ready = !!(row.pwm_root_writable || row.pwm_writable) && !data.external;
  const duty = Number.isInteger(row.pwm) ? Math.round(row.pwm * 100 / 255) : null;
  const sorted = [...(points || [])].sort((a, b) => a[0] - b[0]);
  const edit = (i, k, v) => setPoints(sorted.map((p, j) => (j === i ? (k ? [p[0], v] : [v, p[1]]) : p)));
  const presets = Object.entries(data.presets).map(([key, value]) => [key, value]);
  return (
    <div className="cols fan-split">
      <Card title={t("Fan")} sub={`${t("Fan controlled by")}: ${data.owner}`}>
        <label className="field"><span>{t("PWM channel")}</span><select className="input" value={pwm} onChange={(e) => setPwm(Number(e.target.value))}>
          {(writable.length ? writable : rows).map((r) => <option key={r.index} value={r.index}>PWM {r.index} · {r.label}</option>)}</select></label>
        <div className="reads"><Read label={t("Speed")} value={num(row.rpm)} unit="RPM" />
          <div className="read"><span>{t("Current duty")}</span><div className="bar" style={{ flex: 1, margin: "0 12px", alignSelf: "center" }}><i style={{ width: `${duty || 0}%` }} /></div><div><b>{duty ?? "--"}</b><em>%</em></div></div>
          <Read label={t("PWM mode")} value={row.pwm_enable === 2 ? "Firmware (BIOS)" : row.pwm_enable === 1 ? t("Manual") : t("Automatic")} /></div>
        <Segments items={[{ key: "manual", title: t("Manual") }, { key: "curve", title: t("Automatic curve") }]} value={tab} onChange={setTab} />
        {tab === "manual" ? <>
          <div className="row" style={{ justifyContent: "space-between" }}><b>{t("Fan speed")}</b><Number_ label="" min={0} max={100} value={percent} unit="%" onChange={(v) => setPercent(Math.max(0, Math.min(100, v || 0)))} /></div>
          <input className="range" type="range" min="0" max="100" step="5" value={percent} aria-label={t("Fan speed")} onChange={(e) => setPercent(Number(e.target.value))} />
          <p className="note">{t("Raw PWM {raw} / 255", { raw: Math.round(percent * 255 / 100) })}</p>
          <div className="tiles">{presets.map(([key, value]) => <Tile key={key} label={t(NAMES[key] || key)} value={`${value} %`} on={percent === value} onClick={() => setPercent(value)} />)}</div>
          <div className="row"><Btn wide disabled={!ready} onClick={() => act({ action: "fan.auto", level: 1, params: { pwm }, title: t("Restore automatic mode") })}>{t("Restore automatic mode")}</Btn>
            <Btn kind="primary" wide disabled={!ready} onClick={() => act({ action: "fan.pwm", level: percent < LOW_DUTY ? 2 : 1, params: { pwm, percent }, title: percent < LOW_DUTY ? t("Apply a low fan speed") : t("Apply PWM"), body: `PWM ${pwm} · ${percent} %` })}>{t("Apply PWM")}</Btn></div>
          {!ready && <p className="note warn">{data.external ? t("The fan is handed to another program. Nothing here writes to it.") : t("PWM control is not ready")}</p>}
        </> : <>
          {sorted.length > 1 && <CurvePlot points={sorted} temp={gpu.temperature_c} />}
          <Check checked={auto} onChange={setAuto}>{t("Automatic curve")}</Check>
          <div className="row">{Object.entries(CURVES).map(([name, v]) => <Btn key={name} small onClick={() => { setPoints(v); setAuto(true); }}>{t(NAMES[name])}</Btn>)}</div>
          {sorted.map((p, i) => <div className="row" key={i}><b style={{ width: 24 }}>#{i + 1}</b><Number_ label="" min={20} max={110} value={p[0]} unit="°C" onChange={(v) => edit(i, 0, v)} /><Number_ label="" min={0} max={100} value={p[1]} unit="%" onChange={(v) => edit(i, 1, v)} /></div>)}
          <div className="row"><Btn small disabled={sorted.length >= 8} onClick={() => { const last = sorted[sorted.length - 1] || [50, 50]; setPoints([...sorted, [Math.min(110, last[0] + 5), Math.min(100, last[1] + 5)]]); }}>{t("Add point")}</Btn>
            <Btn small disabled={sorted.length <= 2} onClick={() => setPoints(sorted.slice(0, -1))}>{t("Remove point")}</Btn><span style={{ flex: 1 }} />
            <Btn kind="primary" disabled={!ready} onClick={() => act({ action: "fan.curve", level: 1, params: { pwm, enabled: auto, points: sorted }, title: t("Save curve") })}>{t("Save curve")}</Btn></div>
        </>}
      </Card>
      <Card title={t("Thermal detail")}><div className="reads">
        <Read label="GPU" value={num(gpu.temperature_c, 1)} unit="°C" /><Read label="CPU" value={num(cpu.temperature_c, 1)} unit="°C" />
        <Read label={t("Board")} value={num(sensors.board_temperature_c, 1)} unit="°C" /><Read label="VRM MOS" value={num(sensors.vrm_mos_temperature_c, 1)} unit="°C" />
        <Read label="M.2 SSD" value={num(sensors.nvme_temperature_c, 1)} unit="°C" /><Read label={t("Fan controlled by")} value={data.owner} /></div></Card>
    </div>
  );
}
