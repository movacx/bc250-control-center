import { TerminalInput } from "../DesktopActivity.jsx";
/** PC presentation of the existing hardware actions. Mobile pages stay separate. */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { keep, num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Check, ControlTabs, CpuCores, Fold, Number_, ProfileDeck, ProfileEditor, Read } from "../ui.jsx";
import VoltageLab from "./VoltageLab.jsx";
import CoreUnlock from "./CoreUnlock.jsx";

function Tabs({ value, onChange, voltage = false }) {
  const items = [["control", t("Hardware control"), "nav_cpu"], ["sensors", t("Sensors"), "nav_performance"]];
  if (voltage) items.push(["voltage", t("Voltage laboratory"), "nav_settings"]);
  return <ControlTabs items={items} value={value} onChange={onChange} />;
}

function DesktopVoltage({ raw, gpu }) {
  const lab = raw.voltage_lab || {};
  return <div className="desktop-lab-layout">
    <Card className="desktop-voltage-panel" title={t("Voltage curve")} sub={t("Choose a preset or adjust each active point before reviewing the changes.")}>
      <VoltageLab data={raw} />
    </Card>
    <Card className="desktop-lab-reference" title={t("Reference")}>
      <Tiles items={[
        [t("GPU voltage"), `${num(pick(raw.voltaje_actual, gpu.voltage_mv))} mV`, t("OD / SMU telemetry")],
        [t("Core clock"), `${num(pick(raw.sclk_actual, gpu.frequency_mhz))} MHz`],
        [t("Active points"), lab.points?.length ?? 0],
        [t("Allowed voltage range"), lab.minimum_mv != null && lab.maximum_mv != null ? `${lab.minimum_mv}–${lab.maximum_mv} mV` : "—"],
      ]} />
      <p className="note">{t("Changes are reviewed before they are applied.")}</p>
    </Card>
  </div>;
}
function Tiles({ items }) {
  return <div className="desktop-sensor-tiles">{items.map(([label, value, note]) => <div className="tile" key={label}><small>{label}</small><strong>{value ?? "--"}</strong>{note && <span>{note}</span>}</div>)}</div>;
}
function SessionConsole({ kind }) {
  const { job, registerConsole, session, stopJob } = useApp();
  const output = useRef(null);
  const matches = job?.kind?.startsWith(kind);
  useLayoutEffect(() => { registerConsole?.(kind); return () => registerConsole?.(null); }, [kind, registerConsole]);
  useEffect(() => { if (output.current) output.current.scrollTop = output.current.scrollHeight; }, [job?.text]);
  return <div className="desktop-console-host">
    <pre className="console desktop-session-console" ref={output} tabIndex={0} data-job-console={kind} aria-label={t("Terminal output")}>{matches ? job.text || t("Waiting for data…") : t("No hardware command has been run.")}</pre>
    {matches && <><TerminalInput job={job} canType={session?.password} /><div className="desktop-console-actions"><span role="status">{job.done ? (job.ok ? t("Done") : t("Failed")) : job.waiting ? t("Administrator password") : t("Running…")}</span>{!job.done && <Btn small kind="danger" onClick={stopJob}>{t("Stop")}</Btn>}</div></>}
  </div>;
}
function Overview({ processor, cpu }) {
  return <section className="desktop-overview"><h3>{t("Processor overview")}</h3><div className="desktop-specs">{[["model_name", keep("Processor")], ["architecture", keep("Architecture")], ["topology", keep("Topology")], ["platform_process", keep("Platform / process")], ["microcode", keep("Microcode")], ["cache", keep("Cache hierarchy")], ["features", keep("Instruction features")]].map(([key, label]) => <Read key={key} label={t(label)} value={processor[key] || t("Not exposed")} />)}<Read label={t("Total CPU load")} value={num(cpu.usage_percent)} unit="%" /></div></section>;
}

