import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App, api, loadStrings, onSessionLost, setCsrf, t, usePoll } from "./lib.jsx";
import { Btn, Card, Icon } from "./ui.jsx";
import Compute from "./pages/Compute.jsx";
import Cpu from "./pages/Cpu.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Fans from "./pages/Fans.jsx";
import Gpu from "./pages/Gpu.jsx";
import Performance from "./pages/Performance.jsx";
import Settings from "./pages/Settings.jsx";

// The desktop's sidebar: same order, same icons, same captions.
const NAV = [
  { key: "dashboard", title: () => t("Dashboard"), icon: "nav_dashboard", page: Dashboard },
  { cap: () => t("Hardware") },
  { key: "cpu", title: () => t("CPU / SMU"), icon: "nav_cpu", page: Cpu },
  { key: "cu", title: () => t("Compute Units"), icon: "nav_compute", page: Compute },
  { key: "gpu", title: () => t("GPU Governor"), icon: "nav_gpu", page: Gpu },
  { cap: () => t("Monitoring") },
  { key: "performance", title: () => t("Performance"), icon: "nav_performance", page: Performance },
  { key: "fans", title: () => t("Fans"), icon: "nav_fans", page: Fans },
];
const SETTINGS = { key: "settings", title: () => t("Settings"), icon: "nav_settings", page: Settings };
const ALL = [...NAV.filter((item) => item.key), SETTINGS];
const route = () => (ALL.find((item) => `#/${item.key}` === location.hash) || ALL[0]).key;

function Login({ onDone, error }) {
  const [key, setKey] = useState("");
  const [message, setMessage] = useState(error || "");
  const submit = async (e) => {
    e.preventDefault();
    const result = await api("login", { key });
    if (result.ok) { setCsrf(result.csrf); onDone(); } else setMessage(t(result.error || "That key is not right."));
  };
  return (
    <div className="login"><form onSubmit={submit}><Card title={t("BC250 Control Center")} sub={t("Enter the access key shown in Remote access on the desktop application.")}>
      <input className="input" autoFocus autoComplete="off" autoCapitalize="characters" spellCheck="false" aria-label={t("Access key")}
        placeholder="XXXX-XXXX" value={key} onChange={(e) => setKey(e.target.value)} />
      {message && <p className="err" role="alert">{message}</p>}
      <Btn kind="primary" type="submit" disabled={!key.trim()}>{t("Sign in")}</Btn>
    </Card></form></div>
  );
}

/** The job that runs hardware changes: its output, and the password prompt sudo or Polkit shows. */
function Activity({ job, onClose, canType }) {
  const [text, setText] = useState("");
  const out = useRef(null);
  useEffect(() => { if (out.current) out.current.scrollTop = out.current.scrollHeight; }, [job?.text]);
  if (!job) return null;
  const send = async (e) => { e.preventDefault(); await api("job/input", { text }); setText(""); };
  return (
    <div className="sheet" role="dialog" aria-label={job.label}>
      <div className="hd"><h2>{job.label}</h2>{job.done ? <span className={`pill ${job.ok ? "green" : "red"}`}>{job.ok ? t("Done") : t("Failed")}</span> : <span className="pill blue">{t("Running…")}</span>}</div>
      <pre className="console" ref={out}>{job.text || t("Waiting for data…")}</pre>
      {!job.done && (canType
        ? <form className="row" onSubmit={send}><input className="input" type="password" autoComplete="off" placeholder={t("Password")} aria-label={t("Password")} value={text}
            onChange={(e) => setText(e.target.value)} style={{ flex: 1 }} /><Btn type="submit" disabled={!text}>{t("Send")}</Btn></form>
        : <p className="note warn">{t("The password is only accepted on this computer, or after turning that option on.")}</p>)}
      <div className="row end">{!job.done && <Btn kind="danger" small onClick={() => api("job/interrupt", {})}>{t("Stop")}</Btn>}
        {job.done && <Btn small onClick={onClose}>{t("Close")}</Btn>}</div>
    </div>
  );
}

function Confirm({ spec, onCancel, onGo }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    const result = await onGo(key);
    if (!result.ok) { setError(t(result.error || "Not detected")); setBusy(false); }
  };
  return (
    <div className="scrim" onClick={onCancel}><div className="dialog" role="alertdialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
      <header><div className="eyebrow">{t("CONFIRM HARDWARE ACTION")}</div><h3>{spec.title}</h3></header>
      <section>{spec.body && <p style={{ margin: 0 }}>{spec.body}</p>}
        {(spec.warning || spec.level === 2) && <div className="notice">{spec.warning || t("Stop every game, benchmark, and 3D workload before continuing.")}</div>}
        {spec.level === 2 && <label className="field"><span>{t("Access key")}</span><input className="input" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} /></label>}
        {error && <p className="err" role="alert">{error}</p>}</section>
      <footer><Btn onClick={onCancel}>{t("Cancel")}</Btn>
        <Btn kind={spec.level ? "danger" : "primary"} disabled={busy || (spec.level === 2 && !key.trim())} onClick={go}>{spec.go || t("Apply")}</Btn></footer>
    </div></div>
  );
}

