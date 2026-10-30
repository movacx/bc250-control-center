import { useState } from "react";
import { api, t, usePoll } from "../lib.jsx";
import { Btn, HeatChart, Icon, LineChart, Menu, Pill, Segments, useMobile } from "../ui.jsx";

const Chart = ({ chart, small }) => chart ? (chart.heatmap ? <HeatChart chart={chart} /> : <LineChart chart={chart} small={small} single={chart.series.length === 1} />) : null;

function Resource({ data, state, set }) {
  const mobile = useMobile();
  const { views = [], legend = [], cards = [], chart } = data;
  const current = views.find((v) => v.key === data.view);
  return <div className="pad resource-view">
    <div className="resource-hero"><div><span className="resource-caption">{data.title}</span><strong>{data.primary}</strong><p>{data.context}</p></div><Pill tone={data._disconnected ? "orange" : "green"}>{t(data._disconnected ? "Not connected" : "Live")}</Pill></div>
    <div className="resource-controls">{views.length > 1 && (mobile ? <label className="field"><span>{t("Views")}</span><select className="input" value={data.view} onChange={(e) => set({ view: e.target.value })}>{views.map((v) => <option key={v.key} value={v.key} disabled={!v.available}>{v.title}</option>)}</select></label> : <Menu label={current?.title || t("Views")} items={views} value={data.view} onPick={(view) => set({ view })} />)}
      {data.percent && <Btn small onClick={() => set({ scale: state.scale === "fixed" ? "auto" : "fixed" })}>{state.scale === "fixed" ? "0–100 %" : t("Auto")}</Btn>}</div>
    {chart ? <Chart chart={chart} /> : <p className="note">{data.context}</p>}
    {legend.length > 0 && legend.length <= 8 && !chart?.heatmap && <div className="resource-legend">{legend.map((item, i) => <div key={item.name}><span><i style={{ background: legend.length === 1 ? "var(--c-blue)" : `var(--c-series-${i + 1})` }} />{item.name}</span><small>{t("min {value}", { value: item.min })} · {t("avg {value}", { value: item.avg })} · {t("max {value}", { value: item.max })}</small></div>)}</div>}
    {cards.length > 0 && <div className="stat">{cards.map((c) => <div key={c.label}><small>{c.label}</small><b>{c.value}</b></div>)}</div>}
    <details className="monitor-info"><summary>{t("Details")}</summary><p className="note">{data.hint}</p><p className="note">{t("120 samples · 1 s cadence · 2 minute window")}</p><p className="note">{t("Last sample {time}", { time: data.sampled })}</p></details>
  </div>;
}

