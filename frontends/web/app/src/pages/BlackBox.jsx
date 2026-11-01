import { useEffect, useRef, useState } from "react";
import { api, t, useApp, usePoll } from "../lib.jsx";
import { Btn, Icon, Segments, useMobile } from "../ui.jsx";

function ServerUnavailable() {
  return <p className="notice" role="alert">{t("This web server does not support Black box yet. Stop and start web access from the desktop application after updating, then reload this page.")}</p>;
}

function Recording() {
  const mobile = useMobile();
  const { session } = useApp();
  const [again, setAgain] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const data = usePoll("blackbox?view=recording", 1000, again);
  const control = async (operation, enabled) => {
    if (busy || !session?.control) return;
    setBusy(true); setError("");
    const result = await api("blackbox/control", { operation, ...(operation === "autostart" ? { enabled } : {}) });
    if (!result.ok) setError(result.status === 404 ? t("Restart web access from the desktop application to use these controls.") : t(result.error || "Failed"));
    setAgain(value => value + 1);
    setBusy(false);
  };
  const [shown, setShown] = useState(null), [following, setFollowing] = useState(true), [page, setPage] = useState(0);
  const viewport = useRef(null);
  useEffect(() => { if (following && data?.rows) setShown(data); }, [following, data]);
  const value = shown || data;
  const rows = value?.rows || [], columns = value?.columns || [];
  const size = mobile ? 20 : 50, pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(page, pages - 1), visible = rows.slice(current * size, (current + 1) * size);
  const follow = () => { setPage(0); setFollowing(true); if (viewport.current) viewport.current.scrollTop = 0; };
  if (data?.status === 404) return <ServerUnavailable/>;
  const ready = !!data?.rows && !data?._disconnected;
  const autostart = data?.autostart || {};
  return <>
    <div className="blackbox-controls"><Btn kind={data?.running ? "" : "primary"} disabled={!ready || busy || !session?.control || (!data?.supported && !data?.running)} onClick={() => control(data?.running ? "stop" : "start")}>{data?.running ? t("Stop recording") : t("Start recording")}</Btn>
      {autostart.supported && <label className="check"><input type="checkbox" checked={!!autostart.enabled} disabled={busy || !ready || !session?.control || autostart.foreign} onChange={event => control("autostart", event.target.checked)}/>{t("Start with the session")}</label>}
    </div>
    {error && <p className="notice" role="alert">{error}</p>}
    {data?._disconnected && <p className="notice" role="status">{t("Not connected")}</p>}
    {data?.state === "cut-off" && <p className="notice" role="status">{t(data.message)}</p>}
    {data?.error && <p className="notice" role="alert">{t(data.error)}</p>}
    {!following && <div className="blackbox-follow"><span>{t("Paused while you read. Go back to the top to follow the recording.")}</span><Btn small onClick={follow}>{t("Follow latest readings")}</Btn></div>}
    <div className="blackbox-recording" ref={viewport} onScroll={event => {
      if (event.currentTarget.scrollTop > 8) setFollowing(false);
      else if (current === 0) setFollowing(true);
    }} tabIndex={0} aria-label={t("Black box")}>
      {!value?.rows ? <p className="note">{t("Waiting for data…")}</p> : !rows.length ? <p className="note blackbox-empty">{t("No recording is available. Start recording before playing to catch a freeze.")}</p> : mobile ? <div className="blackbox-samples">{visible.map((row, index) => <details className="blackbox-sample" key={`${row.time}-${index}`} onToggle={event => { if (event.currentTarget.open) setFollowing(false); }}>
        <summary><span className="blackbox-sample-heading"><time>{row.time}</time><b>{row.clock}</b><span>{row.busy}</span><Icon name="chevron_down_gray" /></span>
          <span className="blackbox-sample-preview">{[["GPU",row.t_gpu,"°C"],["CPU",row.t_cpu,"°C"],[t("Power"),row.watts,"W"],["CPU",row.cpu,"MHz"]].map(([label,value,unit],i)=><span key={i}><small>{label}</small><b>{value && value !== "-" ? `${value} ${unit}` : "—"}</b></span>)}</span>
        </summary>
        <dl>{columns.filter(column => !["time", "clock", "busy", "t_gpu", "t_cpu", "watts", "cpu"].includes(column.key)).map(column => <div key={column.key}><dt>{t(column.label)}</dt><dd>{row[column.key] === "-" ? "—" : row[column.key]}</dd></div>)}</dl>
      </details>)}</div> : <table className="blackbox-table"><thead><tr>{columns.map(column => <th key={column.key} scope="col">{t(column.label)}</th>)}</tr></thead><tbody>{visible.map((row, index) => <tr key={`${row.time}-${index}`}>{columns.map(column => <td key={column.key}>{row[column.key] === "-" ? "—" : row[column.key]}</td>)}</tr>)}</tbody></table>}
    </div>
    <div className="blackbox-footer"><span>{t("{count} readings", { count: rows.length })} · {t("Newest first")}</span>{pages > 1 && <div className="row"><Btn small disabled={current === 0} onClick={() => { setFollowing(false); setPage(current - 1); }}>{t("Previous")}</Btn><span>{current + 1} / {pages}</span><Btn small disabled={current >= pages - 1} onClick={() => { setFollowing(false); setPage(current + 1); }}>{t("Next")}</Btn></div>}</div>
  </>;
}

