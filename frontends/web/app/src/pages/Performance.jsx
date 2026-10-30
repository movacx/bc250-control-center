import { useState } from "react";
import { api, t, usePoll } from "../lib.jsx";
import { Btn, HeatChart, LineChart, Menu, Pill, Segments } from "../ui.jsx";

const Chart = ({ chart, small }) => (chart.heatmap ? <HeatChart chart={chart} /> : <LineChart chart={chart} small={small} single={chart.series.length === 1} />);

function Resource({ data, state, set }) {
  const { views = [], legend = [], cards = [], chart } = data;
  const current = views.find((v) => v.key === data.view);
  return (
    <div className="pad">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="title"><b>{data.title}</b><b>{data.primary}</b><span>{data.context}</span></div>
        <div className="row">{views.length > 1 && <Menu label={current?.title || t("Views")} items={views} value={data.view} onPick={(view) => set({ view })} />}
          {data.percent && <Btn small onClick={() => set({ scale: state.scale === "fixed" ? "auto" : "fixed" })}>{state.scale === "fixed" ? "0–100 %" : t("Auto")}</Btn>}</div>
      </div>
      <p className="note">{data.hint}</p>
      {legend.length > 0 && legend.length <= 8 && !chart?.heatmap && <div className="legendrow">{legend.map((item, i) => (
        <span key={item.name}><i style={{ background: legend.length === 1 ? "var(--c-blue)" : `var(--c-series-${i + 1})` }} /><b>{item.name}</b> {t("min {value}", { value: item.min })} · {t("avg {value}", { value: item.avg })} · {t("max {value}", { value: item.max })}</span>))}</div>}
      {chart ? <Chart chart={chart} /> : <p className="note">{data.context}</p>}
      {cards.length > 0 && <div className="stat">{cards.map((c) => <div key={c.label}><small>{c.label}</small><b>{c.value}</b></div>)}</div>}
      <div className="row"><Pill tone="green">{t("Sampling")}</Pill><span className="note">{t("120 samples · 1 s cadence · 2 minute window")}</span><span style={{ flex: 1 }} /><span className="note">{t("Last sample {time}", { time: data.sampled })}</span></div>
    </div>
  );
}

function Sensors({ data, state, set }) {
  const { rows = [], traces = [], kinds = [], layouts = [] } = data;
  const layout = state.layout || "list";
  const ticked = state.ticked;
  const toggle = (key) => {
    const base = ticked ?? rows.filter((r) => r.ticked).map((r) => r.key);
    set({ ticked: base.includes(key) ? base.filter((k) => k !== key) : [...base, key] });
  };
  const [details, setDetails] = useState(false);
  return (
    <div className={`pad ${details ? "sensor-details" : ""}`}>
      <div className="sensor-tools"><input className="input sensor-search" placeholder={t("Filter by name")} aria-label={t("Filter by name")} value={state.q || ""} onChange={(e) => set({ q: e.target.value })} />
        <label className="check" style={{ fontSize: 12 }}><input type="checkbox" checked={state.hide !== "0"} onChange={(e) => set({ hide: e.target.checked ? "1" : "0" })} />{t("Hide unused channels")}</label>
        <Btn small onClick={() => setDetails(!details)} aria-pressed={details}>{t("Min")} / {t("Avg")} / {t("Max")}</Btn>
        <Btn small onClick={() => api("performance/reset", {})}>{t("Reset min/max")}</Btn>
        <Menu label={layouts.find((l) => l.key === layout)?.title || t("Views")} items={layouts} value={layout} onPick={(key) => set({ layout: key })} /></div>
      <div className="chips">{kinds.map((k) => <button key={k.index} className={`chip ${(state.kind || 0) === k.index ? "on" : ""}`} onClick={() => set({ kind: k.index })}><i style={{ background: `var(--c-series-${(k.index % 8) + 1})` }} />{k.title}</button>)}</div>
      {layout !== "graphs" && <div className="sensors sensor-desktop"><table><thead><tr><th>{t("Sensor")}</th><th>{t("Value")}</th><th>{t("Min")}</th><th>{t("Avg")}</th><th>{t("Max")}</th></tr></thead>
        <tbody>{rows.map((r) => (r.group ? <tr className="g" key={r.group + rows.indexOf(r)}><td colSpan="5">▾ {r.group}</td></tr>
          : <tr className="s" key={r.key} onDoubleClick={() => { toggle(r.key); set({ layout: "split" }); }}><td><label><input type="checkbox" checked={r.ticked} onChange={() => toggle(r.key)} />{r.label}</label></td><td className="v">{r.value}</td><td data-label={t("Min")}>{r.min}</td><td data-label={t("Avg")}>{r.avg}</td><td data-label={t("Max")}>{r.max}</td></tr>))}</tbody></table></div>}
      {layout !== "graphs" && <div className="sensor-mobile">{rows.map((r, index) => r.group ? <h3 className="sensor-group" key={`${r.group}-${index}`}>{r.group}</h3> : <div className="sensor-item" key={r.key}>
        <label><input type="checkbox" checked={r.ticked} onChange={() => toggle(r.key)} /><span>{r.label}</span><b>{r.value}</b></label>
        {details && <dl>{[[t("Min"), r.min], [t("Avg"), r.avg], [t("Max"), r.max]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
      </div>)}</div>}
      {layout !== "list" && (traces.length ? traces.map((trace) => <div key={trace.label}><div className="title"><b style={{ fontSize: 14 }}>{trace.label}</b><span>{trace.value}</span></div><Chart chart={trace.chart} small={layout === "split"} /></div>)
        : <p className="note">{t("Tick a sensor in the list to draw its last two minutes here.")}</p>)}
      <p className="note">{data.count}</p>
    </div>
  );
}

export default function Performance() {
  const [state, setState] = useState({ tab: "sensors" });
  const set = (patch) => setState((s) => ({ ...s, ...patch }));
  const query = new URLSearchParams({ tab: state.tab });
  const rule = state.tab === "sensors" ? { layout: state.layout, q: state.q, kind: state.kind, hide: state.hide, ticked: state.ticked?.join(",") } : { view: state[`view:${state.tab}`], scale: state.scale };
  Object.entries(rule).forEach(([k, v]) => v !== undefined && (v !== "" || k === "ticked") && query.set(k, v));
  const data = usePoll(`performance?${query}`, 1000, 0);
  return (
    <section className="card perf">
      <Segments items={data?.tabs || []} value={state.tab} onChange={(tab) => set({ tab })} />
      {!data || data.waiting || data.tab !== state.tab ? <p className="note pad">{t("Waiting for first sample")}</p>
        : state.tab === "sensors" ? <Sensors data={data} state={state} set={set} />
        : <Resource data={data} state={state} set={(patch) => set(patch.view ? { [`view:${state.tab}`]: patch.view } : patch)} />}
    </section>
  );
}
