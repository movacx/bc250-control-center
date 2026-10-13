# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [日本語](README.ja.md)

适用于 Linux 的 AMD BC-250 控制中心。将监控、GPU 控制、CPU 调校、计算单元、风扇和 BIOS 更新整合到一个桌面应用中，并在每次硬件改动前提供明确的限制和校验。

## 截图

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center 仪表板" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[查看全部截图 →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## 安装

### Arch、CachyOS 和 SteamOS（AUR）

```bash
yay -S bc250-control-center-git
```

### 发布包

从[最新版本](https://github.com/movacx/bc250-control-center/releases/latest)下载适合你系统的包：

| 系统 | 文件 |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<版本>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<版本>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<版本>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: 同一个 RPM，然后重启进入新的部署
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

在 Debian 和 Ubuntu 上请使用 `apt install` 而不是 `dpkg -i`，这样 APT 也会下载依赖。如果 `dpkg -i` 让包处于半安装状态，可以用 `sudo apt --fix-broken install` 修复。

### 更新

无需再回到本页。新版本发布时，仪表板会提示你、显示更新内容，并在校验 SHA-256 后用系统的包管理器安装。

在 SteamOS 上，更新会先关闭只读保护，安装后再重新开启。SteamOS 系统更新会删除安装到系统中的所有内容，包括本应用：请在桌面模式菜单中打开 **Reinstall BC250 Control Center**，然后重新准备依赖项。SteamOS 会要求输入 `deck` 的密码；如果从未设置过，请先在 Konsole 中运行 `passwd`。

**从 1.19 升级？** 1.19 内置的更新程序无法安装软件包。请用[最新版本](https://github.com/movacx/bc250-control-center/releases/latest)的软件包手动更新一次，之后应用会自行更新。在 Bazzite 上一步替换 1.19 并重启；如果使用 install-local.sh 安装，请先移除那份副本：

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## 首次启动

1. 打开 **BC250 Control Center**。
2. 欢迎界面会询问语言、外观和侧边栏样式，并提供安装主板所需的工具。之后都可以在**设置**中修改。
3. 如果愿意，可以跟随引导教程：它会逐个介绍模块，并说明每个模块会改动主板的什么。

应用任何改动前，先查看模块状态：它会说明哪些已就绪、缺少什么以及原因。

## 功能

**仪表板与监控**
- 仪表板显示处理器、图形与散热、实时核心、每颗 GDDR6 芯片的温度、供电轨（需 I2C 改装）以及已安装的 BIOS。
- 性能模块提供 CPU、GPU、显存、内存、磁盘和网络图表，以及带最小值、平均值和最大值的传感器视图。

**硬件**
- **GPU：** Cyan 和 Oberon 的安全调速器范围、电压实验室以及 2000 MHz 以上的频点。
- **CPU / SMU：** 临时与持久调校、稳定性测试以及实验性的隐藏核心解锁。
- **计算单元：** 24 至 40 个 CU，实时状态和启动状态分开显示。
- **风扇：** 手动 PWM 控制、温度曲线、重启后保留的配置，以及导出到文件或 Decky。
- **内存：** 显存大小、ZRAM、ZSWAP 和交换文件。
- **固件（BIOS）：** 制作包含 P3.00 Chipset Menu、MeiMeiDXE v3、P5.00、P3.00 或 P2.00 的更新 U 盘，每个文件都经过校验。

**系统**
- 按发行版适配的依赖准备，内置终端显示每条命令。
- 兼容性修复：GFX1013 与异步计算、按游戏的 FSR4、遥测和 ACPI。
- 为功放和条形音箱提供 HDMI 杜比数字 5.1，并通过 Valve 的 cecd 用 HDMI-CEC 控制电视。
- 从发行版官方仓库安装 Wi-Fi、蓝牙和打印机驱动。
- 诊断、历史记录以及导出 CSV 指标。

**界面**
- 浅色、深色和夜蓝主题，标准与正式风格，10 种强调色，缩放 70 % 至 150 %。
- 30 种语言和手柄导航。

## Decky Quick Access（可选）

用于 SteamOS 快速访问菜单和 Steam 游戏模式的面板。无需离开游戏即可使用日常控制（GPU、CU、CPU、风扇和显存）；高级设置仍在桌面应用中。

- **按游戏配置：** 为每个游戏指定 GPU 和风扇配置。游戏启动时应用，关闭后一切恢复原状。
- **实时异步计算：** 显示游戏是否使用异步计算以及使用程度。
- **风扇预设：** 使用你从桌面导出的名称和转速。

安装方法：打开**仪表板**，滚动到 **Decky** 部分并选择提供的操作。如果缺少 Decky Loader，应用会安装它；如果已存在，则只安装或修复 BC250 Quick Access。常规依赖准备永远不会自动安装 Decky。

更多内容见 [Decky README](../../integrations/decky/bc250-quick-access/README.md)。

## 安全

超频、修改计算单元、风扇控制和 BIOS 更新可能导致系统卡死或关机、数据丢失或硬件损坏。一次只应用一项改动，始终保留恢复手段，也不要把应用的检查当作硬件保证。

## 外部工具与致谢

BC250 Control Center 建立在社区的工作之上，不声称拥有这些项目。每个工具都只通过明确且经过审查的流程使用。

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): GPU 调速器。
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): 受支持的替代调速器。
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) 和 [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): GFX1013 的内核与 Mesa/RADV。
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): 为 Arch/CachyOS 配套的内核与 Mesa/RADV。
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): Bazzite 44 上的异步计算。
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) 和 [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): 按游戏的 FSR4。
- [HelixSR](https://github.com/lonewolf0622/HelixSR): 为 FSR 3.1 游戏提供 DLSS Model E 重建，按游戏启用。

**CPU 与计算单元**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): 通过 SMU 检测和调校 CPU。
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) 和 [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): 核心解锁。
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) 和 [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): 计算单元。
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): 通过 ACPI 提供 CPU 性能状态。

