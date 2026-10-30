import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App, api, loadStrings, onSessionLost, setCsrf, t, usePoll } from "./lib.jsx";
import { Btn, Card, Dialog, Icon, Modal } from "./ui.jsx";
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
  const [busy, setBusy] = useState(false);
  const privateConnection = location.protocol === "https:" || ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const signIn = async (value) => {
    if (!privateConnection) { setMessage(t("HTTPS required")); return; }
    setBusy(true);
    const result = await api("login", { key: value });
    if (result.ok) { setCsrf(result.csrf); onDone(); }
    else { setMessage(t(result.error || "That key is not right.")); setBusy(false); }
  };
  useEffect(() => {
    const pair = new URLSearchParams(location.hash.slice(1)).get("pair");
    if (pair) { history.replaceState(null, "", location.pathname); setKey(pair); signIn(pair); }
  }, []);
  const submit = async (e) => {
    e.preventDefault();
    await signIn(key);
  };
  return (
    <div className="login"><form onSubmit={submit}><div className="login-brand"><img src="logo.png" alt="" /><span>BC250<small>{t("Control Center")}</small></span></div><Card title={t("Remote access")} sub={t("Enter the access key shown in Remote access on the desktop application.")}>
      <input className="input" autoFocus autoComplete="off" autoCapitalize="characters" spellCheck="false" aria-label={t("Access key")}
        placeholder="XXXX-XXXX" value={key} onChange={(e) => setKey(e.target.value)} />
      {message && <p className="err" role="alert">{message}</p>}
      {!privateConnection && <p className="notice">{t("HTTPS required")}</p>}
      <Btn kind="primary" type="submit" disabled={!privateConnection || busy || !key.trim()}>{busy ? t("Connecting…") : t("Sign in")}</Btn>
    </Card></form></div>
  );
}

/** The job that runs hardware changes: its output, and the password prompt sudo or Polkit shows. */
function Activity({ job, onClose, canType }) {
  const [text, setText] = useState("");
  const out = useRef(null);
  const [expanded, setExpanded] = useState(true);
  useEffect(() => setExpanded(true), [job?.id]);
  useEffect(() => setText(""), [job?.id, job?.waiting]);
  useEffect(() => { if (out.current) out.current.scrollTop = out.current.scrollHeight; }, [job?.text]);
  if (!job) return null;
  const send = async (e) => { e.preventDefault(); const value = text; setText(""); await api("job/input", { text: value }); };
  const status = job.done ? (job.ok ? t("Done") : t("Failed")) : job.waiting ? t("Administrator password") : t("Running…");
  const tone = job.done ? (job.ok ? "green" : "red") : "blue";
  if (!expanded) return <button className="operation-minimized" onClick={() => setExpanded(true)} aria-expanded={false}><span className={`pill ${tone}`}>{status}</span><span>{job.label}</span><Icon name="expand_gray" /></button>;
  return <Modal onClose={() => setExpanded(false)}><section className="dialog operation-dialog" role="dialog" aria-modal="true" aria-label={job.label}>
    <header><div className="dialog-heading"><span className={`dialog-symbol ${tone}`}><Icon name={job.done ? (job.ok ? "check_green" : "warning_orange") : "nav_performance"} /></span><div><span className="dialog-caption">{t("Hardware")}</span><h3>{job.label}</h3></div></div>
      <div className="operation-status"><span className={`pill ${tone}`} role="status">{status}</span></div></header>
    <section><pre className="console operation-output" ref={out} tabIndex={0} aria-label={t("Terminal output")}>{job.text || t("Waiting for data…")}</pre>
      {!job.done && (job.interactive || job.waiting) && (canType
        ? <form className="terminal-auth" onSubmit={send}><label className="field"><span>{job.waiting ? t("Linux password") : t("Terminal input")}</span><input className="input" type={job.waiting ? "password" : "text"} autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} /></label><Btn type="submit" kind="primary" disabled={job.waiting && !text}>{t("Send")}</Btn></form>
        : <p className="notice">{t("Use HTTPS before entering your Linux password.")}</p>)}
    </section><footer>{!job.done && <Btn kind="danger" onClick={() => api("job/interrupt", {})}>{t("Stop")}</Btn>}<Btn onClick={() => setExpanded(false)}>{t("Hide")}</Btn>{job.done && <Btn kind="primary" onClick={onClose}>{t("Close")}</Btn>}</footer>
  </section></Modal>;
}

