import { useState } from "react";
import { t, useApp } from "../lib.jsx";
import { Btn, Card, Check, Fold, Read } from "../ui.jsx";

export default function CoreUnlock({ unlock, controls = {}, fold = false }) {
  const { act, running } = useApp();
  const [chosenMode, setMode] = useState(null);
  const [force, setForce] = useState(false);
  const mode = chosenMode || (controls.installed ? "persistent" : "temporary");
  const persistent = mode === "persistent";
  const allowed = persistent ? controls.persist_allowed : controls.temporary_allowed;
  const action = persistent ? controls.action : unlock.unlocked ? t("Already unlocked") : t("Unlock cores and restart");
  const Frame = fold ? Fold : Card;
  const warning = t("CPU core unlocking is experimental. Continue with caution and save your work before proceeding, because a restart is required to apply the changes.");

  return <Frame risk title={t("Unlock hidden CPU cores")}>
    <div className="mode-choice core-unlock-modes" role="group" aria-label={t("Unlock hidden CPU cores")}>
      <button type="button" className={!persistent ? "on" : ""} aria-pressed={!persistent} disabled={running} onClick={() => setMode("temporary")}>
        <strong>{t("Temporary")}</strong><span>{t("Until the next full power-off. Nothing is installed.")}</span>
      </button>
      <button type="button" className={persistent ? "on" : ""} aria-pressed={persistent} disabled={running || !controls.offered} onClick={() => setMode("persistent")}>
        <strong>{t("Persistence")}</strong><span>{t("Applied again by itself on every cold boot, without flashing the BIOS.")}</span>
      </button>
    </div>
    {persistent && <Read label={t("Status")} value={controls.status} />}
    {controls.note && <p className="notice">{controls.note}</p>}
    {(persistent || !controls.offered) && controls.hint && <p className="note">{controls.hint}</p>}
    <Check checked={force} onChange={setForce} disabled={running || !allowed}>{t("Force a non-standard core mask (-f)")}</Check>
    <div className="core-unlock-actions">
      <Btn kind="danger" disabled={running || !allowed} onClick={() => act({
        action: persistent ? "cpu.unlock_persist" : "cpu.unlock", level: 2,
        params: { force_mask: force }, title: action, body: persistent ? t(
          "This installs a small boot service that unlocks the two extra cores again early on every cold boot, without flashing the BIOS. Each cold boot then restarts once by itself, about 30 seconds. If the board cannot keep the unlock, the service stops itself after two restarts. To skip it for one boot, add bc250.core_unlock=0 to the kernel command line."
        ) : warning,
      })}>{action}</Btn>
      {persistent && controls.installed && <Btn disabled={running || !controls.remove_allowed} onClick={() => act({
        action: "cpu.unlock_persist_off", level: 2, title: t("Remove persistence"),
        body: t("The boot service is removed. Nothing restarts: the cores stay unlocked until the next full power-off, which brings the board back to 6 cores."),
      })}>{t("Remove persistence")}</Btn>}
    </div>
  </Frame>;
}
