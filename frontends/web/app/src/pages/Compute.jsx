import { useEffect, useState } from "react";
import { num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Fold, Tile } from "../ui.jsx";

const cls = { "D+": "D", "S+": "S", "D!": "X" };
const pop = (mask) => (mask.toString(2).match(/1/g) || []).length;

export default function Compute() {
  const { act, live } = useApp();
  const page = usePage("cu");
  const [pending, setPending] = useState(null);
  const cu = page?.cu;
  const current = cu?.rows?.slice(0, 4).map((row) => Number(row.mask ?? 0)) || [];
  const signature = current.join(",");
  useEffect(() => { if (pending?.join(",") === signature) setPending(null); }, [signature, pending]);
  if (current.length !== 4) return <Card title={t("Compute Units")}><p className="note">{String(cu?.error || t("Waiting for data…"))}</p>
    <Btn kind="primary" onClick={() => act({ action: "cu.sync", title: t("Unlock / Sync") })}>{t("Unlock / Sync")}</Btn></Card>;
  const masks = pending || current;
  const active = masks.reduce((sum, m) => sum + 2 * pop(m), 0);
  const changed = masks.reduce((sum, m, i) => sum + pop(m ^ current[i]), 0);
  const ready = !!cu.privileged_backend_ready;
  const se0 = 2 * (pop(masks[0]) + pop(masks[1])), se1 = 2 * (pop(masks[2]) + pop(masks[3]));
  const gpu = live?.metrics?.gpu || {}, sensors = live?.metrics?.sensors || {}, power = live?.metrics?.power || {};
  const toggle = (r, c) => { const next = [...masks]; next[r] ^= 1 << c; setPending(next); };
  const run = (name, title, level = 1) => act({ action: "cu.action", level, params: { name }, title });
  return <>
    <Card className="cu-overview">
      <div className="cu-total"><div><span className="eyebrow">{t("Compute Units")}</span><strong>{active}<small>/ 40 CU</small></strong></div><div className="cu-engines"><span>SE0 <b>{se0}</b></span><span>SE1 <b>{se1}</b></span><span className={`pill ${se0 === se1 ? "green" : "orange"}`}>{se0 === se1 ? t("Balanced") : t("Unbalanced")}</span></div></div>
      <div className="cu-capacity">{Array.from({ length: 20 }, (_, i) => <i key={i} className={i < active / 2 ? "on" : ""} />)}</div>
      <div className="row"><span className="note">{changed ? t("{pairs} differ from the last authorized live table.", { pairs: `${changed} WGP` }) : t("No pending WGP changes.")}</span></div>
    </Card>
    <div className="cols two cu-layout"><div className="stack">
      <Card title={t("Live routing")} action={<div className="row"><Btn small disabled={!ready} onClick={() => setPending([7, 7, 7, 7])}>24 CU</Btn><Btn small disabled={!ready} onClick={() => setPending([31, 31, 31, 31])}>40 CU</Btn></div>}>
        <div className="wgp-rows">{masks.map((mask, r) => {
          const row = cu.rows[r], tokens = row.tokens || [];
          return <section className="wgp-row" key={r} aria-label={row.name || `SE${r >> 1}.SH${r & 1}`}><header><b id={`wgp-row-${r}`}>{row.name || `SE${r >> 1}.SH${r & 1}`}</b><span>{2 * pop(mask)} / 10 CU</span></header>
            <div className="wgp-cells">{Array.from({ length: 5 }, (_, c) => {
              const on = !!(mask & (1 << c)), was = !!(current[r] & (1 << c));
              const token = on && was && tokens[c] ? tokens[c] : on ? "S+" : "--";
              return <button type="button" key={c} className={on !== was ? "chg" : on ? cls[token] || "D" : "off"} aria-pressed={on}
                aria-describedby={`wgp-row-${r}`} onClick={() => toggle(r, c)} disabled={!ready}><small>WGP {c}</small>{" "}<b>{on ? token : "—"}</b>{" "}<span>{c * 2}–{c * 2 + 1}</span></button>;
            })}</div></section>;
        })}</div>
        <div className="legend">{[["D+", t("Driver + routed"), "D"], ["S+", t("Live unlock"), "S"], ["D!", t("Driver blocked"), "X"]].map(([token, label, kind]) => <span key={token}><i className={kind}>{token}</i>{label}</span>)}</div>
        {!ready && <p className="notice">{t("CU write actions are locked until a verified root-owned backend is installed.")}</p>}
        {se0 !== se1 && <p className="notice">{t("SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine only add heat.", { se0, se1, effective: Math.min(se0, se1) * 2, idle: Math.abs(se0 - se1) })}</p>}
        <div className="action-dock"><Btn disabled={!changed} onClick={() => setPending(null)}>{t("Reset selection")}</Btn><Btn kind="primary" disabled={!changed || !ready} onClick={() => act({ action: "cu.apply", level: 2, params: { masks }, title: t("Apply live table"), body: `${active} / 40 CU`, warning: t("Stop every game, benchmark, and 3D workload before continuing.") })}>{t("Apply now")}</Btn></div>
      </Card>
      <Fold title={t("Boot persistence")}>
        <p className="note">{t("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, Install service — to make the change survive a reboot.")}</p>
        <div className="row"><Btn wide disabled={!ready} onClick={() => act({ action: "cu.save", level: 1, params: { masks }, title: t("Save selection") })}>{t("Save selection")}</Btn><Btn wide disabled={!ready} onClick={() => run("install_service", t("Install service"))}>{t("Install service")}</Btn></div>
        <Btn kind="danger" disabled={!cu.service_installed} onClick={() => run("remove_service", t("Remove service"), 2)}>{t("Remove service")}</Btn>
      </Fold>
      <Fold title={t("Restore factory")} risk><Btn kind="danger" disabled={!ready} onClick={() => run("factory", t("Restore factory"), 2)}>{t("Restore factory")}</Btn></Fold>
    </div><div className="stack"><Card title={t("Runtime status")}><div className="tiles t3">
      <Tile label={t("GPU frequency")} value={`${num(gpu.frequency_mhz)} MHz`} /><Tile label={t("GPU load")} value={`${num(pick(gpu.usage_percent, gpu.compute_busy_percent))} %`} />
      <Tile label={t("GPU power")} value={`${num(pick(power.value_w, gpu.power_w), 1)} W`} /><Tile label={t("GPU temperature")} value={`${num(gpu.temperature_c, 1)} °C`} />
      <Tile label={t("VRM temperature")} value={`${num(sensors.vrm_mos_temperature_c, 1)} °C`} /><Tile label={t("Service")} value={cu.service_installed ? t("Enabled") : t("Not installed")} /></div>
      <Btn onClick={() => act({ action: "cu.sync", title: t("Unlock / Sync") })}>{t("Unlock / Sync")}</Btn>
      <p className="note">{t("Live routing is temporary until the current table is saved and the boot service is installed. One WGP always represents two CUs; individual CUs cannot be toggled separately.")}</p>
    </Card></div></div>
  </>;
}
