# BC250 Control Center

Linux control center for the AMD BC-250. It brings monitoring, GPU control, CPU tuning, Compute Units, fans and BIOS updates into one desktop application, with clear limits and validation before every hardware change.

## Screenshots

<table>
  <tr>
    <td width="7%" align="center" valign="middle">
      <a href="https://movacx.github.io/bc250-control-center/gallery/#decky-monitoring" aria-label="Previous screenshot" title="Previous screenshot"><kbd>&#10094;</kbd></a>
    </td>
    <td width="86%" align="center" valign="middle">
      <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="assets/screenshots/dashboard-overview.png" alt="BC250 Control Center dashboard" width="100%"></a>
    </td>
    <td width="7%" align="center" valign="middle">
      <a href="https://movacx.github.io/bc250-control-center/gallery/#cpu" aria-label="Next screenshot" title="Next screenshot"><kbd>&#10095;</kbd></a>
    </td>
  </tr>
</table>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/English-238636?style=for-the-badge" alt="Read in English"></a>
  <a href="docs/readmes/README.es.md"><img src="https://img.shields.io/badge/Espa%C3%B1ol-1f6feb?style=for-the-badge" alt="Leer en español"></a>
  <a href="docs/readmes/README.pt-BR.md"><img src="https://img.shields.io/badge/Portugu%C3%AAs-8250df?style=for-the-badge" alt="Ler em português"></a>
  <a href="docs/readmes/README.ru.md"><img src="https://img.shields.io/badge/%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-bb2f7b?style=for-the-badge" alt="Читать на русском"></a>
  <a href="docs/readmes/README.uk.md"><img src="https://img.shields.io/badge/%D0%A3%D0%BA%D1%80%D0%B0%D1%97%D0%BD%D1%81%D1%8C%D0%BA%D0%B0-0969da?style=for-the-badge" alt="Читати українською"></a>
  <a href="docs/readmes/README.de.md"><img src="https://img.shields.io/badge/Deutsch-57606a?style=for-the-badge" alt="Auf Deutsch lesen"></a>
  <a href="docs/readmes/README.fr.md"><img src="https://img.shields.io/badge/Fran%C3%A7ais-c9510c?style=for-the-badge" alt="Lire en français"></a>
  <a href="docs/readmes/README.pl.md"><img src="https://img.shields.io/badge/Polski-0a7d6c?style=for-the-badge" alt="Czytaj po polsku"></a>
  <a href="docs/readmes/README.zh-CN.md"><img src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-9a6700?style=for-the-badge" alt="阅读中文说明"></a>
  <a href="docs/readmes/README.ja.md"><img src="https://img.shields.io/badge/%E6%97%A5%E6%9C%AC%E8%AA%9E-0550ae?style=for-the-badge" alt="日本語で読む"></a>
</p>

## Install

### Arch, CachyOS and SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Release packages

