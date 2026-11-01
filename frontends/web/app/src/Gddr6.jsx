import { num, t, useApp, usePage } from "./lib.jsx";
import { Btn, Card, useMobile } from "./ui.jsx";

export default function Gddr6() {
  const mobile = useMobile();
  const state = usePage("gddr6");
  const { live, job, act, running, stopJob } = useApp();
  const monitor = live?.gddr6 || {};
  const sample = monitor.sample || {};
  const owned = job?.kind === "gddr6.monitor" && !job.done;
  const external = state?.external?.state === "active";
  const active = monitor.active || owned || external;
  const current = owned && Number.isFinite(job.sample_age) && job.sample_age <= 15 && Array.isArray(job.sample?.chips) ? job.sample : sample;
  const readings = Array.isArray(current.chips) ? current.chips : [];
  if (!mobile) {
    return <section className="card desktop-memory-bar desktop-memory-control">
      <div className="desktop-memory-summary-row"><span>GDDR6</span>
        <b>{Number.isFinite(current.average_c) ? `${num(current.average_c, 1)} °C` : t("Waiting for sample")}</b>
        {Number.isFinite(current.hotspot_c) && <span className="desktop-memory-hotspot">{t("Hotspot")} {num(current.hotspot_c, 1)} °C</span>}
        <div className="row">
    {owned ? <Btn small onClick={stopJob}>{t("Stop monitoring")}</Btn> : <Btn small disabled={!state?.can_monitor || active || running} onClick={() => act({ action: "gddr6.monitor", level: 2, title: t("Monitor live"), body: t("The eight GDDR6 chips, read straight from the memory controller. Monitor live applies the SMU patch and starts a reading session that stops on its own after ten minutes.") })}>{t("Monitor live")}</Btn>}
    {state && !state.repository_ready && !state.kernel_driver && <Btn small disabled={running || active} onClick={() => act({ action: "gddr6.prepare", level: 1, title: t("Prepare readings") })}>{t("Prepare readings")}</Btn>}</div>
      </div>
      {readings.length > 0 && <div className="desktop-memory-readings">{Array.from({ length: 8 }, (_, index) => {
        const chip = readings.find(entry => entry.chip === index);
        return <div key={index}><span>Chip {index}</span><b>{Number.isFinite(chip?.temperature_c) ? `${num(chip.temperature_c, 1)} °C` : t("Not detected")}</b>{Number.isInteger(chip?.code) && <small> · MR3 0x{chip.code.toString(16).toUpperCase().padStart(2, "0")}</small>}</div>;
      })}</div>}
      {state?.blocker && !active && <p className="note">{state.blocker}</p>}
      {current.blocked_reason && <p className="notice" role="status">{current.blocked_reason}</p>}
    </section>;
  }
  return <Card className="memory-control memory-readings-only">
    <div className="memory-chips">{Array.from({ length: 8 }, (_, index) => {
      const chip = readings.find(entry => entry.chip === index);
      return <div key={index}><span>Chip {index}</span><b>{Number.isFinite(chip?.temperature_c) ? `${num(chip.temperature_c, 1)} °C` : "—"}</b></div>;
    })}</div>
    <div className="row memory-actions">{owned ? <Btn small onClick={stopJob}>{t("Stop monitoring")}</Btn> : <Btn small disabled={!state?.can_monitor || active || running} onClick={() => act({ action: "gddr6.monitor", level: 2, title: t("Monitor live"), body: t("The eight GDDR6 chips, read straight from the memory controller. Monitor live applies the SMU patch and starts a reading session that stops on its own after ten minutes.") })}>{t("Monitor live")}</Btn>}
      {state && !state.repository_ready && !state.kernel_driver && <Btn small disabled={running || active} onClick={() => act({ action: "gddr6.prepare", level: 1, title: t("Prepare readings") })}>{t("Prepare readings")}</Btn>}</div>
    {state?.blocker && !active && <p className="note">{state.blocker}</p>}
    {current.blocked_reason && <p className="notice" role="status">{current.blocked_reason}</p>}
  </Card>;
}
