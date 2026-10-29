import { useState } from "react";
import { num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, Tile } from "../ui.jsx";

const WGPS = 5;
const cls = { "D+": "D", "S+": "S", "D!": "X" };
const pop = (mask) => (mask.toString(2).match(/1/g) || []).length;

export default function Compute() {
  const { act, live } = useApp();
  const page = usePage("cu");
  const [pending, setPending] = useState(null);
  const cu = page?.cu;
  if (!cu?.rows?.length) return <Card title={t("Compute Units")}><p className="note">{String(cu?.error || t("Waiting for data…"))}</p>
    <Btn kind="primary" onClick={() => act({ action: "cu.sync", title: t("Unlock / Sync") })}>{t("Unlock / Sync")}</Btn></Card>;
  const live0 = cu.rows.slice(0, 4).map((row) => Number(row.mask ?? 31));
  const masks = pending || live0;
  const active = masks.reduce((sum, m) => sum + 2 * pop(m), 0);
  const changed = masks.reduce((sum, m, i) => sum + pop(m ^ live0[i]), 0);
  const ready = !!cu.privileged_backend_ready;
  const balance = page.balance;
  const gpu = live?.metrics?.gpu || {}, sensors = live?.metrics?.sensors || {}, power = live?.metrics?.power || {};
  const toggle = (r, c) => { const next = [...masks]; next[r] ^= 1 << c; setPending(next); };
  const run = (name, title, level = 1) => act({ action: "cu.action", level, params: { name }, title });
  const legend = [["D+", t("Driver + routed"), "D"], ["S+", t("Live unlock"), "S"], ["D!", t("Driver blocked"), "X"], ["--", t("Not routed"), "off"]];
  const detail = !ready ? t("CU write actions are locked until a verified root-owned backend is installed.")
    : changed ? t("{pairs} differ from the last authorized live table.", { pairs: `${changed} WGP` }) : t("No pending WGP changes.");
  return (
    <>
      <div className="card" style={{ padding: "10px 14px" }}><div className="legend">{legend.map(([token, label, kind]) => <span key={token}><i className={`cu ${kind}`} style={{ display: "inline-block", minHeight: 0, minWidth: 28, padding: "4px 8px", flexDirection: "row" }}>{token}</i>{label}</span>)}</div></div>
      <Card className="scroll-x">
        <div className="cu" role="grid">
          <div className="h"><b>{t("Shader row")}</b><small>SE / SH</small></div>
          {Array.from({ length: WGPS }, (_, c) => <div className="h" key={c}><b>WGP{c}</b><small>CU {2 * c}–{2 * c + 1}</small></div>)}
          <div className="h"><b>CUs</b><small>{t("active / 10")}</small></div>
          {masks.map((mask, r) => {
            const row = cu.rows[r] || {}, tokens = row.tokens || [];
            return [<div key={`n${r}`} style={{ minHeight: 72 }}><b>{row.name || `SE${r >> 1}.SH${r & 1}`}</b></div>,
              ...Array.from({ length: WGPS }, (_, c) => {
                const on = !!(mask & (1 << c)), was = !!(live0[r] & (1 << c));
                const token = on && was && tokens[c] ? tokens[c] : on ? "S+" : "--";
                return <button type="button" key={`${r}${c}`} className={on !== was ? "chg" : on ? cls[token] || "D" : "off"} aria-pressed={on}
                  aria-label={`WGP${c} ${row.name}`} onClick={() => toggle(r, c)} disabled={!ready && !pending && false}><b>{on ? token : "--"}</b><b>{on ? t("ROUTED") : t("Not routed")}</b></button>;
              }),
              <div key={`s${r}`} className="sum" style={{ margin: 0, fontSize: 12 }}><b style={{ color: "inherit" }}>{2 * pop(mask)} / 10</b></div>];
          })}
        </div>
      </Card>
      <div className="cols two">
        <div className="stack">
          <Card title={t("Target: {count} / 40 CUs", { count: active })} sub={detail}>
            <p className="note" style={balance && !balance.balanced ? { color: "var(--c-orange)" } : undefined}>{balance && (balance.balanced
              ? t("SE0 {se0} · SE1 {se1} CUs — balanced: every active CU adds performance.", { se0: balance.se0, se1: balance.se1 })
              : t("SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine only add heat.", { se0: balance.se0, se1: balance.se1, effective: balance.effective, idle: balance.idle }))}</p>
            <div className="row">
              <Btn wide onClick={() => act({ action: "cu.sync", title: t("Unlock / Sync") })}>{t("Unlock / Sync")}</Btn>
              <Btn wide disabled={!changed} onClick={() => setPending(null)}>{t("Reset selection")}</Btn>
              <Btn kind="primary" wide disabled={!changed || !ready} onClick={() => act({ action: "cu.apply", level: 2, params: { masks }, title: t("Apply live table"), body: `${active} / 40`, warning: t("Stop every game, benchmark, and 3D workload before continuing.") })}>{t("Apply now")}</Btn></div>
          </Card>
          <Card title={t("Boot persistence")} sub={t("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, Install service — to make the change survive a reboot.")}>
            <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))" }}>
              <Btn disabled={!ready} onClick={() => act({ action: "cu.save", level: 1, params: { masks }, title: t("Save selection") })}>{t("Save selection")}</Btn>
              <Btn disabled={!ready} onClick={() => run("install_service", t("Install service"))}>{t("Install service")}</Btn>
              <Btn kind="danger" disabled={!cu.service_installed} onClick={() => run("remove_service", t("Remove service"), 2)}>{t("Remove service")}</Btn>
              <Btn disabled={!ready} onClick={() => run("factory", t("Restore factory"), 2)}>{t("Restore factory")}</Btn></div>
            <p className="note">{t("Live routing is temporary until the current table is saved and the boot service is installed. One WGP always represents two CUs; individual CUs cannot be toggled separately.")}</p>
          </Card>
        </div>
        <Card><div className="tiles" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))" }}>
          <Tile label={t("Service")} value={cu.service_installed ? t("Enabled") : t("Not installed")} note="bc250-cu-live-manager.service" />
          <Tile label={t("Boot persistence")} value={String(cu.mode || "--")} />
          <Tile label={t("GPU frequency")} value={`${num(gpu.frequency_mhz)} MHz`} /><Tile label={t("GPU load")} value={`${num(pick(gpu.usage_percent, gpu.compute_busy_percent))} %`} />
          <Tile label={t("GPU power")} value={`${num(pick(power.value_w, gpu.power_w), 1)} W`} /><Tile label={t("GPU temperature")} value={`${num(gpu.temperature_c, 1)} °C`} />
          <Tile label={t("VRM temperature")} value={`${num(sensors.vrm_mos_temperature_c, 1)} °C`} /></div></Card>
      </div>
    </>
  );
}