**传感器、内存与风扇**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): 电压调节器（VRM）遥测。
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): GDDR6 显存温度。
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): 通过 CMOS 设置显存大小。
- [nct6687d](https://github.com/Fred78290/nct6687d): NCT 传感器与风扇 PWM。
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): Valve 的 HDMI-CEC 守护进程 cecd。

**固件**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): 原版 P3.00 和 Chipset Menu BIOS。
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell 和 MeiMeiDXE v3。
- [BC-250](https://github.com/kenavru/BC-250): ASRock 更新套件镜像（P2.00 和 P5.00）。
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): 自定义开机徽标。

许可证、审查状态和每项集成的确切范围见[第三方声明](../THIRD_PARTY_NOTICES.md)。

## 项目结构

```text
bc250-control-center/
├── src/bc250cc/          核心，不含图形界面
│   ├── domain/           各模块的规则与限制（GPU、CPU、CU、风扇、固件……）
│   ├── application/      组合这些规则的用例
│   ├── infrastructure/   系统访问：传感器、服务、软件包、GitHub
│   ├── platform/         发行版与 init 系统之间的差异
│   └── shared/           所有进程共享的版本、路径和约定
├── frontends/
│   ├── desktop/          Qt 桌面应用
│   │   ├── pages/        每个模块一个文件（仪表板、GPU、CPU、风扇、固件……）
│   │   ├── components/   可复用的界面组件
│   │   ├── onboarding/   欢迎界面与引导教程
│   │   ├── console/      内置终端
│   │   ├── theme/        主题、风格、颜色和图标
│   │   └── i18n/         30 种语言的翻译
│   └── cli.py            命令行模式
├── integrations/decky/   游戏模式用的 Decky Quick Access 插件
├── privileged/           以 root 运行的部分，隔离且经过审查
│   ├── helpers/          每项特权任务一个辅助程序
│   ├── lib/              这些辅助程序共享的代码
│   └── policies/         Polkit 权限
├── packaging/            .pkg.tar.zst、.rpm 和 .deb 包，以及 AUR 的 PKGBUILD
├── scripts/              启动器、本地安装程序和系统工具
├── assets/               图标、截图和网页图库
├── docs/                 文档、第三方声明和本 README 的翻译
└── tests/                4000 多项自动化测试
```

采用 [MIT 许可证](../../LICENSE)。
