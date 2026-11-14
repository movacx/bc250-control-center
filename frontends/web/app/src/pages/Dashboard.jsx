import { useMobile } from "../ui.jsx";
import { keep, memory, heat, num, pick, t, useApp, usePage } from "../lib.jsx";
import Gddr6 from "../Gddr6.jsx";
import { Btn, Card, CpuCores, Read } from "../ui.jsx";

const dark = () => document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);

function Mem({ label, used, total }) {
  const u = memory(used), whole = memory(total);
  return <Read label={label} value={u.value} unit={u.unit} note={whole.value !== "--" ? `/ ${whole.value} ${whole.unit}` : undefined} />;
}

// Disks without a name of their own; a volume label stays as the user wrote it.
const DISK_KIND_LABELS = { system: keep("System"), home: keep("Home") };
const diskName = (volume) => DISK_KIND_LABELS[volume.kind] ? t(DISK_KIND_LABELS[volume.kind]) : (volume.label || volume.mountpoint || "--");

// The desktop's FAN_OWNER_LABELS: who sets the Cooling card's fan.
const OWNER_LABELS = { system: keep("System service"), daemon: keep("Desktop daemon"), firmware: keep("Firmware (BIOS)"), manual: keep("Manual value"), external: keep("Another program") };
const countCUs = rows => rows.length ? rows.reduce((sum, row) => sum + 2 * (Number(row.mask || 0).toString(2).match(/1/g) || []).length, 0) : null;

export function DashboardHeaderSummary() {
  const { live } = useApp();
  const data = usePage("dashboard");
  const gpu = live?.metrics?.gpu || {};
  const cus = countCUs(data?.cu?.rows || []);
  const vram = Number.isFinite(gpu.vram_total) ? Math.round(gpu.vram_total / 2 ** 20) : "—";
  return <small className="dashboard-header-summary">{cus ?? "—"} / 40 CU · {vram} MB VRAM</small>;
}

