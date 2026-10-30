import { useState } from "react";
import { keep, num, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, ControlTabs, Fold, Number_, ProfileDeck, ProfileEditor, Read, useStored } from "../ui.jsx";

const PROFILES = [
  { key: "board_average", name: keep("Average board"), frequency: 3550, vid: 1050, temperature: 90 },
  { key: "mid_point", name: keep("Mid point"), frequency: 3850, vid: 1150, temperature: 90 },
  { key: "safe_maximum", name: keep("Safe maximum"), frequency: 4000, vid: 1275, temperature: 90 },
];
const fields = () => [["frequency", t("Frequency"), 3100, 4200, "MHz"], ["vid", "VID", 950, 1325, "mV"], ["temperature", t("Temperature cap"), 70, 90, "°C"]];

export default function Cpu() {
  const { act, live, running } = useApp();
  const data = usePage("cpu");
  const [profiles, setProfiles] = useStored("cpu-profiles", PROFILES);
  const [chosen, setChosen] = useState(PROFILES[0].key), [tab, setTab] = useState("profiles");
  const [manual, setManual] = useState(false), [scale, setScale] = useState(-34);
  const [force, setForce] = useState(false), [editing, setEditing] = useState(null);
  if (!data) return <Card><p className="note">{t("Waiting for data…")}</p></Card>;
  const profile = profiles.find((item) => item.key === chosen) || profiles[0], cpu = live?.metrics?.cpu || {};
  const unlock = data.unlock || {}, processor = unlock.processor || {}, enabled = data.persistence.enabled;
  const cores = new Map((unlock.cores || []).map((core) => [core.index, core]));
  const apply = () => act({ action: "cpu.apply", level: 1, title: manual ? t("Apply temporary OC + manual scale") : t("Apply configuration + automatic scale"),
    body: `${profile.frequency} MHz · ${manual ? `${t("Scale")} ${scale}` : `${profile.vid} mV`} · ${profile.temperature} °C`,
    params: { frequency: profile.frequency, vid: profile.vid, temperature: profile.temperature, manual, scale } });
  return <div className="control-workspace cpu-workspace">
    <ControlTabs items={[["profiles", t("Profiles"), "nav_cpu"], ["monitor", t("Monitoring"), "nav_performance"], ["boot", t("Boot persistence"), "nav_settings"]]} value={tab} onChange={setTab} />
    {tab === "profiles" && <Card className="control-primary">
      <ProfileDeck profiles={profiles.map((p) => ({ ...p, name: t(p.name) }))} selected={{ ...profile, name: t(profile.name) }} onSelect={setChosen} onEdit={setEditing} />
      {editing && <ProfileEditor key={editing} profile={profiles.find((p) => p.key === editing)} fields={fields()} onClose={() => setEditing(null)} onSave={(next) => { setProfiles(profiles.map((p) => p.key === editing ? next : p)); setEditing(null); }} />}
      <section className="scale-control"><h3>{t("Live scale test")}</h3><div className="mode-choice"><button className={!manual ? "on" : ""} aria-pressed={!manual} onClick={() => setManual(false)}>{t("Automatic")}</button><button className={manual ? "on" : ""} aria-pressed={manual} onClick={() => setManual(true)}>{t("Manual scale")}</button></div>{manual && <Number_ label={t("Scale")} min={-50} max={0} value={scale} onChange={setScale} unit="scale" />}
        <details className="control-explanation"><summary>{t("Details")}</summary><p className="note">{t("Enter the exact scale you want. It is stress-tested in 100 MHz steps before it stays applied, the way automatic detection tests its own.")}</p></details></section>
      <Btn kind="primary" wide disabled={running || manual && (!Number.isInteger(scale) || scale < -50 || scale > 0)} onClick={apply}>{t("Review and apply")}</Btn>
    </Card>}
    {tab === "monitor" && <><Card title={t("Live core monitor")} pill={t("{cores} cores / {threads} threads", { cores: unlock.physical_cores ?? "--", threads: unlock.logical_cpus ?? "--" })}>
      <Read label={t("Frequency")} value={num(cpu.frequency_mhz)} unit="MHz" /><Read label={t("Total CPU load")} value={num(cpu.usage_percent)} unit="%" /><Read label={t("Temperature")} value={num(cpu.temperature_c, 1)} unit="°C" />
      <div className="cores">{Array.from({ length: 8 }, (_, i) => { const core = cores.get(i), clock = core?.frequency_mhz ?? cpu.per_core_frequency_mhz?.[i], usage = core?.usage_percent ?? cpu.per_core_percent?.[i]; return <div className="core" key={i}><b>N{i + 1}</b><span>{clock ? `${(clock / 1000).toFixed(2)} GHz` : t("Hidden")}</span><div className="bar"><i style={{ width: `${usage || 0}%` }} /></div><u>{usage == null ? "—" : `${num(usage)} %`}</u></div>; })}</div>
    </Card><Card title={t("Runtime status")}><Read label={t("Applied tuning")} value={data.tuning.applied_value} /><Read label={t("Active scale")} value={data.tuning.live_value} /><Read label={t("Detection reference")} value={data.tuning.detection_value} /></Card></>}
    {tab === "boot" && <><Card title={t("Boot persistence")} pill={enabled ? t("Enabled") : t("Temporary")}><Read label={t("Status")} value={data.persistence.value} /><p className="note">{data.persistence.detail}</p><Btn kind="primary" disabled={running} onClick={() => act({ action: "cpu.persist", level: 1, title: t("Enable / update CPU persistence") })}>{t("Save for startup")}</Btn><Btn disabled={!enabled || running} onClick={() => act({ action: "cpu.persist_off", level: 1, title: t("Disable CPU boot service") })}>{t("Remove from boot")}</Btn><details className="control-explanation"><summary>{t("Review persistence")}</summary>{Object.entries(data.persistent || {}).filter(([, v]) => typeof v !== "object").map(([key, value]) => <Read key={key} label={key} value={String(value)} />)}</details></Card>
      <Fold title={t("Processor overview")}>{[["model_name", keep("Processor")], ["architecture", keep("Architecture")], ["topology", keep("Topology")], ["platform_process", keep("Platform / process")], ["microcode", keep("Microcode")], ["cache", keep("Cache hierarchy")], ["features", keep("Instruction features")]].map(([key, label]) => <Read key={key} label={t(label)} value={processor[key] || t("Not exposed")} />)}</Fold>
      <Fold risk title={t("Unlock hidden CPU cores")}><p className="note">{t("CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes.")}</p><Check checked={force} onChange={setForce}>{t("Force a non-standard core mask (-f)")}</Check><Btn kind="danger" disabled={!!unlock.unlocked || running} onClick={() => act({ action: "cpu.unlock", level: 2, params: { force_mask: force }, title: t("Unlock CPU cores and restart") })}>{t("Unlock cores and restart")}</Btn></Fold>
    </>}
  </div>;
}