Download the package for your system from the [latest release](https://github.com/movacx/bc250-control-center/releases/latest):

| System | File |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<version>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<version>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<version>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: the same RPM, then reboot into the new deployment
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

On Debian and Ubuntu use `apt install`, not `dpkg -i`, so APT also downloads the dependencies. If `dpkg -i` already left the package half-installed, `sudo apt --fix-broken install` repairs it.

### Updates

No need to come back to this page. When a new version is out, the dashboard says so, shows what changed and installs it with your system's package manager, checking its SHA-256 first.

On SteamOS the update switches the read-only protection off, installs and switches it back on. A SteamOS update removes everything installed into the system, this application included: open **Reinstall BC250 Control Center** from the Desktop Mode menu, then run Prepare dependencies again. SteamOS asks for the `deck` password; if you never set one, run `passwd` in Konsole first.

**Coming from 1.19?** Its built-in updater cannot install packages. Update once by hand with the package from the [latest release](https://github.com/movacx/bc250-control-center/releases/latest); from then on the application updates itself.

```bash
# Bazzite / Fedora Atomic: replace the layered 1.19 in one step, then reboot
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# Installed with install-local.sh: remove that copy first, then install the package for your system
bash scripts/uninstall-local.sh
```

## First start

1. Open **BC250 Control Center**.
2. The welcome screen asks for your language, appearance and sidebar, and offers to install the tools the board needs. Everything can be changed later in **Settings**.
3. If you like, follow the guided tour: it visits every module and explains what each one changes on the board.

Before applying any change, check the module's status: it tells you what is ready, what is missing and why.

## What it does

**Dashboard and monitoring**
- Dashboard with processor, graphics and cooling, live cores, the temperature of every GDDR6 chip, power delivery rails (with the I2C mod) and the installed BIOS.
- Performance module with CPU, GPU, VRAM, RAM, disk and network charts, plus a Sensors view with minimum, average and maximum.

**Hardware**
- **GPU:** safe governor ranges for Cyan and Oberon, voltage laboratory and points above 2000 MHz.
- **CPU / SMU:** temporary and persistent tuning, stability test and experimental hidden-core unlocking.
- **Compute Units:** 24 to 40 CU, with the live and boot states reported separately.
- **Fans:** manual PWM control, temperature curves, profiles that survive a reboot and export to a file or to Decky.
- **Memory:** VRAM size, ZRAM, ZSWAP and swapfile.
- **Firmware (BIOS):** prepares an update USB with P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 or P2.00, with every file verified.

**System**
- Dependency preparation adapted to each distribution, with a built-in terminal that shows every command.
- Compatibility fixes: GFX1013 and async compute, per-game FSR4, telemetry and ACPI.
- Wi-Fi, Bluetooth and printer drivers from your distribution's official repositories.
- Diagnostics, history and CSV metric export.

**Interface**
- Light, Dark and Night blue themes, Standard and Formal styles, 10 accent colors and 70 % to 150 % scale.
- 30 languages and controller navigation.

## Decky Quick Access (optional)

A panel for the SteamOS Quick Access menu and Steam Game Mode. It brings the everyday controls (GPU, CU, CPU, fans and VRAM) without leaving the game; advanced setup stays in the desktop application.

- **Per-game profiles:** give each game a GPU and fan profile. It is applied when the game opens and everything goes back when it closes.
- **Live async compute:** shows whether the game uses asynchronous compute, and how much.
- **Fan presets:** with the names and speeds you export from the desktop.

To install it, open the **Dashboard**, scroll to the **Decky** section and choose the action it offers. If Decky Loader is missing, the application installs it; if it is already there, it installs or repairs only BC250 Quick Access. Normal dependency preparation never installs Decky on its own.

More details in the [Decky README](integrations/decky/bc250-quick-access/README.md).

## Safety

Overclocking, Compute Unit changes, fan control and BIOS updates can freeze or shut down the system, lose data or damage the hardware. Apply one change at a time, always keep a way back, and do not take the application's checks as a hardware guarantee.

## External tools and credits

BC250 Control Center builds on community work and claims none of these projects as its own. Each tool is used only through explicit, reviewed workflows.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): GPU governor.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): supported alternative governor.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) and [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): kernel and Mesa/RADV for GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): matched kernel and Mesa/RADV for Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute on Bazzite 44; its RADV patches are also built for Arch/CachyOS and Fedora on kernel 7.2 or newer.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) and [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): per-game FSR4.

**CPU and Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): CPU detection and tuning through the SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) and [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): core unlocking.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) and [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): CPU performance states through ACPI.

**Sensors, memory and fans**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): voltage regulator (VRM) telemetry.
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): GDDR6 memory temperature.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): VRAM size through CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): NCT sensors and fan PWM.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): stock P3.00 and Chipset Menu BIOS.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell and MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): mirror of ASRock's update kit (P2.00 and P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): custom boot logo.

Licenses, review status and the exact scope of every integration are in the [third-party notices](docs/THIRD_PARTY_NOTICES.md).

## Project layout

```text
bc250-control-center/
├── src/bc250cc/          The core, without a graphical interface
│   ├── domain/           Rules and limits of each module (GPU, CPU, CU, fans, firmware…)
│   ├── application/      Use cases that combine those rules
│   ├── infrastructure/   System access: sensors, services, packages, GitHub
│   ├── platform/         Differences between distributions and init systems
│   └── shared/           Version, paths and contracts shared by every process
├── frontends/
│   ├── desktop/          Qt desktop application
│   │   ├── pages/        One file per module (dashboard, GPU, CPU, fans, firmware…)
│   │   ├── components/   Reusable interface pieces
│   │   ├── onboarding/   Welcome screen and guided tour
│   │   ├── console/      Built-in terminal
│   │   ├── theme/        Themes, styles, colors and icons
│   │   └── i18n/         Translations into 30 languages
│   └── cli.py            Command-line mode
├── integrations/decky/   Decky Quick Access plugin for Game Mode
├── privileged/           What runs as root, isolated and reviewed
│   ├── helpers/          One helper per privileged task
│   ├── lib/              Code shared by those helpers
│   └── policies/         Polkit permissions
├── packaging/            The .pkg.tar.zst, .rpm and .deb packages, and the AUR PKGBUILD
├── scripts/              Launchers, local installer and system utilities
├── assets/               Icons, screenshots and web gallery
├── docs/                 Documentation, third-party notices and translations of this README
└── tests/                More than 4000 automated tests
```

Licensed under the [MIT License](LICENSE).