function Statistics({ row }) {
  return <dl className="reading-statistics">{[[t("Min"), row.min], [t("Avg"), row.avg], [t("Max"), row.max]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>;
}

function Sensors({ data, state, set }) {
  const mobile = useMobile();
  const { rows = [], traces = [], kinds = [], layouts = [] } = data;
  const layout = state.layout || "list";
  const [details, setDetails] = useState(false), [expanded, setExpanded] = useState(null);
  const selected = state.ticked ?? data.ticked ?? rows.filter((r) => r.ticked).map((r) => r.key);
  const toggle = (key) => set({ ticked: selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key] });
  const reveal = (key) => { setExpanded(expanded === key ? null : key); if (!selected.includes(key)) set({ ticked: [...selected, key] }); };
  const filters = <div className="sensor-searchbar"><input className="input" placeholder={t("Filter by name")} aria-label={t("Filter by name")} value={state.q || ""} onChange={(e) => set({ q: e.target.value })} /><select className="input" aria-label={t("Sensors")} value={state.kind || 0} onChange={(e) => set({ kind: Number(e.target.value) })}>{kinds.map((kind) => <option key={kind.index} value={kind.index}>{kind.title}</option>)}</select></div>;
  return <div className="pad sensor-workspace">
    <div className="sensor-heading"><div><h2>{t("Sensors")}</h2><span>{data.count}</span></div><Pill tone={data._disconnected ? "orange" : "green"}>{t(data._disconnected ? "Not connected" : "Live")}</Pill></div>
    <div className="sensor-mode" aria-label={t("Views")}><button aria-pressed={layout === "list"} className={layout === "list" ? "on" : ""} onClick={() => set({ layout: "list" })}><Icon name="nav_processes" />{t("List")}</button><button aria-pressed={layout !== "list"} className={layout !== "list" ? "on" : ""} onClick={() => set({ layout: "graphs" })}><Icon name="nav_performance" />{t("Graphs")}<small>{selected.length}</small></button></div>
    {(!mobile || layout === "list") && filters}
    <details className="sensor-refine"><summary>{t("More")}</summary>{mobile && layout !== "list" && filters}<div className="sensor-tools"><label className="check"><input type="checkbox" checked={state.hide !== "0"} onChange={(e) => set({ hide: e.target.checked ? "1" : "0" })} />{t("Hide unused channels")}</label><Btn small onClick={() => setDetails(!details)} aria-pressed={details}>{t("Min")} / {t("Avg")} / {t("Max")}</Btn><Btn small onClick={() => api("performance/reset", {})}>{t("Reset min/max")}</Btn><Menu label={layouts.find((l) => l.key === layout)?.title || t("Views")} items={layouts} value={layout} onPick={(key) => set({ layout: key })} /></div></details>
    {layout !== "list" && mobile && <div className="sensor-trends">{traces.map((item) => <article className="sensor-trend" key={item.key}><header><div><h3>{item.label}</h3><strong>{item.value}</strong></div><Pill tone={item.fresh ? "green" : ""}>{item.fresh ? t("Live") : t("Not connected")}</Pill></header><Chart chart={item.chart} /><Statistics row={item} /></article>)}{(data.missing_traces || []).map((item) => <article className="sensor-trend" key={item.key}><h3>{item.label}</h3><p className="note">{t("Waiting for first sample")}</p></article>)}{!traces.length && !(data.missing_traces || []).length && <p className="note">{t("Tick a sensor in the list to draw its last two minutes here.")}</p>}</div>}

    {layout !== "graphs" && (mobile ? <div className="sensor-mobile">{rows.map((r, index) => r.group ? <h3 className="sensor-group" key={`${r.group}-${index}`}>{r.group}</h3> : <article className={`sensor-reading ${expanded === r.key ? "expanded" : ""}`} key={r.key}><div className="sensor-reading-row"><input type="checkbox" checked={selected.includes(r.key)} aria-label={`${t("Graphs")}: ${r.label}`} onChange={() => toggle(r.key)} /><button className="sensor-open" onClick={() => reveal(r.key)} aria-expanded={expanded === r.key}><span>{r.label}</span><b>{r.value}</b><Icon name="chevron_right_gray" /></button></div>{(details || expanded === r.key) && <Statistics row={r} />}{expanded === r.key && <Chart chart={traces.find((item) => item.key === r.key)?.chart} small />}</article>)}</div> : <div className="sensors"><table><thead><tr>{[t("Sensor"), t("Value"), t("Min"), t("Avg"), t("Max")].map((label) => <th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((r, index) => r.group ? <tr className="g" key={`${r.group}-${index}`}><td colSpan="5">▾ {r.group}</td></tr> : <tr className="s" key={r.key}><td><label><input type="checkbox" checked={selected.includes(r.key)} onChange={() => toggle(r.key)} />{r.label}</label></td><td className="v">{r.value}</td><td>{r.min}</td><td>{r.avg}</td><td>{r.max}</td></tr>)}</tbody></table></div>)}
    {layout !== "list" && !mobile && traces.map((item) => <section className="desktop-trace" key={item.key}><div className="title"><b>{item.label}</b><span>{item.value}</span></div><Chart chart={item.chart} small={layout === "split"} /></section>)}
  </div>;
}

export default function Performance() {
  const mobile = useMobile();
  const [state, setState] = useState({ tab: "sensors" });
  const set = (patch) => setState((s) => ({ ...s, ...patch }));
  const query = new URLSearchParams({ tab: state.tab });
  const rule = state.tab === "sensors" ? { layout: state.layout, q: state.q, kind: state.kind, hide: state.hide, ticked: state.ticked?.join(",") } : { view: state[`view:${state.tab}`], scale: state.scale };
  Object.entries(rule).forEach(([k, v]) => v !== undefined && (v !== "" || k === "ticked") && query.set(k, v));
  const data = usePoll(`performance?${query}`, 1000, 0);
  return <section className="card perf">
    {mobile ? <div className="resource-switch"><Icon name="nav_performance" /><label><span>{t("Performance")}</span><select value={state.tab} aria-label={t("Performance")} onChange={(e) => set({ tab: e.target.value })}>{(data?.tabs || [{ key: "sensors", title: t("Sensors") }]).map((tab) => <option key={tab.key} value={tab.key}>{tab.title}</option>)}</select></label></div> : <Segments items={data?.tabs || []} value={state.tab} onChange={(tab) => set({ tab })} />}
    {!data || data.waiting || data.tab !== state.tab ? <p className="note pad">{t("Waiting for first sample")}</p> : state.tab === "sensors" ? <Sensors data={data} state={state} set={set} /> : <Resource data={data} state={state} set={(patch) => set(patch.view ? { [`view:${state.tab}`]: patch.view } : patch)} />}
  </section>;
}
