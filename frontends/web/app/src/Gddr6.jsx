import { num, t, useApp, usePage } from "./lib.jsx";
import { Btn, Card, Pill } from "./ui.jsx";

export default function Gddr6() {
  const state = usePage("gddr6");
  const { live, job, act, running, stopJob } = useApp();
  const monitor = live?.gddr6 || {};
  const sample = monitor.sample || {};
  const chips = sample.chips || [];
  const owned = job?.kind === "gddr6.monitor" && !job.done;
  const external = state?.external?.state === "active";
  const active = monitor.active || owned || external;
  return <Card title={t("GDDR6 memory temperature")} className="memory-control" pill={active ? t("Live") : t("Not connected")} tone={active ? "green" : ""}>
    {sample.average_c != null && <div className="memory-summary"><div><span>{t("Average")}</span><b>{num(sample.average_c, 1)} <small>°C</small></b></div><div><span>{t("Hotspot")}</span><b>{num(sample.hotspot_c, 1)} <small>°C</small></b></div></div>}
    <div className="row memory-actions">{owned ? <Btn onClick={stopJob}>{t("Stop monitoring")}</Btn> : <Btn kind="primary" disabled={!state?.can_monitor || active || running} onClick={() => act({ action: "gddr6.monitor", level: 2, title: t("Monitor live"), body: t("The eight GDDR6 chips, read straight from the memory controller. Monitor live applies the SMU patch and starts a reading session that stops on its own after ten minutes.") })}>{t("Monitor live")}</Btn>}
      {state && !state.repository_ready && !state.kernel_driver && <Btn disabled={running || active} onClick={() => act({ action: "gddr6.prepare", level: 1, title: t("Prepare readings") })}>{t("Prepare readings")}</Btn>}
      {state?.kernel_driver && <Pill>bc250_memory</Pill>}</div>
    {state?.blocker && !active && <p className="note">{state.blocker}</p>}
    {external && <p className="note">{t("BC250-Telemetry's memory service is running. Its readings will appear here.")}</p>}
    {active && <p className="note">{t("Monitoring")} · 5 s · 10 min</p>}
    {chips.length > 0 && <div className="memory-chips">{chips.map((chip) => <div key={chip.chip}><span>Chip {chip.chip}</span><b>{num(chip.temperature_c, 1)} °C</b></div>)}</div>}
    {sample.blocked_reason && <p className="notice" role="status">{sample.blocked_reason}</p>}
  </Card>;
}
