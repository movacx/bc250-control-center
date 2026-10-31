import { useEffect, useState } from "react";
import { keep, num, pick, t, useApp, usePage } from "../lib.jsx";
import { Btn, Card, ControlTabs, Fold, Read } from "../ui.jsx";

const cls = { "D+": "D", "S+": "S", "D!": "X" };
const pop = (mask) => (mask.toString(2).match(/1/g) || []).length;

export default function Compute() {
  const { act, live, running, session } = useApp();
  const page = usePage("cu");
  const [pending, setPending] = useState(null), [tab, setTab] = useState("routing");
  const cu = page?.cu;
  const current = cu?.rows?.slice(0, 4).map((row) => Number(row.mask ?? 0)) || [];
  const signature = current.join(",");
  useEffect(() => { if (pending?.join(",") === signature) setPending(null); }, [signature, pending]);
  const canControl = !!session?.control && !running;
  const sync = () => act({ action: "cu.sync", title: t("Unlock / Sync") });
  if (current.length !== 4 || !cu?.available || cu?.parse_error) return <Card title={t("Compute Units")}><p className="note">{String(cu?.error || cu?.parse_error || t("Authorize a live refresh before applying WGP changes."))}</p>
    <Btn kind="primary" disabled={!canControl} onClick={sync}>{t("Unlock / Sync")}</Btn></Card>;
  const masks = pending || current;
  const total = (values) => values.reduce((sum, mask) => sum + 2 * pop(mask), 0);
  const active = total(masks), applied = total(current);
  const changed = masks.reduce((sum, mask, i) => sum + pop(mask ^ current[i]), 0);
  const ready = !!cu.privileged_backend_ready, editable = ready && canControl;
  const se0 = 2 * (pop(masks[0]) + pop(masks[1])), se1 = 2 * (pop(masks[2]) + pop(masks[3]));
  const gpu = live?.metrics?.gpu || {};
  const bootSync = { pending: t("Pending changes"), saved: t("Current table saved"), not_saved: t("No saved table"), unknown: t("Unknown") }[cu.boot_sync_key] || (cu.boot_sync ? t(cu.boot_sync) : "—");
  const toggle = (r, c) => { const next = [...masks]; next[r] ^= 1 << c; setPending(next); };
  const run = (name, title, level = 1) => act({ action: "cu.action", level, params: { name }, title });
  return <div className="control-workspace cu-workspace">
    <ControlTabs items={[["routing", t("Live routing"), "nav_compute"], ["monitor", t("Monitoring"), "nav_performance"], ["boot", t("Boot persistence"), "nav_settings"]]} value={tab} onChange={setTab} />
    {tab === "routing" && <Card className="cu-routing">
      {changed > 0 && <div className="cu-selection-state" role="status"><span className="cu-pending">{t("Selection")} <b>{active} / 40 CU</b></span></div>}
      <div className="cu-engines">{[0, 1].map((engine) => <section className="cu-engine" key={engine} aria-label={`SE${engine}`}>
        <header className="cu-engine-heading"><h2>SE{engine}</h2><span>{engine === 0 ? se0 : se1} / 20 CU</span></header>
        <div className="wgp-rows">{[0, 1].map((shader) => {
          const r = engine * 2 + shader, mask = masks[r], row = cu.rows[r], tokens = row.tokens || [];
          return <section className="wgp-row" key={r} aria-label={row.name || `SE${engine}.SH${shader}`}><header><b id={`wgp-row-${r}`}>SH{shader}</b><span>{2 * pop(mask)} / 10 CU</span></header>
            <div className="wgp-cells">{Array.from({ length: 5 }, (_, c) => {
              const on = !!(mask & (1 << c)), was = !!(current[r] & (1 << c)), edited = on !== was;
              const token = edited ? (on ? "+" : "−") : tokens[c] || (on ? "S+" : "—");
              return <button type="button" key={c} className={edited ? "chg" : cls[token] || (on ? "D" : "off")} aria-pressed={on}
                aria-label={`SE${engine}.SH${shader} · WGP ${c} · CU ${c * 2}–${c * 2 + 1} · ${token}`} onClick={() => toggle(r, c)} disabled={!editable}><small>WGP {c}</small><b>{token}</b><span>{c * 2}–{c * 2 + 1}</span></button>;
            })}</div></section>;
        })}</div>
      </section>)}</div>
      {se0 !== se1 && <p className="notice">{t("SE0 {se0} · SE1 {se1} CUs — unbalanced: performs like {effective} CUs; {idle} CUs on the stronger engine only add heat.", { se0, se1, effective: Math.min(se0, se1) * 2, idle: Math.abs(se0 - se1) })}</p>}
      {!ready && <p className="notice">{t("CU write actions are locked until a verified root-owned backend is installed.")}</p>}
      <div className="cu-apply"><p className={changed ? "cu-pending" : "note"} role="status">{changed ? `${t("Changed WGP pairs")}: ${changed}` : t("No pending WGP changes.")}</p>
        <div className="action-dock"><Btn disabled={!changed || running} onClick={() => setPending(null)}>{t("Reset selection")}</Btn><Btn kind="primary" disabled={!changed || !editable} onClick={() => act({ action: "cu.apply", level: 2, inline: true, params: { masks: [...masks] }, title: t("Apply live table"), summary: [[t("Applied tuning"), `${applied} / 40 CU`], [t("Selection"), `${active} / 40 CU`], ["SE0 / SE1", `${se0} / ${se1} CU`]], warning: t("Stop every game, benchmark, and 3D workload before continuing.") })}>{t("Review and apply")}</Btn></div>
        <Btn wide disabled={!canControl} onClick={sync}>{t("Unlock / Sync")}</Btn>
      </div>
      <details className="control-explanation cu-details"><summary>{t("Details")}</summary>
        <section className="cu-registers" aria-label={t("Register diagnostics")}><h3>{t("Register diagnostics")}</h3><p className="note">{t("Read-only register values and the pending SPI target.")}</p>
          <table><thead><tr>{[keep("Shader row"), "Live SPI", "Target SPI", "Driver map", "CC harvest"].map((label) => <th scope="col" key={label}>{t(label)}</th>)}</tr></thead><tbody>{cu.rows.slice(0, 4).map((row, r) => {
            const hex = (value) => Number.isInteger(value) && value >= 0 && value <= 31 ? `0x${value.toString(16).padStart(2, "0")}` : "—";
            const spi = typeof row.spi === "string" && /^0x[0-9a-f]+$/i.test(row.spi) ? row.spi : "—";
            return <tr key={r}><th scope="row">{row.name || `SE${r >> 1}.SH${r & 1}`}</th><td data-label={t("Live SPI")}>{spi}</td><td data-label={t("Target SPI")} className={masks[r] !== current[r] ? "cu-pending" : ""}>{hex(masks[r])}</td><td data-label={t("Driver map")}>{hex(row.driver_mask ?? cu.driver_masks?.[r])}</td><td data-label={t("CC harvest")}>{row.cc || "—"}</td></tr>;
          })}</tbody></table>
        </section><p className="note">{t("2 CUs per WGP")}</p><div className="legend">{[["D+", t("Driver + routed"), "D"], ["S+", t("Live unlock"), "S"], ["D!", t("Driver blocked"), "X"]].map(([token, label, kind]) => <span key={token}><i className={kind}>{token}</i>{label}</span>)}</div></details>
    </Card>}
    {tab === "monitor" && <><Card title={t("Details")} className="cu-runtime-details">
      <Read label={t("Compute Units")} value={`${applied} / 40`} unit="CU" /><Read label="SE0 / SE1" value={`${2 * (pop(current[0]) + pop(current[1]))} / ${2 * (pop(current[2]) + pop(current[3]))}`} unit="CU" />

      <Read label="UMR" value={cu.umr || "—"} /><Read label="UMR inst" value={cu.umr_instance || "—"} /><Read label="ASIC" value={cu.asic || "—"} />
      <Read label="amdgpu · bc250_cc_write_mode" value={cu.amdgpu_mode || "—"} /><Read label="amdgpu · active_cu_number" value={cu.amdgpu_active_cus || "—"} />
      <Read label="CPU" value={cu.cpu_summary || "—"} /><Read label={t("Service")} value={cu.service_enabled ? t("Enabled") : cu.service_installed ? t("Disabled") : t("Not installed")} /><Read label={t("Boot sync")} value={bootSync} />
      <Read label={t("Source")} value={cu.register_source || "—"} /><Read label={t("Source cache")} value={cu.source || "—"} /><Read label={t("Updated")} value={cu.updated_at || "—"} />
      {cu.legend && <p className="note cu-report-legend">{cu.legend}</p>}
    </Card><Card title={t("Runtime status")}>
      <Read label={t("GPU frequency")} value={num(gpu.frequency_mhz)} unit="MHz" /><Read label={t("GPU load")} value={num(pick(gpu.usage_percent, gpu.compute_busy_percent))} unit="%" />
      <Read label={t("GPU temperature")} value={num(gpu.temperature_c, 1)} unit="°C" />
    </Card></>}
    {tab === "boot" && <>
      <Card title={t("Boot persistence")} pill={cu.service_installed ? t("Enabled") : t("Not installed")} tone={cu.service_installed ? "green" : ""}>
        <p className="note">{t("Select the WGP pairs above, then use the buttons below in order — Apply now, Save selection, Install service — to make the change survive a reboot.")}</p>
        <Read label={t("Applied tuning")} value={`${applied} / 40`} unit="CU" />
        {changed > 0 && <p className="notice">{t("Selection has pending changes")}</p>}
        <div className="cu-boot-actions"><Btn kind="primary" disabled={!editable || !!changed} onClick={() => act({ action: "cu.save", level: 1, params: { masks: [...current] }, title: t("Save selection") })}>{t("Save selection")}</Btn><Btn disabled={!editable || !!changed} onClick={() => run("install_service", t("Install service"))}>{t("Install service")}</Btn></div>
        <Btn wide disabled={!cu.service_installed || !canControl} onClick={() => run("remove_service", t("Remove service"))}>{t("Remove service")}</Btn>
      </Card>
      <Fold title={t("Restore factory")} risk><Btn kind="danger" disabled={!editable} onClick={() => run("factory", t("Restore factory"), 2)}>{t("Restore factory")}</Btn></Fold>
    </>}
  </div>;
}