export function DesktopCpu({ data, profiles, profile, chosen, setChosen, editing, setEditing, setProfiles, fields, manual, setManual, scale, setScale, apply }) {
  const { act, live, running, job } = useApp();
  const [tab, setTab] = useState("control");
  const cpu = live?.metrics?.cpu || {}, unlock = data.unlock || {}, processor = unlock.processor || {};
  const persistence = data.persistence || {}, tuning = data.tuning || {};
  const runtime = <Tiles items={[[t("Boot persistence"), persistence.value, persistence.detail], [t("Last operation"), job?.kind?.startsWith("cpu") ? job.label : "—", job?.kind?.startsWith("cpu") ? (job.done ? t("Done") : t("Running…")) : t("No hardware command has been run.")], [t("Applied tuning"), tuning.applied_value, tuning.applied_detail], [t("Detection reference"), tuning.detection_value, tuning.detection_detail], [t("Active scale"), tuning.live_value, tuning.live_detail], [t("Live CPU state"), `${num(cpu.temperature_c, 0)} °C | ${num(cpu.frequency_mhz)} MHz`, t("Temperature and average clock")]]} />;
  return <div className="desktop-layout desktop-cpu"><Tabs value={tab} onChange={setTab} />
    {tab === "control" ? <div className="desktop-cpu-columns"><div className="stack">
      <Card><section className="desktop-inset"><h3>{t("Operating profile")}</h3><p className="note">{t("One click sets the range. The pencil changes the name and frequencies.")}</p>
        <ProfileDeck profiles={profiles.map(p => ({ ...p, name: t(p.name) }))} selected={{ ...profile, name: t(profile.name) }} onSelect={setChosen} onEdit={setEditing} />
        {editing && <ProfileEditor key={editing} profile={profiles.find(p => p.key === editing)} fields={fields()} onClose={() => setEditing(null)} onSave={next => { setProfiles(profiles.map(p => p.key === editing ? next : p)); setEditing(null); }} />}</section>
        <section className="desktop-inset"><h3>{t("Live scale test")}</h3><div className="desktop-scale"><div><Check checked={manual} onChange={setManual}>{t("Use manual scale")}</Check><p className="note">{t("Enter the exact scale you want. It is stress-tested in 100 MHz steps before it stays applied, the way automatic detection tests its own.")}</p></div><Number_ label={t("Scale")} min={-50} max={0} value={scale} onChange={setScale} unit="scale" disabled={!manual} /></div></section>
        <Btn kind="primary" wide disabled={running || manual && (!Number.isInteger(scale) || scale < -50 || scale > 0)} onClick={apply}>{manual ? t("Apply temporary OC + manual scale") : t("Apply configuration + automatic scale")}</Btn>
      </Card><Card><SessionConsole kind="cpu" /></Card></div>
      <Card className="desktop-cpu-runtime"><section className="desktop-inset"><h3>{t("Runtime status")}</h3><p className="note">{t("What is used in this session and what happens at the next boot.")}</p>{runtime}</section>
        <section className="desktop-inset"><h3>{t("Boot persistence")}</h3><div className="desktop-action-row"><Btn disabled={running} onClick={() => act({ action: "cpu.persist", level: 1, title: t("Enable / update CPU persistence") })}>{t("Save for startup")}</Btn><details><summary className="btn">{t("Review persistence")}</summary><div className="desktop-persistence-details">{Object.entries(data.persistent || {}).filter(([,v]) => typeof v !== "object").map(([key,value]) => <Read key={key} label={key} value={String(value)} />)}</div></details><Btn kind="danger" disabled={!persistence.enabled || running} onClick={() => act({ action: "cpu.persist_off", level: 1, title: t("Disable CPU boot service") })}>{t("Remove from boot")}</Btn></div></section>
        <CoreUnlock unlock={unlock} controls={data.unlock_controls} />
      </Card></div> : <div className="stack"><Card title={t("Live core monitor")} pill={t("{cores} cores / {threads} threads", { cores: cpu.physical_cores ?? "--", threads: cpu.logical_cores ?? "--" })}><Tiles items={[[t("Frequency"), `${num(cpu.frequency_mhz)} MHz`], [t("Temperature"), `${num(cpu.temperature_c,1)} °C`], [t("Total CPU load"), `${num(cpu.usage_percent)} %`]]} /><CpuCores cpu={cpu} /></Card><Card title={t("Runtime status")}>{runtime}<Overview processor={processor} cpu={cpu} /></Card></div>}
  </div>;
}

