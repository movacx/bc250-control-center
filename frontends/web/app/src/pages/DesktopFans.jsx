import { useState } from "react";
import { num, t, useApp } from "../lib.jsx";
import { Card, ControlTabs } from "../ui.jsx";
import { channelName, dot, ProfileBar, say, ServiceBar } from "./Fans.jsx";

/** PC layout of the channel board: the desktop's table on the left, the editor on the right. */
export default function DesktopFans({ data, board }) {
  const [view, setView] = useState("channels");
  const { live, running } = useApp();
  const { gpu = {}, cpu = {}, sensors = {} } = live?.metrics || {};
  const { rows, row } = board;
  const readings = [["GPU", gpu.temperature_c], ["CPU", cpu.temperature_c], [t("Board"), sensors.board_temperature_c],
    ["VRM", sensors.vrm_temperature_c], ["VRM MOS", sensors.vrm_mos_temperature_c], ["M.2 SSD", sensors.nvme_temperature_c]];
  return <div className="desktop-layout desktop-fans">
    <ControlTabs items={[["channels", t("Channels"), "nav_fans"], ["thermal", t("Thermal detail"), "nav_performance"]]} value={view} onChange={setView} />
    {view === "channels" ? <div className="desktop-fan-columns">
      <Card className="desktop-fan-board">
        <ProfileBar data={data} selected={board.selected} draft={board.draft} dirty={board.dirty} discard={board.discard} locked={running} />
        {data.driver && <p className="note warn">{t(data.driver)}</p>}
        <div className="fan-table-wrap"><table className="fan-table">
          <thead><tr><th>{t("Fan")}</th><th className="r">BIOS</th><th>{t("Mode")}</th><th>{t("Follows")}</th><th className="r">°C</th><th className="r">{t("PWM %")}</th><th className="r">RPM</th><th>{t("State")}</th></tr></thead>
          <tbody>{rows.map((item) => <tr key={item.pwm} className={item.pwm === row?.pwm ? "on" : ""} tabIndex={0} aria-selected={item.pwm === row?.pwm}
            title={`PWM ${item.pwm} · ${item.header}`} onClick={() => board.choose(item.pwm)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); board.choose(item.pwm); } }}>
            <td>{dot(item.tone)}{channelName(item)}</td><td className="r">{item.bios ?? "—"}</td>
            <td>{t(item.mode_label)}{item.role === "pump" && item.mode !== "firmware" ? ` · ${t("Pump")}` : ""}</td>
            <td>{say(item.follows, item.follows_values)}</td><td className="r">{item.temperature != null ? item.temperature.toFixed(1) : "—"}</td>
            <td className="r">{item.duty ?? "—"}</td><td className="r">{item.rpm ?? "—"}</td><td>{say(item.state)}</td></tr>)}</tbody>
        </table></div>
        <p className="note">{[t("{count} channels", { count: data.counts.channels }), t("{count} turning", { count: data.counts.turning }), t("{count} controlled", { count: data.counts.controlled }), data.chip].filter(Boolean).join(" · ")}</p>
        <ServiceBar data={data} locked={running} />
      </Card>
      <Card className="desktop-fan-editor" title={row ? channelName(row) : t("No channel")}>{board.editor(running)}</Card>
    </div> : <Card title={t("Thermal detail")}><div className="desktop-sensor-tiles">
      {readings.map(([name, value]) => <div className="tile" key={name}><small>{name}</small><strong>{num(value, 1)} °C</strong></div>)}
      {rows.filter((item) => item.detected).map((item) => <div className="tile" key={item.pwm}><small>{channelName(item)}</small><strong>{num(item.rpm)} RPM</strong></div>)}
    </div></Card>}
  </div>;
}