export default function Dashboard() {
  const mobile = useMobile();
  const { live } = useApp();
  const data = usePage("dashboard");
  if (!live) return <Card title={t("Dashboard")}><p className="note">{t("Waiting for data…")}</p></Card>;
  const { gpu = {}, cpu = {}, memory: ram = {}, sensors = {}, power = {} } = live.metrics;
  const daemon = data?.daemon || {};
  const disk = live.metrics.disk || {}, performance = data?.performance || {};
  // Every real disk after the M.2 one; a drive unplugged drops out on the next sample.
  const extraDisks = (disk.volumes || performance.discos || []).slice(1).filter((volume) => volume && volume.mountpoint);
  const persistent = data?.cpu_persistence || {}, registered = persistent.config || {};
  const recorded = persistent.applied_this_boot && registered.valid ? registered : {};

  const rows = data?.cu?.rows || [];
  const cus = countCUs(rows);
  const engineCounts = [rows.slice(0,2), rows.slice(2,4)].map(engine => engine.reduce((sum,row) => sum + 2 * (Number(row.mask || 0).toString(2).match(/1/g) || []).length,0));
  const effective = Math.min(...engineCounts) * 2;
  // The fan the service follows or that turns (bc250cc.application.fan.board_view.dashboard_fan).
  const pump = data?.cooling_fan || {};
  const duty = Number.isInteger(pump.pwm) ? Math.round(pump.pwm * 100 / 255) : undefined;
  const busy = pick(gpu.usage_percent, gpu.compute_busy_percent);
  const rails = [["Vin", sensors.vrm_input_voltage_v, "V", 2], [t("CPU voltage"), sensors.vrm_cpu_voltage_v, "V", 3], [t("GPU voltage"), sensors.vrm_gpu_voltage_v, "V", 3],
    [t("CPU current"), sensors.vrm_cpu_current_a, "A", 1], [t("GPU current"), sensors.vrm_gpu_current_a, "A", 1], [t("Total board power"), sensors.vrm_total_power_w, "W", 1]];
  const shown = (label, value, unit, digits, extra = {}) => value !== undefined && value !== null ? <Read label={label} value={num(value, digits)} unit={unit} {...extra} /> : <Read label={label} value={t("Not detected")} />;
  return (
    <>
      {!mobile && <Card className="board desktop-board"><div className="row" style={{ gap: 16, flexWrap: "nowrap" }}>
        <img src={dark() ? "board-dark.png" : "board-light.png"} alt="" width="78" height="52" style={{ objectFit: "contain" }} />
        <div className="board-info"><h2 style={{ margin: "0 0 2px", fontSize: 17, fontWeight: 800 }}>AMD BC-250</h2>
          <p className="note" style={{ fontWeight: 600 }}>{[t("{cores} cores / {threads} threads", { cores: cpu.physical_cores ?? "--", threads: cpu.logical_cores ?? "--" }),
            cus != null ? `${cus} / 40 ${t("Compute Units")}` : null, gpu.vram_total ? `${Math.round(gpu.vram_total / 2 ** 20)} MB VRAM` : null].filter(Boolean).join(" · ")}</p></div></div></Card>}
      <div className={mobile ? "cols dash mobile-dashboard" : "cols dash desktop-dashboard"}>
        <section className="card inst">
          <div className="top"><h2>{t("Processor")}</h2><span className="head">{cpu.frequency_mhz ? (cpu.frequency_mhz / 1000).toFixed(2) : "--"}<em>GHz</em></span></div>
          <div className="group">{t("Thermal")}</div>
          {shown(t("Core temperature"), cpu.temperature_c, "°C", 1, { tone: heat(cpu.temperature_c) })}
          {shown("VRM CPU", sensors.vrm_cpu_temperature_c, "°C", 1)}
          <div className="group">{t("Activity")}</div>
          <Read label={t("CPU usage")} value={num(cpu.usage_percent)} unit="%" />
          <Read label={t("Core voltage")} value={cpu.voltage_mv ? num(cpu.voltage_mv / 1000, 3) : performance.cpu_voltage != null ? num(Number(performance.cpu_voltage) / 1000,3) : "--"} unit="V" />
          <Read label={t("Registered OC")} value={recorded.frequency ?? t("Not detected")} unit={recorded.frequency ? "MHz" : undefined} note={recorded.scale != null ? `${t("Scale")} ${recorded.scale}` : undefined} />
          <div className="sum"><span>{t("Live core monitor")}</span><b>{t("{cores} cores / {threads} threads", { cores: cpu.physical_cores ?? "--", threads: cpu.logical_cores ?? "--" })}</b></div>
          <CpuCores cpu={cpu} />
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/cpu")}>{t("Configure CPU")}</Btn></div>
        </section>
        <section className="card inst">
          <div className="top"><h2>{t("Graphics")}</h2><span className="head">{num(gpu.frequency_mhz)}<em>MHz</em></span></div>
          <div className={mobile ? "cols" : "cols desktop-graphics-columns"} style={mobile ? { gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", columnGap: 24 } : undefined}>
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
              <Read label={t("Compute units")} value={cus != null ? `${cus} / 40` : "--"} note={cus != null && effective !== cus ? `${t("Custom")} · ${effective} ${t("Effective CUs")}` : undefined} />
              <Read label={t("Governor")} value={({ "cyan-skillfish-governor-smu": "Cyan Skillfish", "oberon-governor": "Oberon" }[daemon.governor_backend] || daemon.governor_backend || "--")} />
              <Read label={t("Requested range")} value={`${daemon.current_min ?? "--"} – ${daemon.current_max ?? "--"}`} unit="MHz" note={daemon.current_max != null ? `${t("Accepted")} ${daemon.current_max} MHz` : undefined} />
              <Read label={t("PCIe link")} value={gpu.pcie_link || "--"} /><Read label="VBIOS" value={gpu.vbios_version || "--"} /></div></div>
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/gpu")}>{t("Configure Governor")}</Btn><Btn wide onClick={() => (location.hash = "#/cu")}>{t("Configure CUs")}</Btn></div>
        </section>
        <section className="card inst">
          <div className="top"><h2>{t("Cooling")}</h2><span className="head">{num(pump.rpm)}<em>RPM</em></span></div>
          <div className="group">{t("Fan")}</div>
          <Read label={t("PWM duty")} value={duty ?? "--"} unit="%" />
          <Read label={t("PWM mode")} value={pump.owner ? t(OWNER_LABELS[pump.owner] || "Not detected") : "--"} />
          <Read label={t("Controller")} value={pump.name || "--"} />
          {shown(t("Board temperature"), sensors.board_temperature_c, "°C", 1)}
          <div className="group">{t("M.2 drive")}</div>
          {shown(t("Temperature"), sensors.nvme_temperature_c, "°C", 1)}{shown(t("Hotspot"), sensors.nvme_hotspot_temperature_c, "°C", 1)}
          <Mem label={t("Used")} used={pick(disk.used, performance.disco_usado)} total={pick(disk.total, performance.disco_total)} />
          <Mem label="Swap" used={ram.swap_used} total={ram.swap_total} />
          {extraDisks.length > 0 && <><div className="group">{t("Storage")}</div>
            {extraDisks.map((volume) => <Mem key={volume.mountpoint} label={diskName(volume)} used={volume.used} total={volume.total} />)}</>}
          <div className="group">BIOS</div><Read label={t("Version")} value={data?.bios || performance.bios_version || t("Not detected")} note={performance.bios_variant} />
          <div className="row" style={{ marginTop: 12 }}><Btn kind="soft" wide onClick={() => (location.hash = "#/fans")}>{t("Fan Control")}</Btn>{!mobile && <Btn wide onClick={() => (location.hash = "#/fans")}>{t("Automatic curve")}</Btn>}</div>
        </section>
      </div>
      <Gddr6 />
      {mobile ? <Card title={t("Power")}>
        {rails.every(([, value]) => value == null) ? <p className="note">{t("Not detected")}</p>
          : <div className="tiles">{rails.map(([label, value, unit, digits]) => <div className="tile" key={label}><small>{label}</small><strong>{num(value, digits)} {unit}</strong></div>)}</div>}
      </Card> : <section className="card desktop-power"><span>{t("Power")}</span>
        {rails.every(([, value]) => value == null) ? <p className="note">{t("Not detected")}</p>
          : <div className="tiles">{rails.map(([label, value, unit, digits]) => <div className="tile" key={label}><small>{label}</small><strong>{num(value, digits)} {unit}</strong></div>)}</div>}
      </section>}
    </>
  );
}
