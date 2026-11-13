import { t, useApp } from "../lib.jsx";
import { channelName, footer, modeText, ProfileBar, say } from "./Fans.jsx";

/** PC layout, a copy of the desktop Fans page: the top bar, the channel table, the editor beside it. */
export default function DesktopFans({ data, board }) {
  const { running } = useApp();
  const { rows, row } = board;
  return <section className="card fan-page fan-desktop"><div className="body">
    <ProfileBar data={data} selected={board.selected} draft={board.draft} dirty={board.dirty} locked={running} />
    {data.driver && <p className="note warn">{t(data.driver)}</p>}
    <div className="fan-columns">
      <div className="fan-table-wrap"><table className="fan-table">
        <thead><tr><th>{t("Fan")}</th><th className="r">BIOS</th><th>{t("Mode")}</th><th>{t("Follows")}</th><th className="r">°C</th><th className="r" colSpan={2}>{t("PWM %")}</th><th className="r">RPM</th><th>{t("State")}</th></tr></thead>
        <tbody>{rows.map((item) => <tr key={item.pwm} className={item.pwm === row?.pwm ? "on" : ""} tabIndex={0} aria-selected={item.pwm === row?.pwm}
          title={`PWM ${item.pwm} · ${item.header}`} onClick={() => board.choose(item.pwm)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); board.choose(item.pwm); } }}>
          <td>{channelName(item)}</td><td className="r">{item.bios ?? "—"}</td><td>{modeText(item)}</td>
          <td>{item.mode === "firmware" ? "—" : say(item.follows, item.follows_values)}</td>
          <td className="r">{item.temperature != null ? item.temperature.toFixed(1) : "—"}</td>
          <td className="fan-meter-cell"><span className="fan-meter"><i style={{ width: `${item.duty ?? 0}%` }} /></span></td>
          <td className="r">{item.duty ?? "—"}</td><td className="r">{item.rpm ?? "—"}</td><td>{say(item.state)}</td></tr>)}</tbody>
      </table></div>
      <div className="fan-side">{board.editor(running)}</div>
    </div>
    <p className="fan-footer">{footer(data)}</p>
  </div></section>;
}
