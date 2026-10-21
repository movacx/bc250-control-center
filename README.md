# BC250 Control Center

**One app to set up, tune and monitor an AMD BC-250 on Linux.**

The BC-250 is a mining board with a PlayStation 5 APU that the community turned into a gaming PC. Getting it right used to mean a dozen scripts, forum threads and kernel patches. BC250 Control Center puts that work in one window: it prepares your distribution, runs the GPU governor, tunes the CPU, unlocks Compute Units, drives the fans, shows every sensor the board has and builds BIOS update USBs. Each hardware change has limits and a check before it is applied.

It is shaped by the BC-250 community: most features started as a bug report or a "can it do X?" on Discord.

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="assets/screenshots/dashboard-overview.png" alt="BC250 Control Center dashboard" width="100%"></a>
  <br>
  <sub><a href="https://movacx.github.io/bc250-control-center/gallery/">See every screen in the gallery</a></sub>
</p>

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

---

## Contents

- [Supported systems](#supported-systems)
- [Install](#install)
- [Keeping it up to date](#keeping-it-up-to-date)
- [Your first ten minutes](#your-first-ten-minutes)
- [Modules](#modules)
- [Decky Quick Access for Game Mode](#decky-quick-access-for-game-mode)
- [When something goes wrong](#when-something-goes-wrong)
- [Before you touch the hardware](#before-you-touch-the-hardware)
- [Built on the community's work](#built-on-the-communitys-work)
- [Inside the repository](#inside-the-repository)

## Supported systems

| Distribution | Package | Notes |
|---|---|---|
| Arch, CachyOS, Manjaro | `.pkg.tar.zst`, or `bc250-control-center-git` from the AUR | CachyOS can use MastaG's matched BC-250 kernel and Mesa. |
| Fedora, Nobara | `.noarch.rpm` | Warns when Mesa is too old and the desktop falls back to the CPU. |
| Bazzite and other Fedora Atomic | `.noarch.rpm` through `rpm-ostree` | Needs a reboot into the new deployment after installing or updating. |
| SteamOS | AUR package | The app turns the read-only protection off and on around each install. A SteamOS system update removes it; see [Keeping it up to date](#keeping-it-up-to-date). |
| Ubuntu, Linux Mint, Debian 13 | `_all.deb` | Install with `apt`, not `dpkg -i`, so the dependencies come along. |

Other distributions are detected and handled where possible, including OpenRC systems such as Gentoo and Alpine. If yours is not in the table, try it and tell me how it went.

## Install

**AUR (Arch, CachyOS, SteamOS):**

```bash
yay -S bc250-control-center-git
```

**Release packages:** download the file for your system from the [latest release](https://github.com/movacx/bc250-control-center/releases/latest), then:

```bash
# Arch, CachyOS, Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora, Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite, Fedora Atomic
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu, Linux Mint, Debian
sudo apt install ./bc250-control-center_*.deb
```

If `dpkg -i` already left the package half-installed on Debian or Ubuntu, `sudo apt --fix-broken install` repairs it.

## Keeping it up to date

You install once. When a new version is out, the dashboard says so, shows the changelog, checks the package's SHA-256 and installs it with your package manager.

- **SteamOS:** a SteamOS system update wipes everything installed into the system, this app included. Afterwards, open **Reinstall BC250 Control Center** from the Desktop Mode menu and run Prepare dependencies again. SteamOS asks for the `deck` password; if you never set one, run `passwd` in Konsole first.
- **Coming from 1.19:** its updater cannot install packages. Update once by hand from the [latest release](https://github.com/movacx/bc250-control-center/releases/latest); from then on the app updates itself.

```bash
# Bazzite / Fedora Atomic: replace a layered 1.19 in one step, then reboot
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# Installed with install-local.sh: from the folder you installed it from, remove that copy,
# then install the package for your system
bash scripts/uninstall-local.sh
```

## Your first ten minutes

1. Open **BC250 Control Center**. The welcome screen asks for language, appearance and sidebar, and offers to install what the board needs. All of it can be changed later in **Settings**.
2. Take the guided tour. It walks through every module and says what each one touches on the board.
3. On the **Dashboard**, run **Prepare BC250 system**. It lists what it will install for your distribution (the GPU governor, sensors, the tools the CPU and Compute Units modules need) and runs it in a built-in terminal, so every command is visible.
4. Before applying anything in a module, read its status line: it says what is ready, what is missing and why.

## Modules

| Module | What it does | Touches the hardware |
|---|---|---|
| **Dashboard** | Processor, graphics and cooling at a glance; live cores, the temperature of each GDDR6 chip, the installed BIOS and notices when something installed needs attention. The power rails need a small hardware modification (two wires between two headers, no soldering); the app's **Guide with photos** shows where they go. | No |
| **Performance** | CPU, GPU, VRAM, RAM, disk and network charts, and a Sensors view with minimum, average and maximum. CSV export. | No |
| **GPU** | The Cyan governor (Oberon as an alternative) with safe ranges, a voltage laboratory and points above 2000 MHz. If you are unsure, use Cyan. | Yes |
| **CPU / SMU** | Temporary and persistent tuning, a stability test and the experimental hidden-core unlock. | Yes |
| **Compute Units** | 24 to 40 CU, with the live and boot states shown separately. | Yes |
| **Fans** | Manual PWM, temperature curves, profiles that survive a reboot, export to a file or to Decky, or hand the fan to CoolerControl, fancontrol or fan2go. | Yes |
| **Firmware (BIOS)** | Builds an update USB with P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 or P2.00, every file verified. | Writes a USB stick |
| **Additional settings** | VRAM size, ZRAM, ZSWAP and swap; compatibility fixes (GFX1013, async compute, ACPI, Mesa); Dolby Digital 5.1 over HDMI; TV control over HDMI-CEC with Valve's cecd. | Some options |
| **Upscaling** | FSR4 INT8 through OptiScaler Client and HelixSR (DLSS Model E in FSR 3.1 games), per game. Backs up and restores any game the client added, offers new upstream versions on its own, and keeps the Steam launch option in one place. | Writes into game folders, with backups |
| **Drivers** | Wi-Fi, Bluetooth and printer drivers from your distribution's repositories, and case accessories (Thermalright screen, Corsair fans). | No |

The interface comes in 30 languages, with Light, Dark and Night blue themes, Standard and Formal styles, 10 accent colors, 70 % to 150 % scale and controller navigation.

## Decky Quick Access for Game Mode

An optional panel in the Quick Access menu, for the everyday changes (GPU, CU, CPU, fans, VRAM) without leaving the game. The advanced setup stays in the desktop app.

- **Per-game profiles:** a GPU and fan profile per game, applied when it opens and undone when it closes.
- **Live async compute:** whether the game uses asynchronous compute, and how much.
- **Fan presets:** with the names and speeds exported from the desktop.

It is only useful if you play from Steam's Game Mode. To install it, open the **Dashboard** and press the action in the **Decky** section: that installs Decky Loader too if it is missing. Nothing else installs Decky; Prepare BC250 system leaves it alone. More in the [Decky README](integrations/decky/bc250-quick-access/README.md).

## When something goes wrong

Every error window names the fault and where it happened:

- **An error code** such as `BC250-UPSCALE-001`, with what happened, the likely cause and how to fix it.
- **An origin code** such as `GPU-0142`. Every function in the app has a stable one, so the code points at the exact action and the exact line that raised the error.
- **The raw error**, exactly as it was raised, with its traceback one click away.

Press **Report this problem** in that window, or **Settings › Diagnostics › Send a report**, and the report form opens inside the app with all of that filled in, plus your system's specifications and recent errors. You see exactly what is sent before sending it, paths have your home folder replaced by `~`, and if Google Forms cannot be reached the form opens in the browser without losing what you wrote. The same form is [on the web](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform).

## Before you touch the hardware

Overclocking, unlocking Compute Units, controlling fans and flashing a BIOS can freeze the machine, lose data or kill the board. Change one thing at a time and keep a way back. The app's checks catch the obvious mistakes, not all of them; they are not a guarantee.

## Built on the community's work

None of this exists without the people who reverse-engineered the board. These projects are theirs; the app only reaches them through workflows I have read and pinned. Licenses, review status and the exact scope of every integration are in the [third-party notices](docs/THIRD_PARTY_NOTICES.md).

| Area | Project | Used for |
|---|---|---|
| GPU | [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu) | GPU governor |
| GPU | [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor) | Alternative governor |
| GPU | [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix), [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos) | Kernel and Mesa/RADV for GFX1013 |
| GPU | [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250) | Matched kernel and Mesa/RADV for Arch and CachyOS |
| GPU | [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite) | Async compute on Bazzite 44; its RADV patches also built for Arch/CachyOS and Fedora on kernel 7.2+ |
| Upscaling | [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4), [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) | FSR4 per game (OptiScaler Client) |
| Upscaling | [HelixSR](https://github.com/lonewolf0622/HelixSR) | DLSS Model E reconstruction in FSR 3.1 games |
| CPU | [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc) | CPU detection and tuning through the SMU |
| CPU | [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock), [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock) | Hidden-core unlock |
| CPU | [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix) | CPU performance states through ACPI |
| Compute Units | [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [its SteamOS port](https://github.com/F5GO/bc250-cu-live-manager-SteamOS), [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock) | 24 to 40 CU |
| Sensors | [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry) | VRM telemetry, and the photos of the I2C guide |
| Sensors | [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature) | GDDR6 temperature |
| Sensors | [nct6687d](https://github.com/Fred78290/nct6687d) | NCT sensors and fan PWM |
| Memory | [bc250_memcfg](https://github.com/fanoush/bc250_memcfg) | VRAM size through CMOS |
| HDMI | [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec) | cecd, Valve's HDMI-CEC daemon |
| Firmware | [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios) | Stock P3.00 and Chipset Menu BIOS |
| Firmware | [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script) | UEFI Shell and MeiMeiDXE v3 |
| Firmware | [BC-250](https://github.com/kenavru/BC-250) | Mirror of ASRock's update kit (P2.00 and P5.00) |
| Firmware | [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo) | Custom boot logo |

**Projects I am following** (not used by the app yet; licenses as GitHub reports them):
[bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) and [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0), VRM and memory temperatures as kernel modules;
[bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0), another take on setting up Bazzite;
[bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) and [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm), VCN video encoding research and an open Windows driver. Neither declares a license, so they are only linked.

## Inside the repository

```text
bc250-control-center/
├── src/bc250cc/          Core, with no graphical interface
│   ├── domain/           Rules and limits of each module
│   ├── application/      Use cases that combine those rules
│   ├── infrastructure/   System access: sensors, services, packages, GitHub
│   ├── platform/         Differences between distributions and init systems
│   └── shared/           Version, paths, error and origin codes shared by every process
├── frontends/desktop/    Qt desktop app: pages, components, onboarding, terminal, themes, 30 languages
├── integrations/decky/   Decky Quick Access plugin for Game Mode
├── privileged/           What runs as root, isolated and reviewed: one helper per task, polkit policies
├── packaging/            .pkg.tar.zst, .rpm, .deb and the AUR PKGBUILD
├── scripts/              Launchers, local installer, system utilities and the distribution test matrix
├── assets/               Icons, screenshots, the web gallery and the I2C guide photos
├── docs/                 Third-party notices and translations of this README
└── tests/                Over 5,000 automated tests, with os-release files from 37 real distributions
```

To run it from a checkout: `./run.sh`. To install that checkout for your user: `bash scripts/install-local.sh`.

## Contributing

Bug reports help the most: use the in-app report, or open an issue with your distribution, kernel and what the terminal printed. If you run a distribution that is not listed, tell me how it went either way.

Licensed under the [MIT License](LICENSE).