function Shell({ session, onLogout }) {
  const [page, setPage] = useState(route());
  const [slim, setSlim] = useState(() => localStorage.getItem("slim") === "1");
  const [menu, setMenu] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [jobId, setJobId] = useState(0);
  const [job, setJob] = useState(null);
  const [toast, setToast] = useState(null);
  const [again, setAgain] = useState(0);
  const live = usePoll("live", 1000, 0);

  useEffect(() => { const on = () => { setPage(route()); setMenu(false); }; addEventListener("hashchange", on); return () => removeEventListener("hashchange", on); }, []);
  useEffect(() => { localStorage.setItem("slim", slim ? "1" : "0"); }, [slim]);
  useEffect(() => { if (!toast) return undefined; const id = setTimeout(() => setToast(null), 5000); return () => clearTimeout(id); }, [toast]);
  useEffect(() => {
    if (!jobId) return undefined;
    let stop = false;
    const tick = async () => {
      const next = await api("job");
      if (stop) return;
      setJob(next);
      if (next.done) {
        setAgain((n) => n + 1);
        setToast(next.ok ? { tone: "ok", text: next.message || t("Done") } : { tone: "bad", text: t("The workflow did not finish successfully.") });
      } else setTimeout(tick, 600);
    };
    tick();
    return () => { stop = true; };
  }, [jobId]);

  /** Every hardware change goes through here: the spec names the closed action, the dialog asks. */
  const go = async (spec, key) => {
    const result = await api("action", { action: spec.action, title: spec.title, params: spec.params || {}, confirm: spec.level ? true : undefined, key: spec.level === 2 ? key : undefined });
    if (result.ok) { setConfirm(null); setJob({ label: spec.title, text: "", done: false }); setJobId(result.job); }
    return result;
  };
  const act = (spec) => (spec.level ? setConfirm(spec) : go(spec));
  const running = job && !job.done;
  const current = ALL.find((item) => item.key === page);
  const Page = current.page;
  const link = (item) => <a key={item.key} className={`nav ${page === item.key ? "on" : ""}`} href={`#/${item.key}`} aria-current={page === item.key ? "page" : undefined}><Icon name={item.icon} /><span>{item.title()}</span></a>;
  const name = t("BC250 Control Center").replace("BC250", "").trim();
  return (
    <App.Provider value={{ live: live?.metrics ? live : null, history: live?.history || {}, act, again, running, toast: setToast, session }}>
      <div className="shell">
        <div className="topbar"><button className="ghost" aria-label={t("Menu")} onClick={() => setMenu(true)}><Icon name="expand_gray" /></button><b>{current.title()}</b></div>
        {menu && <div className="scrim menu-scrim" style={{ zIndex: 24 }} onClick={() => setMenu(false)} />}
        <nav className={`side ${slim ? "slim" : ""} ${menu ? "open" : ""}`} aria-label="BC250">
          <div className="brand"><img src="logo.png" alt="" /><div className="grow"><b>BC250</b><small>{name[0]?.toUpperCase() + name.slice(1)}</small></div>
            <button className="ghost collapse" aria-label={slim ? t("Expand sidebar") : t("Collapse sidebar")} onClick={() => setSlim(!slim)}><Icon name={slim ? "expand_gray" : "collapse_gray"} /></button></div>
          {NAV.map((item) => (item.cap ? <div className="cap" key={item.cap()}>{item.cap()}</div> : link(item)))}
          <div className="spring" /><div className="rule" />{link(SETTINGS)}
        </nav>
        <main className="main"><Page onLogout={onLogout} /></main>
      </div>
      {confirm && <Confirm spec={confirm} onCancel={() => setConfirm(null)} onGo={(key) => go(confirm, key)} />}
      {(job && (jobId || running)) && <Activity job={job} canType={session.password} onClose={() => { setJob(null); setJobId(0); }} />}
      {toast && <div className={`toast ${toast.tone}`} role="status">{toast.text}</div>}
    </App.Provider>
  );
}

function Root() {
  const [state, setState] = useState({ loading: true });
  const refresh = useCallback(async () => {
    const data = await api("session");
    setCsrf(data.csrf);
    setState({ loading: false, ...data });
  }, []);
  useEffect(() => {
    onSessionLost(() => setState((s) => ({ ...s, authenticated: false })));
    const theme = localStorage.getItem("theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    loadStrings().then(refresh);
  }, [refresh]);
  if (state.loading) return null;
  if (!state.authenticated) return <Login onDone={refresh} />;
  return <Shell session={state} onLogout={async () => { await api("logout", {}); refresh(); }} />;
}

createRoot(document.getElementById("root")).render(<StrictMode><Root /></StrictMode>);
