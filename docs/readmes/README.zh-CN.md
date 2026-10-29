# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [日本語](README.ja.md)

<a href="https://ko-fi.com/movacx"><img src="https://img.shields.io/badge/Ko--fi-%E8%B5%9E%E5%8A%A9-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="赞助 · Ko-fi"></a>

一款用于在 Linux 上设置、调校和监控 AMD BC-250 的桌面应用。

它涵盖 GPU 调速器（governor）、CPU 调校、计算单元（CU）、风扇、内存、BIOS 更新、升频（upscaling）以及受支持发行版的系统准备。每一项硬件更改都会先经过范围检查，并在应用前确认。可选的 Decky 插件可将日常控制带入 Steam 的游戏模式。

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center 仪表盘" width="100%"></a>
</p>

更多截图请见[图库](https://movacx.github.io/bc250-control-center/gallery/)。

## 功能

- 仪表盘：显示 CPU、GPU、散热、每核负载、每颗芯片的 GDDR6 温度、已安装的 BIOS 以及供电轨（供电轨需要 I2C 硬件改装；应用内附带带照片的指南）
- CPU、GPU、VRAM、RAM、磁盘和网络的性能图表，附带传感器视图和 CSV 导出
- GPU 调速器管理（Cyan，备选 Oberon）、安全的频率范围和电压实验室
- 通过 SMU 调校 CPU、稳定性测试以及可选的核心解锁
- 计算单元：24 至 40 CU，实时状态与启动状态分开显示
- 风扇控制：手动 PWM、温度曲线、持久化配置，或交由 CoolerControl、fancontrol 或 fan2go 接管
- 内存：VRAM 大小、ZRAM、ZSWAP 和交换分区
- 制作 BIOS 更新 U 盘（P3.00 Chipset Menu、MeiMeiDXE v3、P5.00、P3.00、P2.00），每个文件都经过校验
- 按游戏升频：通过 OptiScaler Client 使用 FSR4 INT8，以及 HelixSR，并支持备份和还原游戏文件
- 按发行版进行系统准备，在内置终端中运行
- 针对 GFX1013、async compute、ACPI 和 Mesa 的兼容性修复；通过 HDMI 输出 Dolby Digital 5.1；通过 HDMI-CEC 控制电视
- 应用内问题报告，附带错误代码、来源代码以及原始错误信息
- 30 种语言，浅色和深色主题，界面缩放以及手柄导航

## 支持的发行版

- Arch Linux、CachyOS、Manjaro
- Fedora、Nobara
- Bazzite 及其他 Fedora Atomic 变体
- SteamOS（测试版）
- Ubuntu、Linux Mint、Debian 13

需要 Python 3.11 或更高版本。其他发行版（包括使用 OpenRC 的系统）会尽量被识别和支持，但并非每个版本都经过测试。

## 安装

### AUR

适用于 Arch Linux、CachyOS 和 SteamOS：

```bash
yay -S bc250-control-center-git
```

### 发布包

从[最新版本](https://github.com/movacx/bc250-control-center/releases/latest)下载适合你发行版的包。

Arch Linux、CachyOS、Manjaro：

```bash
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
```

Fedora、Nobara：

```bash
sudo dnf install ./bc250-control-center-*.rpm
```

Bazzite 和 Fedora Atomic（需要重启）：

```bash
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot
```

Ubuntu、Linux Mint、Debian：

```bash
sudo apt install ./bc250-control-center_*.deb
```

请使用 `apt install` 而不是 `dpkg -i`，以便自动安装依赖。如果 `dpkg -i` 留下了未完成的安装，请运行 `sudo apt --fix-broken install`。

### SteamOS

SteamOS 将系统分区保持为只读，因此只有在关闭该保护后才能安装此包。在桌面模式中打开 Konsole，然后运行：

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
sudo pacman -Syy
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
sudo steamos-readonly enable
```

`pacman-key` 和 `pacman -Syy` 两行会刷新密钥环和软件包数据库，这些内容会在 SteamOS 更新时被重置。如果你还没有为 `deck` 用户设置密码，请先运行 `passwd`。SteamOS 更新后，桌面模式菜单中的 **Reinstall BC250 Control Center** 会替你完成这些步骤。

### 从源代码安装

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center
./run.sh                          # 从代码仓库运行
bash scripts/install-local.sh     # 或为当前用户安装
```

## 更新

应用会检查新版本、显示更新日志、验证软件包校验和，并通过系统的包管理器安装更新。

**SteamOS：** SteamOS 系统更新会删除安装到系统中的软件包，包括本应用。系统更新后，请在桌面模式菜单中运行 **Reinstall BC250 Control Center**，然后再次运行 Prepare BC250 system。SteamOS 会要求输入 `deck` 用户的密码；如果还没有设置，请用 `passwd` 设置。

**从 1.19 升级：** 1.19 的更新程序无法安装软件包。请手动安装一次当前版本；之后的版本会自动更新。

```bash
# Bazzite / Fedora Atomic：替换分层安装的 1.19 软件包
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# 通过 install-local.sh 安装的副本：先删除，再安装软件包
bash scripts/uninstall-local.sh
```

## 快速开始

1. 启动 BC250 Control Center。首次运行的界面会设置语言和外观，并提供安装所需组件的选项。
2. 可选：完成引导教程，了解每个模块会对主板做出哪些更改。
3. 在仪表盘中运行 **Prepare BC250 system**。它会显示你的发行版将安装哪些内容，并在内置终端中执行。
4. 应用更改前请阅读模块的状态行，它会说明哪些已就绪、哪些缺失。

## Decky 插件

BC250 Quick Access 是 Steam 游戏模式快速访问菜单中的可选面板。它提供 GPU、计算单元、CPU、风扇和 VRAM 控制，按游戏设置的 GPU 和风扇配置文件，以及实时的 async compute 读数。高级配置仍保留在桌面应用中。

请从仪表盘的 **Decky** 部分安装。如果缺少 Decky Loader，它也会一并安装；应用中没有其他部分会安装 Decky。详情请参阅[插件 README](../../integrations/decky/bc250-quick-access/README.md)。

## 报告问题

错误窗口会显示诊断代码（例如 `BC250-UPSCALE-001`）、标明出错函数的来源代码（例如 `GPU-0142`），以及带有回溯信息的原始错误。

在错误窗口中使用 **报告此问题**，或在 **设置 › 诊断 › 发送报告** 中操作。报告表单会在应用内打开，并已填好代码、原始错误、系统规格和最近的错误。发送前你可以检查全部内容；主目录路径会被替换为 `~`。如果无法提交表单，它会在浏览器中打开，并保留你已填写的答案。该表单也可[在网页上](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform)使用。

报告还会附带一份硬件诊断，无需 root 即可在所有发行版上收集：内核和头文件、已加载的传感器模块及其内核消息（NCT6687、amdgpu）、hwmon 和 `sensors` 读数、内核日志中的 GPU 和崩溃行、上一次启动的结束方式（正常关机或突然重置）、服务、软件包，以及上一个工作流日志的结尾。当你的用户无法读取内核日志时，桌面会通过 polkit 询问一次密码。过大而无法放入表单的报告会自动裁剪，先删除最次要的部分；**在浏览器中打开** 仍会复制完整文本。

### 黑匣子（冻结与重置）

硬冻结不会在内核日志中留下任何记录。黑匣子每秒记录四次 GPU 频率和负载、温度、GFX 电压、功率、风扇转速、CPU 频率和可用内存，并将每一行立即写入磁盘。因此，下一份报告会显示主板在冻结或重置前的最后几秒。它无需 root，文件大小有限（512 KB，之后轮转）。

```bash
# 桌面模式：游戏时保持终端打开，使用 Ctrl+C 停止
bc250-control-center-cli black-box

# 游戏模式（SteamOS）：切换前在后台启动
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

日志保存在 `~/.local/state/bc250-control-center/black-box/`。`bc250-control-center-cli diagnose` 会输出报告所发送的同一份硬件诊断。

无需终端：在侧边栏打开**黑匣子**（位于 Firmware (BIOS) 上方）即可开始和停止记录，在表格中查看最后写入的几行，并开启*随会话启动*，让它在每次登录时运行（仅限 systemd）。被重启或死机中断的记录会在那里标出。

要在发送前阅读报告附带的全部内容，请打开**设置 › 诊断 › 查看完整诊断**：每个部分（内核、上次启动、黑匣子、传感器、GPU、服务、配置、软件包、日志）都可展开，按标签页分类，可搜索，并可复制或另存为文件。终端中用 `bc250-control-center-cli diagnose --full` 输出相同内容。

也欢迎在 GitHub 上提交 issue。请附上你的发行版、内核版本和终端输出。

## 安全

超频、解锁计算单元、更改风扇控制或刷写 BIOS，都可能导致系统不稳定、数据丢失或损坏主板。每次只更改一项设置，并保留撤销的方法。应用的检查可以发现常见错误，但并不能保证万无一失。

## 致谢

本项目建立在 BC-250 社区的工作之上。下列项目归其作者所有；应用通过经过审查并固定版本的流程与它们集成。每个集成的许可证和范围列在[第三方声明](../THIRD_PARTY_NOTICES.md)中。

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu)：GPU 调速器
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor)：备选调速器
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) 和 [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos)：适用于 GFX1013 的内核和 Mesa/RADV
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250)：适用于 Arch 和 CachyOS 的内核和 Mesa/RADV
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite)：Bazzite 44 上的 async compute，其 RADV 补丁也为 Arch、CachyOS 以及内核 7.2 或更高版本的 Fedora 构建

**升频**
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) 和 [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork)：OptiScaler Client，按游戏使用 FSR4
- [HelixSR](https://github.com/lonewolf0622/HelixSR)：在支持 FSR 3.1 的游戏中使用 DLSS Model E 重建

**CPU 与计算单元**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc)：通过 SMU 进行 CPU 检测与调校
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) 和 [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock)：核心解锁
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix)：通过 ACPI 实现 CPU 性能状态
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager)、[bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) 和 [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock)：计算单元

**传感器、内存与风扇**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry)：VRM 遥测以及 I2C 指南中使用的照片
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature)：GDDR6 温度
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg)：通过 CMOS 设置 VRAM 大小
- [nct6687d](https://github.com/Fred78290/nct6687d)：NCT 传感器和风扇 PWM
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec)：cecd，Valve 的 HDMI-CEC 守护进程

**固件**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios)：原版 P3.00 BIOS 和 Chipset Menu
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script)：UEFI Shell 和 MeiMeiDXE v3
- [BC-250](https://github.com/kenavru/BC-250)：ASRock 更新工具包的镜像（P2.00 和 P5.00）
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo)：自定义启动徽标

**相关项目**（应用未使用；许可证以 GitHub 显示为准）
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) 和 [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms)（GPL-2.0）：以内核模块形式提供的 VRM 和内存温度
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite)（GPL-3.0）：Bazzite 配置套件
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) 和 [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm)：VCN 视频编码研究和一个开源 Windows 驱动（未声明许可证；仅作链接）

## 项目结构

```text
bc250-control-center/
├── src/bc250cc/              核心部分，无图形界面
│   ├── domain/               每个模块的规则和限制（GPU、CPU、CU、风扇、固件…）
│   ├── application/          组合这些规则的用例
│   ├── infrastructure/       系统访问：传感器、服务、软件包、GitHub
│   ├── platform/             不同发行版和启动系统之间的差异
│   └── shared/               所有进程共享的版本、路径和契约
├── frontends/
│   ├── desktop/              Qt 桌面应用
│   │   ├── pages/            每个模块一个文件（仪表盘、GPU、CPU、风扇、固件…）
│   │   ├── components/       可复用的界面组件
│   │   ├── onboarding/       欢迎界面和引导教程
│   │   ├── console/          内置终端
│   │   ├── theme/            主题、样式、颜色和图标
│   │   └── i18n/             30 种语言的翻译
│   └── cli.py                命令行模式
├── integrations/decky/       用于游戏模式的 Decky Quick Access 插件
├── privileged/               以 root 运行的部分，隔离且经过审查
│   ├── helpers/              每个特权任务对应一个辅助程序
│   ├── lib/                  这些辅助程序共享的代码
│   └── policies/             Polkit 权限
├── packaging/                .pkg.tar.zst、.rpm 和 .deb 包，以及 AUR 的 PKGBUILD
├── scripts/                  启动器、本地安装程序和系统工具
├── assets/                   图标、截图和网页图库
├── docs/                     文档、第三方声明以及本 README 的翻译
└── tests/                    超过 5000 个自动化测试，包含 37 个真实发行版的 os-release 文件
```

## 参与贡献

最有用的贡献是错误报告，尤其是附上你的发行版、内核版本以及终端输出。如果你使用的发行版不在上面的列表中，请告诉我们它的使用情况，无论好坏。

许可证为 [MIT](../../LICENSE)。
