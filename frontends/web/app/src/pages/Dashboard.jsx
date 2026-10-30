import { memory, heat, num, pick, t, useApp, usePage } from "../lib.jsx";
import Gddr6 from "../Gddr6.jsx";
import { Btn, Card, Icon, Read } from "../ui.jsx";

const dark = () => document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);

function Mem({ label, used, total }) {
  const u = memory(used), whole = memory(total);
  return <Read label={label} value={u.value} unit={u.unit} note={whole.value !== "--" ? `/ ${whole.value} ${whole.unit}` : undefined} />;
}

export default function Dashboard() {
  const { live, ssh, openSsh } = useApp();
  const data = usePage("dashboard");
  if (!live) return <Card title={t("Dashboard")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const { gpu = {}, cpu = {}, memory: ram = {}, sensors = {}, power = {} } = live.metrics;
  const daemon = data?.daemon || {};
  const rows = data?.cu?.rows || [];
  const cus = rows.length ? rows.reduce((sum, row) => sum + 2 * (Number(row.mask || 0).toString(2).match(/1/g) || []).length, 0) : null;
  const pump = ((data?.fans?.sensores?.fans) || []).find((row) => /pump|j4003|fan2/i.test(row.label || "")) || ((data?.fans?.sensores?.fans) || []).find((row) => row.rpm) || {};
  const duty = Number.isInteger(pump.pwm) ? Math.round(pump.pwm * 100 / 255) : undefined;
  const busy = pick(gpu.usage_percent, gpu.compute_busy_percent);
  const usage = cpu.per_core_percent || [], clocks = cpu.per_core_frequency_mhz || [];
  const rails = [["Vin", sensors.vrm_input_voltage_v, "V", 2], [t("CPU voltage"), sensors.vrm_cpu_voltage_v, "V", 3], [t("GPU voltage"), sensors.vrm_gpu_voltage_v, "V", 3],
    [t("CPU current"), sensors.vrm_cpu_current_a, "A", 1], [t("GPU current"), sensors.vrm_gpu_current_a, "A", 1], [t("Total board power"), sensors.vrm_total_power_w, "W", 1]];
  const shown = (label, value, unit, digits, extra = {}) => value !== undefined && value !== null ? <Read label={label} value={num(value, digits)} unit={unit} {...extra} /> : <Read label={label} value={t("Not detected")} />;
  return (
    <>
      <Card className="board"><div className="row" style={{ gap: 16, flexWrap: "nowrap" }}>
        <img src={dark() ? "board-dark.png" : "board-light.png"} alt="" width="78" height="52" style={{ objectFit: "contain" }} />
        <div className="board-info"><h2 style={{ margin: "0 0 2px", fontSize: 17, fontWeight: 800 }}>AMD BC-250</h2>
          <p className="note" style={{ fontWeight: 600 }}>{[t("{cores} cores / {threads} threads", { cores: cpu.physical_cores ?? "--", threads: cpu.logical_cores ?? "--" }),
            cus != null ? `${cus} / 40 ${t("Compute Units")}` : null, gpu.vram_total ? `${Math.round(gpu.vram_total / 2 ** 20)} MB VRAM` : null].filter(Boolean).join(" · ")}</p></div><button className="connection-button" onClick={openSsh}><i className={`connection-dot ${ssh?.ready ? "connected" : ""}`} />SSH<Icon name="chevron_right_gray" /></button></div></Card>
      <div className="cols dash">
        <section className="card inst">
          <div className="top"><h2>{t("Processor")}</h2><span className="head">{cpu.frequency_mhz ? (cpu.frequency_mhz / 1000).toFixed(2) : "--"}<em>GHz</em></span></div>
          <div className="group">{t("Thermal")}</div>
          {shown(t("Core temperature"), cpu.temperature_c, "°C", 1, { tone: heat(cpu.temperature_c) })}
          {shown("VRM CPU", sensors.vrm_cpu_temperature_c, "°C", 1)}
          <div className="group">{t("Activity")}</div>
          <Read label={t("CPU usage")} value={num(cpu.usage_percent)} unit="%" />
          <Read label={t("Core voltage")} value={cpu.voltage_mv ? num(cpu.voltage_mv / 1000, 3) : "--"} unit="V" />
          <div className="sum"><span>{t("Live core monitor")}</span><b>{t("{cores} cores / {threads} threads", { cores: cpu.physical_cores ?? "--", threads: cpu.logical_cores ?? "--" })}</b></div>
          <div className="cores">{Array.from({ length: 8 }, (_, i) => (
            <div className="core" key={i}><b>N{i + 1}</b>{i < usage.length ? <><span>{clocks[i] ? (clocks[i] / 1000).toFixed(2) : "--"} GHz</span><div className="bar"><i style={{ width: `${usage[i]}%` }} /></div><u>{num(usage[i])} %</u></> : <><span>{t("Hidden")}</span><div className="bar" /><u /></>}</div>))}</div>
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/cpu")}>{t("Configure CPU")}</Btn></div>
        </section>
        <section className="card inst">
          <div className="top"><h2>{t("Graphics")}</h2><span className="head">{num(gpu.frequency_mhz)}<em>MHz</em></span></div>
          <div className="cols" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", columnGap: 24 }}>
            <div><div className="group">{t("Thermal")}</div>
              {shown(t("Temperature"), gpu.temperature_c, "°C", 0, { tone: heat(gpu.temperature_c) })}
              {shown("VRM MOS", sensors.vrm_mos_temperature_c, "°C", 1)}{shown("VRM GPU", sensors.vrm_gpu_temperature_c, "°C", 1)}
              <div className="group">{t("Power")}</div>
              {shown(t("GPU power"), pick(power.value_w, gpu.power_w), "W", 0)}
              {shown(t("GPU voltage"), gpu.voltage_mv != null ? gpu.voltage_mv / 1000 : undefined, "V", 3)}
              <div className="group">{t("Clocks")}</div>
              {shown("MCLK", gpu.memory_frequency_mhz, "MHz", 0)}{shown("SOCCLK", gpu.soc_frequency_mhz, "MHz", 0)}{shown("FCLK", gpu.fabric_frequency_mhz, "MHz", 0)}</div>
            <div><div className="group">{t("Memory")}</div>
              <Mem label="VRAM" used={gpu.vram_used} total={gpu.vram_total} /><Mem label="GTT" used={gpu.gtt_used} total={gpu.gtt_total} /><Mem label={t("System memory")} used={ram.used} total={ram.total} />
              <div className="group">{t("Status")}</div>
              <Read label={t("GPU load")} value={num(busy)} unit="%" />
              <Read label={t("Compute units")} value={cus != null ? `${cus} / 40` : "--"} />
              <Read label={t("Governor")} value={({ "cyan-skillfish-governor-smu": "Cyan Skillfish", "oberon-governor": "Oberon" }[daemon.governor_backend] || daemon.governor_backend || "--")} />
              <Read label={t("Requested range")} value={`${daemon.current_min ?? "--"} – ${daemon.current_max ?? "--"}`} unit="MHz" />
              <Read label={t("PCIe link")} value={gpu.pcie_link || "--"} /><Read label="VBIOS" value={gpu.vbios_version || "--"} /></div></div>
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/gpu")}>{t("Configure Governor")}</Btn><Btn wide onClick={() => (location.hash = "#/cu")}>{t("Configure CUs")}</Btn></div>
        </section>
        <section className="card inst">
          <div className="top"><h2>{t("Cooling")}</h2><span className="head">{num(pump.rpm)}<em>RPM</em></span></div>
          <div className="group">{t("Fan")}</div>
          <Read label={t("PWM duty")} value={duty ?? "--"} unit="%" />
          <Read label={t("PWM mode")} value={pump.pwm_enable === 2 ? "Firmware (BIOS)" : pump.pwm_enable === 1 ? t("Manual") : "--"} />
          <Read label={t("Controller")} value={pump.label || "--"} />
          {shown(t("Board temperature"), sensors.board_temperature_c, "°C", 1)}
          <div className="group">{t("M.2 drive")}</div>
          {shown(t("Temperature"), sensors.nvme_temperature_c, "°C", 1)}{shown(t("Hotspot"), sensors.nvme_hotspot_temperature_c, "°C", 1)}
          <Mem label="Swap" used={ram.swap_used} total={ram.swap_total} />
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/fans")}>{t("Fan Control")}</Btn></div>
        </section>
      </div>
      <Gddr6 />
      <Card title={t("Power")}>
        {rails.every(([, value]) => value == null) ? <p className="note">{t("Not detected")}</p>
          : <div className="tiles">{rails.map(([label, value, unit, digits]) => <div className="tile" key={label}><small>{label}</small><strong>{num(value, digits)} {unit}</strong></div>)}</div>}
      </Card>
    </>
  );
}