export function DesktopCompute({ cu, current, masks, changed, active, applied, se0, se1, ready, editable, canControl, toggle, setPending, sync, run, bootSync }) {
  const { act, live, running } = useApp();
  const [tab, setTab] = useState("control");
  const dashboard = usePage("dashboard");
  const gpu = live?.metrics?.gpu || {}, sensors = live?.metrics?.sensors || {}, power = live?.metrics?.power || {};
  const pop = mask => (mask.toString(2).match(/1/g) || []).length;
  const status = <Tiles items={[[t("Service"), cu.service_enabled ? t("Enabled") : cu.service_installed ? t("Disabled") : t("Not installed")], [t("Boot persistence"), bootSync], [t("GPU frequency"), `${num(gpu.frequency_mhz)} MHz`], [t("GPU load"), `${num(pick(gpu.usage_percent, gpu.compute_busy_percent))} %`], [t("GPU power"), `${num(pick(power.value_w,gpu.power_w))} W`], [t("GPU temperature"), `${num(gpu.temperature_c,1)} °C`], [t("VRM temperature"), `${num(sensors.vrm_mos_temperature_c,1)} °C`], [t("Fan speed"), `${num(dashboard?.performance?.fan_rpm)} RPM`]]} />;
  return <div className="desktop-layout desktop-cu"><Tabs value={tab} onChange={setTab} />{tab === "control" ? <>
    <Card className="desktop-cu-routing"><div className="legend desktop-cu-legend">{[["D+", t("Driver + routed"), "D"], ["S+", t("Live unlock"), "S"], ["D!", t("Driver blocked"), "X"], ["--", t("Not routed"), "off"]].map(([token,label,kind]) => <span key={token}><i className={kind}>{token}</i>{label}</span>)}</div>
      <div className="desktop-cu-matrix"><div className="desktop-cu-heading"><b>{t("Shader row")}<small>SE / SH</small></b>{[0,1,2,3,4].map(c => <b key={c}>WGP{c}<small>CU {2*c}–{2*c+1}</small></b>)}<b>CUs<small>{t("Active")} / 10</small></b></div>
      {cu.rows.slice(0,4).map((row,r) => <div className="desktop-cu-matrix-row" key={r}><b className="desktop-cu-row-name">{row.name || `SE${r>>1}.SH${r&1}`}</b>{[0,1,2,3,4].map(c => { const on=!!(masks[r] & 1<<c), edited=on!==!!(current[r] & 1<<c), token=edited?(on?"+":"−"):row.tokens?.[c] || (on?"S+":"--"), kind=edited?"chg":({"D+":"D","S+":"S","D!":"X"}[token] || "off"); return <button key={c} className={`desktop-cu-cell ${kind}`} disabled={!editable} aria-pressed={on} aria-label={`${row.name || `SE${r>>1}.SH${r&1}`} WGP${c} · CU ${2*c}–${2*c+1} · ${token}`} onClick={() => toggle(r,c)}><b>{token}</b><span>{on?t("Routed"):t("Inactive")}</span></button>; })}<b className="desktop-cu-total">{2*pop(masks[r])} / 10</b></div>)}</div>
    </Card><Card className="desktop-cu-actions"><section className="desktop-inset"><h3>{t("Target")}: {active} / 40 CU</h3><p className="note">{changed?`${t("Changed WGP pairs")}: ${changed}`:t("No pending WGP changes.")}</p>{se0!==se1 && <p className="desktop-balance-warning">{t("SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine only add heat.",{se0,se1,effective:Math.min(se0,se1)*2,idle:Math.abs(se0-se1)})}</p>}
      {!ready && <p className="notice">{t("CU write actions are locked until a verified root-owned backend is installed.")}</p>}<div className="desktop-action-row"><Btn disabled={!canControl} onClick={sync}>{t("Unlock / Sync")}</Btn><Btn disabled={!changed||running} onClick={()=>setPending(null)}>{t("Reset selection")}</Btn><Btn kind="primary" disabled={!changed||!editable} onClick={()=>act({action:"cu.apply",level:2,inline:true,params:{masks:[...masks]},title:t("Apply live table"),summary:[[t("Applied tuning"),`${applied} / 40 CU`],[t("Selection"),`${active} / 40 CU`],["SE0 / SE1",`${se0} / ${se1} CU`]],warning:t("Stop every game, benchmark, and 3D workload before continuing.")})}>{t("Apply now")}</Btn></div></section>
      <section className="desktop-inset"><h3>{t("Boot persistence")}</h3><p className="note">{t("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, Install service — to make the change survive a reboot.")}</p><div className="desktop-action-row"><Btn disabled={!editable||!!changed} onClick={()=>act({action:"cu.save",level:1,params:{masks:[...current]},title:t("Save selection")})}>{t("Save selection")}</Btn><Btn disabled={!editable||!!changed} onClick={()=>run("install_service",t("Install service"))}>{t("Install service")}</Btn><Btn kind="danger" disabled={!cu.service_installed||!canControl} onClick={()=>run("remove_service",t("Remove service"))}>{t("Remove service")}</Btn><Btn kind="danger" disabled={!editable} onClick={()=>run("factory",t("Restore factory"),2)}>{t("Restore factory")}</Btn></div></section>
    </Card></> : <><Card title={t("Runtime status")}>{status}</Card><Card title={t("Register diagnostics")}><div className="desktop-specs">{cu.rows.slice(0,4).map((row,r)=><Read key={r} label={row.name||`SE${r>>1}.SH${r&1}`} value={row.spi||"--"} note={`Driver: ${row.driver_mask??cu.driver_masks?.[r]??"--"} · CC: ${row.cc||"--"}`} />)}{[["UMR",cu.umr],["ASIC",cu.asic],["amdgpu · active_cu_number",cu.amdgpu_active_cus],[t("Source"),cu.register_source],[t("Updated"),cu.updated_at]].map(([label,value])=><Read key={label} label={label} value={value||"--"} />)}</div></Card></>}
  </div>;
}