function DiagnosisText({ text, visible }) {
  const [height, setHeight] = useState(220);
  const drag = useRef(null);
  const clamp = value => Math.max(90, Math.min(3000, value));
  const fit = () => {
    const fitted = clamp(text.split("\n").length * 18 + 24);
    setHeight(value => Math.abs(value - fitted) < 2 ? 220 : fitted);
  };
  return <div className="blackbox-panel" hidden={!visible}>
    <pre tabIndex={0} style={{ height }}>{text}</pre>
    <div className="blackbox-resize" role="separator" tabIndex={0} aria-label={t("Resize diagnosis panel")} aria-orientation="horizontal" aria-valuemin={90} aria-valuemax={3000} aria-valuenow={height} title={t("Drag to resize. Double-click to fit the text.")}
      onPointerDown={event => {
        if (event.button !== 0) return;
        event.preventDefault(); event.currentTarget.focus();
        drag.current = { y: event.clientY, height };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => { if (drag.current) setHeight(clamp(drag.current.height + event.clientY - drag.current.y)); }}
      onPointerUp={event => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
      onPointerCancel={() => { drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }}
      onDoubleClick={fit}
      onKeyDown={event => {
        if (!["ArrowUp", "ArrowDown", "Home", "End", "Enter"].includes(event.key)) return;
        event.preventDefault();
        if (event.key === "Enter") { fit(); return; }
        setHeight(value => event.key === "Home" ? 90 : event.key === "End" ? 3000 : clamp(value + (event.key === "ArrowDown" ? 40 : -40)));
      }}><span aria-hidden="true"/></div>
  </div>;
}

function Diagnosis() {
  const [again, setAgain] = useState(0), [tab, setTab] = useState("all"), [query, setQuery] = useState(""), [open, setOpen] = useState(new Set());
  const data = usePoll("blackbox?view=diagnosis", 1500, again);
  const [refreshing, setRefreshing] = useState(false);
  const sections = (data?.sections || []).filter(section => (tab === "all" || section.group === tab) && `${section.title}\n${section.text}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const refresh = async () => {
    setRefreshing(true);
    await api("blackbox?view=diagnosis&refresh=1");
    setAgain(value => value + 1);
    setRefreshing(false);
  };
  if (data?.status === 404) return <ServerUnavailable/>;
  return <div className="blackbox-diagnosis">
    <Segments items={(data?.tabs || []).map(item => ({ key: item.key, title: t(item.label) }))} value={tab} onChange={setTab}/>
    <div className="blackbox-tools"><input className="input" type="search" aria-label={t("Search the diagnosis")} placeholder={t("Search the diagnosis")} value={query} onChange={event => setQuery(event.target.value)} /><Btn small onClick={() => setOpen(new Set(sections.map(section => section.title)))}>{t("Expand all")}</Btn><Btn small onClick={() => setOpen(new Set())}>{t("Collapse all")}</Btn><Btn small disabled={refreshing || data?.loading} onClick={refresh}>{t("Refresh")}</Btn></div>
    {(!data || data.loading) && <p className="note" role="status">{t("Reading the diagnosis…")}</p>}
    {(data?.error || data?._disconnected) && <p className="notice" role="alert">{t(data.error || "Not connected")}</p>}
    {data?.ready && !sections.length && <p className="note">{t("No matching sections.")}</p>}
    <div className="blackbox-sections">{sections.map(section => <section className="blackbox-section" key={section.title}><button className="blackbox-section-toggle" aria-expanded={open.has(section.title)} onClick={() => setOpen(previous => {
      const next = new Set(previous); next.has(section.title) ? next.delete(section.title) : next.add(section.title); return next;
    })}><Icon name={open.has(section.title) ? "chevron_down_gray" : "chevron_right_gray"}/><span>{t(section.title)}</span><small>{Math.max(1, Math.round(section.text.length / 1024))} KB</small></button><DiagnosisText text={section.text} visible={open.has(section.title)}/></section>)}</div>
  </div>;
}

export default function BlackBox() {
  const [view, setView] = useState("recording");
  return <section className="card blackbox-workspace"><Segments items={[{key:"recording",title:t("Black box")},{key:"diagnosis",title:t("Full diagnosis")}]} value={view} onChange={setView}/>{view === "recording" ? <Recording/> : <Diagnosis/>}</section>;
}
