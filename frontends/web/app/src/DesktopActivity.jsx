import { useEffect, useRef, useState } from "react";
import { api, t } from "./lib.jsx";
import { Btn, Icon, Modal } from "./ui.jsx";

/** Non-password prompts keep using the existing, session-owned job channel. */
export function TerminalInput({ job, canType }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setText(""); setError(""); }, [job.id, job.waiting]);
  if (job.done || job.waiting || !job.interactive) return null;
  const send = async (event) => {
    event.preventDefault();
    if (!canType || sending) return;
    setSending(true);
    setError("");
    const value = text;
    setText("");
    const result = await api("job/input", { text: value });
    setSending(false);
    if (!result.ok) setError(t(result.error || "Failed"));
  };
  return <>
    {canType ? <form className="terminal-auth" onSubmit={send}>
      <label className="field"><span>{t("Terminal input")}</span><input className="input" autoComplete="off" maxLength={256} value={text} disabled={sending} onChange={event => setText(event.target.value)} /></label>
      <Btn type="submit" disabled={sending}>{t("Send")}</Btn>
    </form> : <p className="note">{t("Use HTTPS before entering your Linux password.")}</p>}
    {error && <p className="err" role="alert">{error}</p>}
  </>;
}

/** One output surface per task; authentication is a separate, compact prompt. */
export default function DesktopActivity({ job, inlineConsole, canType, onClose }) {
  const [expanded, setExpanded] = useState(() => job.kind !== "gddr6.monitor");
  const [password, setPassword] = useState("");
  const [sending, setSending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState("");
  const sentPrompt = useRef(null);
  const latestJob = useRef(job);
  latestJob.current = job;
  const output = useRef(null);
  const passwordInput = useRef(null);
  const wasWaiting = useRef(!!job.waiting);
  const hasInline = !!inlineConsole && job.kind?.startsWith(inlineConsole);
  useEffect(() => {
    setExpanded(job.kind !== "gddr6.monitor"); setPassword(""); setSending(false); setCancelling(false); setSubmitted(false); setDismissed(false); setError("");
    sentPrompt.current = null;
  }, [job.id]);
  useEffect(() => {
    // A fresh prompt can be a retry or another privileged step in the same job.
    if (!job.waiting || sentPrompt.current !== null && job.text !== sentPrompt.current) {
      setSubmitted(false); setPassword(""); sentPrompt.current = null;
    }
  }, [job.waiting, job.text]);
  useEffect(() => { if (output.current) output.current.scrollTop = output.current.scrollHeight; }, [job.text, expanded, hasInline, job.waiting]);
  useEffect(() => { if (job.done && !job.ok && !hasInline) setExpanded(true); }, [job.done, job.ok, hasInline]);

  useEffect(() => { if (job.waiting && !submitted && !sending) passwordInput.current?.focus(); }, [job.waiting, submitted, sending]);

  useEffect(() => {
    if (wasWaiting.current && !job.waiting && hasInline) {
      const console = [...document.querySelectorAll("[data-job-console]")].find(node => node.dataset.jobConsole === inlineConsole);
      console?.scrollIntoView({ block: "nearest" });
      console?.focus({ preventScroll: true });
    }
    wasWaiting.current = !!job.waiting;
  }, [job.waiting, hasInline, inlineConsole]);

  const cancel = async () => {
    if (sending || cancelling) return;
    setCancelling(true);
    const requestId = job.id;
    const result = await api("job/interrupt", {});
    if (latestJob.current.id !== requestId) return;
    setCancelling(false);
    if (result.ok) { setPassword(""); setDismissed(true); }
    else setError(t(result.error || "Failed"));
  };
  const authenticate = async (event) => {
    event.preventDefault();
    if (!canType || !password || sending || submitted || cancelling) return;
    const value = password;
    setPassword(""); setSending(true); setError("");
    const requestId = job.id, prompt = job.text;
    sentPrompt.current = prompt;
    const result = await api("job/input", { text: value });
    if (latestJob.current.id !== requestId) return;
    setSending(false);
    if (result.ok) setSubmitted(!!latestJob.current.waiting && latestJob.current.text === prompt);
    else { sentPrompt.current = null; setError(t(result.error || "Failed")); }
  };
  if (!job.done && job.waiting && !dismissed) return <Modal onClose={cancel}>
    <form className="dialog desktop-password-dialog" role="dialog" aria-modal="true" aria-label={t("Administrator password")} aria-busy={sending || submitted} onSubmit={authenticate}>
      <section>
        <p className="desktop-auth-context">{job.label}</p>
        <label className="field"><span>{t("Linux password")}</span><input ref={passwordInput} className="input" type="password" autoComplete="off" maxLength={256} disabled={!canType || sending || submitted || cancelling} value={password} onChange={event => setPassword(event.target.value)} /></label>
        {!canType && <p className="notice">{t("Use HTTPS before entering your Linux password.")}</p>}
        {error && <p className="err" role="alert">{error}</p>}
      </section>
      <footer><Btn disabled={sending || cancelling} onClick={cancel}>{t("Cancel")}</Btn><Btn type="submit" kind="primary" disabled={!canType || !password || sending || submitted || cancelling}>{sending || submitted ? t("Authenticating…") : t("Authenticate")}</Btn></footer>
    </form>
  </Modal>;

  const status = job.done ? (job.ok ? t("Done") : t("Failed")) : job.waiting ? t("Administrator password") : t("Running…");
  const tone = job.done ? (job.ok ? "green" : "red") : "blue";
  const open = () => {
    if (hasInline) {
      const console = [...document.querySelectorAll("[data-job-console]")].find(node => node.dataset.jobConsole === inlineConsole);
      console?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      console?.focus({ preventScroll: true });
    } else setExpanded(true);
  };
  if (hasInline || !expanded || dismissed) return <div className="operation-minimized">
    <button className="operation-open" onClick={open} aria-expanded={false}><span className={`pill ${tone}`}>{status}</span><span>{job.label}</span><Icon name="expand_gray" /></button>
    {!job.done && <button className="ghost" aria-label={t("Stop")} onClick={cancel}><Icon name="stop_red" /></button>}
    {job.done && <button className="ghost" aria-label={t("Close")} onClick={onClose}><Icon name="close_gray" /></button>}
    {error && <span className="err" role="alert">{error}</span>}
  </div>;
  return <Modal onClose={() => setExpanded(false)}>
    <section className="dialog operation-dialog desktop-job-terminal" role="dialog" aria-modal="true" aria-label={job.label}>
      <section><pre className="console operation-output" ref={output} tabIndex={0} aria-label={t("Terminal output")}>{job.text || t("Waiting for data…")}</pre><TerminalInput job={job} canType={canType} />{error && <p className="err" role="alert">{error}</p>}</section>
      <footer>{!job.done && <Btn kind="danger" disabled={cancelling} onClick={cancel}>{t("Stop")}</Btn>}<Btn onClick={() => setExpanded(false)}>{t("Hide")}</Btn>{job.done && <Btn kind="primary" onClick={onClose}>{t("Close")}</Btn>}</footer>
    </section>
  </Modal>;
}
