import { useState } from "react";
import { keep, num, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, Dialog, Fold, Number_, ProfileEditor, Read, Tile, useStored } from "../ui.jsx";

// Mirrors cpu_command_policy.validate_detection_target, which stays the authority.
const PROFILES = [
  { key: "board_average", name: keep("Average board"), frequency: 3550, vid: 1050, temperature: 90 },
  { key: "mid_point", name: keep("Mid point"), frequency: 3850, vid: 1150, temperature: 90 },
  { key: "safe_maximum", name: keep("Safe maximum"), frequency: 4000, vid: 1275, temperature: 90 },
];
const fields = () => [["frequency", t("Frequency"), 3100, 4200, "MHz"], ["vid", "VID", 950, 1325, "mV"], ["temperature", t("Temperature cap"), 70, 90, "°C"]];
const overview = () => [["model_name", t("Processor")], ["architecture", t("Architecture")], ["topology", t("Topology")], ["platform_process", t("Platform / process")],
  ["microcode", t("Microcode")], ["cache", t("Cache hierarchy")], ["features", t("Instruction features")]];

export default function Cpu() {
  const { act, live } = useApp();
  const data = usePage("cpu");
  const [profiles, setProfiles] = useStored("cpu-profiles", PROFILES);
  const [chosen, setChosen] = useState(0);
  const [manual, setManual] = useState(false);
  const [scale, setScale] = useState(-34);
  const [force, setForce] = useState(false);
  const [editing, setEditing] = useState(null);
  const [review, setReview] = useState(false);
  if (!data) return <Card title={t("CPU / SMU")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const profile = profiles[chosen], cpu = live?.metrics?.cpu || {};
  const unlock = data.unlock || {}, processor = unlock.processor || {}, enabled = data.persistence.enabled;
  const apply = () => { act({ action: "cpu.apply", level: 1, title: manual ? t("Apply temporary OC + manual scale") : t("Apply configuration + automatic scale"),
    body: `${profile.frequency} MHz · ${manual ? `${t("Scale")} ${scale}` : `${profile.vid} mV`} · ${profile.temperature} °C`,
    params: { frequency: profile.frequency, vid: profile.vid, temperature: profile.temperature, manual, scale }, go: t("Apply") }); };
  const cores = new Map((unlock.cores || []).map((core) => [core.index, core]));
  const slots = Array.from({ length: 8 }, (_, i) => {
    const core = cores.get(i) || (cpu.per_core_percent && i < cpu.per_core_percent.length ? { frequency_mhz: (cpu.per_core_frequency_mhz || [])[i], usage_percent: cpu.per_core_percent[i] } : null);
    return core;
  });
  return (
    <>
    <div className="cols two">
      <div className="stack">
        <Card title={t("Operating profile")} sub={t("One click sets the range. The pencil changes name and frequencies.")}>
          <div className="tiles profiles">{profiles.map((item, i) => <Tile key={item.key} label={t(item.name)} value={`${item.frequency} MHz`} note={`${item.vid} mV · ${item.temperature} °C`}
            on={i === chosen} onClick={() => setChosen(i)} onEdit={() => setEditing(i)} />)}</div>
        </Card>
        <Card title={t("Live scale test")}>
          <Check checked={manual} onChange={setManual}>{t("Use manual scale")}</Check>
          <Number_ label={t("Scale")} min={-50} max={0} value={scale} onChange={setScale} disabled={!manual} unit="scale" />
          <p className="note">{t("Enter the exact scale you want. It is stress-tested in 100 MHz steps before it stays applied, the way automatic detection tests its own.")}</p>
        </Card>
        <div className="action-dock"><Btn kind="primary" wide onClick={apply}>{manual ? t("Apply temporary OC + manual scale") : t("Apply configuration + automatic scale")}</Btn></div>
        <Fold title={t("Processor overview")}>
          <div className="reads">{overview().map(([key, label]) => <Read key={key} label={label} value={processor[key] || t("Not exposed")} />)}
            <Read label={t("Total CPU load")} value={num(processor.total_usage_percent ?? cpu.usage_percent)} unit="%" /></div>
        </Fold>
      </div>
      <div className="stack">
        <Card title={t("Runtime status")} pill={enabled ? t("Persistence") : t("Temporary")} tone={enabled ? "blue" : "green"}>
          <div className="tiles">
            <Tile label={t("Boot persistence")} value={data.persistence.value} note={data.persistence.detail} tone={enabled ? "ok" : ""} />
            <Tile label={t("Total CPU load")} value={`${num(cpu.usage_percent)} %`} />
            <Tile label={t("Applied tuning")} value={data.tuning.applied_value} note={data.tuning.applied_detail} />
            <Tile label={t("Detection reference")} value={data.tuning.detection_value} note={data.tuning.detection_detail} />
            <Tile label={t("Active scale")} value={data.tuning.live_value} note={data.tuning.live_detail} />
            <Tile label={t("Live CPU status")} value={`${num(cpu.temperature_c)} °C | ${num(cpu.frequency_mhz)} MHz`} />
          </div>
        </Card>
        <Card title={t("Live core monitor")} pill={t("{cores} cores / {threads} threads", { cores: unlock.physical_cores ?? "--", threads: unlock.logical_cpus ?? "--" })} tone="blue" sub={t("Detected by the OS")}>
          <div className="cores">{slots.map((core, i) => <div className="core" key={i}><b>N{i + 1}</b>{core
            ? <><span>{core.frequency_mhz ? (core.frequency_mhz / 1000).toFixed(2) : "--"} GHz</span><div className="bar"><i style={{ width: `${core.usage_percent || 0}%` }} /></div><u>{num(core.usage_percent)} %</u></>
            : <><span>{t("Hidden")}</span><div className="bar" /><u /></>}</div>)}</div>
        </Card>
        <Card title={t("Boot persistence")}>
          <div className="row">
            <Btn kind="soft" wide onClick={() => act({ action: "cpu.persist", level: 1, title: t("Enable / update CPU persistence") })}>{t("Save for startup")}</Btn>
            <Btn wide onClick={() => setReview(true)}>{t("Review persistence")}</Btn>
            <Btn kind="danger" wide disabled={!enabled} onClick={() => act({ action: "cpu.persist_off", level: 1, title: t("Disable CPU boot service") })}>{t("Remove from boot")}</Btn>
          </div>
        </Card>
        <Fold risk title={t("Unlock hidden CPU cores")}><p className="note">{t("CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes.")}</p>
          <Check checked={force} onChange={setForce}>{t("Force a non-standard core mask (-f)")}</Check>
          <Btn kind="danger" disabled={!!unlock.unlocked} onClick={() => act({ action: "cpu.unlock", level: 2, params: { force_mask: force }, title: t("Unlock CPU cores and restart"),
            warning: t("The core unlock does not last: it is applied after the system starts, so a full power-off or a cold start brings the board back to 6 cores. If the board is ever unstable with 8 cores, shut it down completely and start it again: it comes back to 6. If it is stable and you want 8 cores at every start, the permanent way is the firmware, through the external UEFI menu workflow. The guide opens in your browser; this application does not flash firmware, change NVRAM, or reboot the system.") })}>{t("Unlock cores and restart")}</Btn>
        </Fold>
      </div>
      {review && <Dialog title={t("Boot persistence")} onClose={() => setReview(false)} footer={<Btn onClick={() => setReview(false)}>{t("Close")}</Btn>}>
        <div className="reads">{Object.entries(data.persistent || {}).filter(([, v]) => typeof v !== "object").map(([k, v]) => <Read key={k} label={k} value={String(v)} />)}</div></Dialog>}
      {editing !== null && <ProfileEditor profile={profiles[editing]} fields={fields()} onClose={() => setEditing(null)}
        onSave={(next) => { setProfiles(profiles.map((p, i) => (i === editing ? next : p))); setEditing(null); }} />}
    </div></>
  );
}
