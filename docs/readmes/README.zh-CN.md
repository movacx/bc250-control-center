# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [日本語](README.ja.md)

适用于 AMD BC-250 的 Linux 控制中心：在一个桌面应用中提供监控、GPU 控制、CPU 调校、计算单元和风扇控制。

## 截图

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center 仪表板" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## 安装

```bash
# 从源代码安装
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch、CachyOS 和 Manjaro
yay -S bc250-control-center-git
```

如需删除本地安装，请在同一目录中运行 `./uninstall-local.sh`。

软件包位于[最新版本](https://github.com/movacx/bc250-control-center/releases)。Fedora、Nobara 和 Bazzite 使用相同的 `noarch` RPM：

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # rpm-ostree 后重启
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## 首次启动

1. 打开 `bc250-control-center`。
2. 在 Dashboard 中选择 **Prepare dependencies**。
3. 应用更改前先检查模块状态。

## 功能

- 实时显示 CPU、GPU、内存、存储、网络、温度和风扇数据。
- GPU governor、CPU 调校与实验性核心解锁。
- 24–40 个 Compute Units、PWM 和风扇曲线控制。
- 诊断、历史记录、CSV 导出、界面缩放和控制器导航。

## 可选 Decky Quick Access

在 SteamOS/Game Mode 中，请通过 Dashboard 底部的 **Decky** 部分安装面板。应用会在缺少时安装 Decky Loader，或仅安装/修复 BC250 Quick Access。请参阅 [Decky README](../../integrations/decky/bc250-quick-access/README.md)。

## 安全

超频、修改 Compute Units 和风扇控制可能导致死机、关机、数据丢失或硬件损坏。一次只应用一项更改，保留恢复方法，并且不要将软件检查视为硬件验证。

## 致谢

项目通过明确且经过审查的流程整合社区工作。[第三方声明](../THIRD_PARTY_NOTICES.md)包含许可证、审查状态和集成边界。

## 语言

桌面界面支持 30 种语言，可跟随系统语言或在 Settings 中更改，包括英语、西班牙语、葡萄牙语、俄语、乌克兰语、德语、法语、波兰语、中文、日语、韩语等。

## 项目结构

```text
src/bc250cc/   应用与系统逻辑
frontends/     Desktop Qt、CLI 与 Quick Access 适配器
privileged/    受保护的 helpers 与 Polkit 策略
packaging/     软件包元数据和发行版配置
scripts/       启动器和本地安装程序
```

[MIT 许可证](../../LICENSE)。