export function DesktopGpu({ raw, gpu, profiles, selected, cur, volts, lowest, highest, editing, setEditing, setEdited, edited, setChosen, pending, opts, setCompat, backend, actionBusy, running, control, high, unlocked, stops }) {
  const { act } = useApp();
  const [tab, setTab] = useState("control");
  const apply = () => act({action:"gpu.profile",level:selected.max>2000?2:1,params:{min:selected.min,max:selected.max},title:selected.label,body:`${selected.min}–${selected.max} MHz`});
  return <div className="desktop-layout desktop-gpu">
    <Tabs value={tab} onChange={setTab} voltage />
    {tab === "voltage" ? <DesktopVoltage raw={raw} gpu={gpu} /> : tab === "control" ? (
      <div className={`desktop-gpu-control ${backend.startsWith("cyan") ? "" : "no-compat"} ${high.available ? "" : "no-high-points"}`}>
        <Card className="desktop-gpu-profiles"><section className="desktop-inset"><h3>{t("Operating profile")}</h3><p className="note">{t("One click sets the range. The pencil changes the name and frequencies.")}</p><ProfileDeck profiles={profiles.map(p=>({...p,name:p.label,voltage:volts[p.max]}))} selected={{...selected,name:selected.label}} onSelect={setChosen} onEdit={key=>setEditing(profiles.find(p=>p.key===key))} />
      {editing && <ProfileEditor key={editing.key} profile={{name:editing.label,min:editing.min,max:editing.max}} fields={[["min",t("Minimum frequency"),lowest,highest,"MHz"],["max",t("Maximum frequency"),lowest,highest,"MHz"]]} onClose={()=>setEditing(null)} onSave={p=>{setEdited({...edited,[editing.key]:{label:p.name,min:Math.min(p.min,p.max),max:Math.max(p.min,p.max)}});setChosen(editing.key);setEditing(null);}} />}</section></Card>
        <Card className="desktop-gpu-range"><section className="desktop-inset"><div className="desktop-section-heading"><h3>{t("Frequency range")}</h3><strong>{selected.min} – {selected.max} MHz</strong></div><div className="desktop-frequency-fields"><Number_ label={t("Minimum frequency")} value={selected.min} min={lowest} max={selected.max} unit="MHz" onChange={value=>{if(Number.isInteger(value)&&value>=lowest&&value<=selected.max){setEdited({...edited,[selected.key]:{...edited[selected.key],min:value}});setChosen(selected.key);}}} /><Number_ label={t("Maximum frequency")} value={selected.max} min={selected.min} max={highest} unit="MHz" onChange={value=>{if(Number.isInteger(value)&&value>=selected.min&&value<=highest){setEdited({...edited,[selected.key]:{...edited[selected.key],max:value}});setChosen(selected.key);}}} /></div>{pending&&<p className="note">{t("Selected in the UI (not applied yet)")}</p>}</section><div className="desktop-action-row desktop-gpu-apply"><Btn disabled={pending||actionBusy} onClick={()=>act({action:"gpu.save_boot",level:1,title:t("Save active range for startup")})}>{t("Save for startup")}</Btn><Btn kind="primary" disabled={actionBusy} onClick={apply}>{t("Review and apply range")}</Btn></div></Card>
        <Card className="desktop-gpu-service"><section className="desktop-inset"><h3>{t("Governor service")}</h3><Read label={t("Status")} value={running ? t("Active") : t("Not connected")} /><div className="desktop-action-row"><Btn disabled={actionBusy} onClick={()=>act({action:"gpu.status",title:t("View status")})}>{t("View status")}</Btn><Btn disabled={actionBusy} onClick={()=>control("reiniciar",t("Restart service"))}>{t("Restart")}</Btn><Btn kind={running?"danger":""} disabled={actionBusy} onClick={()=>control(running?"desactivar":"activar",running?t("Stop governor"):t("Start governor"),running?2:1)}>{running?t("Stop governor"):t("Start governor")}</Btn></div></section></Card>
        {backend.startsWith("cyan") && <Card className="desktop-gpu-compat"><section className="desktop-inset"><h3>{t("Cyan kernel compatibility")}</h3><p className="note">{t("Change these only if the readings above are wrong.")}</p><div className="compat-fields">{[["set_method",t("Governor method"),[["smu","SMU"],["kernel","Kernel"]]],["usage_method",t("Usage reading"),[["busy-flag","busy-flag"],["process","process"],["kernel","kernel"]]],["temp_read",t("Temperature reading"),[["drm","DRM"],["sysfs","sysfs"]]]].map(([key,label,options])=><label className="field" key={key}><span>{label}</span><select className="input" value={opts[key]} onChange={e=>setCompat({...opts,[key]:e.target.value})}>{options.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>)}</div><div className="desktop-compat-actions"><Check checked={opts.metrics} onChange={v=>setCompat({...opts,metrics:v})}>{raw.fix_labels.metrics}</Check><Check checked={opts.frequencies} onChange={v=>setCompat({...opts,frequencies:v})}>{raw.fix_labels.frequency}</Check><Btn disabled={actionBusy} onClick={()=>act({action:"gpu.compat",level:opts.set_method==="kernel"?2:1,params:{set_method:opts.set_method,usage_method:opts.usage_method,metrics:opts.metrics,frequencies:opts.frequencies,temp_read:opts.temp_read},title:t("Cyan kernel compatibility")})}>{t("Apply compatibility")}</Btn></div></section></Card>}
        {high.available && <Card className="desktop-gpu-high-points" risk title={t("TOML points above 2000 MHz")} pill={unlocked?t("Enabled"):t("Commented")}><p className="note">{t("These frequencies are experimental and can crash the display or system.")}</p><Btn kind="danger" disabled={actionBusy||unlocked&&cur[1]>2000} onClick={()=>act({action:"gpu.high_points",level:2,params:{enable:!unlocked},title:unlocked?t("Re-comment the +2000 MHz points"):t("Uncomment +2000 MHz points"),body:t("This edits only the TOML safe-point blocks above 2000 MHz and validates the complete file. These frequencies are experimental, are not guaranteed stable, and can crash the display or system. This does not reload Cyan or change the live GPU range; use Apply active range explicitly after selecting a point.")})}>{unlocked?t("Re-comment the +2000 MHz points"):t("Uncomment +2000 MHz points")}</Btn></Card>}
      </div>
    ) : <div className="stack"><Card title={t("Runtime status")}><Tiles items={[[t("Core clock"),`${num(pick(raw.sclk_actual,gpu.frequency_mhz))} MHz`,t("Current SCLK state")],[t("GPU voltage"),`${num(pick(raw.voltaje_actual,gpu.voltage_mv))} mV`,t("OD / SMU telemetry")],[t("Temperature"),`${num(gpu.temperature_c,1)} °C`,t("Normal · hwmon")],[t("GPU load"),`${num(pick(gpu.usage_percent,gpu.compute_busy_percent))} %`,t("amdgpu activity")],[t("Memory clock"),`${num(pick(raw.mclk_actual,gpu.memory_frequency_mhz))} MHz`,t("Current MCLK state")],[t("Active range"),`${cur[0]}–${cur[1]} MHz`,t("Persistent in hardware")]]} /></Card><Fold title={t("Advanced GPU diagnostics")}><div className="desktop-specs">{stops.map(f=>volts[f]!=null&&<Read key={f} label={`${f} MHz`} value={volts[f]} unit="mV" />)}<Read label={t("Backend")} value={backend||"--"} /><Read label="config.toml" value={raw.config_path||"--"} /></div></Fold></div>}
  </div>;
}