function SSH({ onClose, canType }) {
  const status = usePoll("ssh", 800, 0);
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const start = async () => { const r = await api("ssh/start", {}); if (r.error) setMessage(t(r.error)); };
  const send = async (e) => { e.preventDefault(); const value = password; setPassword(""); const r = await api("ssh/input", { text: value }); if (r.error) setMessage(t(r.error)); };
  return <Dialog title={t("SSH authorization")} onClose={onClose} footer={<Btn kind="primary" onClick={onClose}>{t("Close")}</Btn>}>
    <p className="note">{t("Connect to this board with your Linux account. Hardware permissions are requested here when needed.")}</p>
    <div className="connection-state"><i className={status?.ready ? "connected" : ""} />{status?.ready ? t("Connected") : t("Not connected")}</div>
    {status?.text && !status.ready && <pre className="console">{status.text}</pre>}
    {message && <p className="err" role="alert">{message}</p>}
    {!canType && <p className="notice">{t("Use HTTPS before entering your Linux password.")}</p>}
    {status?.closed ? <Btn disabled={!canType} onClick={start}>{t("Connect SSH")}</Btn>
      : status?.ready ? <Btn kind="danger" onClick={() => api("ssh/close", {})}>{t("Disconnect")}</Btn>
      : status?.prompt ? <form className="stack" onSubmit={send}><label className="field"><span>{t("Linux password")}</span><input className="input" type="password" autoComplete="off" value={password} disabled={!canType} onChange={(e) => setPassword(e.target.value)} /></label><Btn type="submit" disabled={!canType || !password}>{t("Send")}</Btn></form> : <p className="note" role="status">{t("Connecting…")}</p>}
  </Dialog>;
}

function Confirm({ spec, onCancel, onGo }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    const result = await onGo();
    if (!result.ok) { setError(t(result.error || "Not detected")); setBusy(false); }
  };
  return (
    <Modal onClose={() => { if (!busy) onCancel(); }}><div className="dialog" role="alertdialog" aria-label={spec.title} aria-modal="true">
      <header><div className="dialog-heading"><span className={`dialog-symbol ${spec.level === 2 ? "orange" : "blue"}`}><Icon name="warning_orange" /></span><div><span className="dialog-caption">{t("Confirm")}</span><h3>{spec.title}</h3></div></div></header>
      <section>{spec.body && <p style={{ margin: 0 }}>{spec.body}</p>}
        {spec.summary?.length > 0 && <dl className="dialog-summary">{spec.summary.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
        {(spec.warning || spec.level === 2) && <div className="notice">{spec.warning || t("Stop every game, benchmark, and 3D workload before continuing.")}</div>}
        {error && <p className="err" role="alert">{error}</p>}</section>
      <footer><Btn disabled={busy} onClick={onCancel}>{t("Cancel")}</Btn>
        <Btn kind={spec.level === 2 ? "danger" : "primary"} disabled={busy} onClick={go}>{spec.go || t("Apply")}</Btn></footer>
    </div></Modal>
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
  const [sshOpen, setSshOpen] = useState(false);
  const ssh = usePoll("ssh", 3000, 0);
  const live = usePoll("live", 1000, 0);
  const release = usePoll("version", 15000, 0);
  const loadedBuild = document.querySelector('meta[name="bc250-build"]')?.content;
  const updateAvailable = loadedBuild && release?.version && loadedBuild !== release.version;
  const refreshBuild = () => { const url = new URL(location.href); url.searchParams.set("v", release.version); location.replace(url); };

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
  const go = async (spec) => {
    const result = await api("action", { action: spec.action, title: spec.title, params: spec.params || {}, confirm: spec.level ? true : undefined });
    if (result.ok) { setConfirm(null); setJob({ label: spec.title, text: "", done: false }); setJobId((n) => n + 1); }
    return result;
  };
  const act = (spec) => {
    if (job && !job.done) { setToast({ tone: "bad", text: t("Another hardware action is still running.") }); return; }
    if (spec.level) setConfirm(spec);
    else go(spec).then((r) => { if (!r.ok) setToast({ tone: "bad", text: t(r.error) }); });
  };
  const running = job && !job.done;
  const current = ALL.find((item) => item.key === page);
  const Page = current.page;
  const link = (item) => <a key={item.key} className={`nav ${page === item.key ? "on" : ""}`} href={`#/${item.key}`} aria-current={page === item.key ? "page" : undefined}><Icon name={item.icon} /><span>{item.title()}</span></a>;
  const name = t("BC250 Control Center").replace("BC250", "").trim();
  return (
    <App.Provider value={{ live: live?.metrics ? live : null, history: live?.history || {}, act, again, running, toast: setToast, session, ssh, openSsh: () => setSshOpen(true) }}>
      <div className="shell">
        <header className="topbar"><a className="mobile-brand" href="#/dashboard"><img src="logo.png" alt="" /><strong>BC250</strong></a><span className="topbar-title">{current.title()}</span><button className="ghost" aria-label={t("Menu")} aria-expanded={menu} onClick={() => setMenu(!menu)}><Icon name="nav_settings" /></button></header>
        {menu && <div className="scrim menu-scrim" style={{ zIndex: 24 }} onClick={() => setMenu(false)} />}
        <nav className={`side ${slim ? "slim" : ""} ${menu ? "open" : ""}`} aria-label="BC250">
          <div className="brand"><img src="logo.png" alt="" /><div className="grow"><b>BC250</b><small>{name[0]?.toUpperCase() + name.slice(1)}</small></div>
            <button className="ghost collapse" aria-label={slim ? t("Expand sidebar") : t("Collapse sidebar")} onClick={() => setSlim(!slim)}><Icon name={slim ? "expand_gray" : "collapse_gray"} /></button></div>
          {NAV.map((item) => (item.cap ? <div className="cap" key={item.cap()}>{item.cap()}</div> : link(item)))}
          <div className="spring" /><div className="rule" />
          {link(SETTINGS)}
        </nav>
        <main className={`main page-${page}`}><h1 className="sr-only">{current.title()}</h1>{updateAvailable && <div className="update-notice" role="status"><span>{t("Update available")}</span><Btn small disabled={running} onClick={refreshBuild}>{t("Refresh")}</Btn></div>}{live?._disconnected && <p className="notice" role="status">{t("Not connected")}</p>}<Page onLogout={onLogout} /></main>
        <nav className="bottom-nav" aria-label={t("Hardware")}>{["dashboard", "cpu", "cu", "gpu", "performance"].map((key, i) => {
          const item = ALL.find((v) => v.key === key);
          return <a href={`#/${key}`} key={key} className={page === key ? "on" : ""} aria-current={page === key ? "page" : undefined}><Icon name={item.icon} /><span>{[t("Dashboard"), "CPU", "CU", "GPU", t("Sensors")][i]}</span></a>;
        })}</nav>
      </div>
      {confirm && <Confirm spec={confirm} onCancel={() => { setConfirm(null); confirm.onCancel?.(); }} onGo={() => go(confirm)} />}
      {(job && (jobId || running)) && <Activity job={job} canType={session.password} onClose={() => { setJob(null); setJobId(0); }} />}
      {sshOpen && <SSH onClose={() => setSshOpen(false)} canType={session.password} />}
      {toast && <div className={`toast ${toast.tone}`} role="status"><Icon name={toast.tone === "ok" ? "check_green" : "warning_orange"} /><span>{toast.text}</span><button className="ghost" aria-label={t("Close")} onClick={() => setToast(null)}><Icon name="close_gray" /></button></div>}
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
    const changed = () => setState((s) => ({ ...s }));
    addEventListener("languagechanged", changed);
    loadStrings(localStorage.getItem("language") || navigator.language).then(refresh);
    return () => removeEventListener("languagechanged", changed);
  }, [refresh]);
  if (state.loading) return null;
  if (!state.authenticated) return <Login onDone={refresh} />;
  return <Shell session={state} onLogout={async () => { await api("logout", {}); refresh(); }} />;
}

createRoot(document.getElementById("root")).render(<StrictMode><Root /></StrictMode>);
