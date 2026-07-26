# BC250 Control Center

Graphical interface to manage an AMD BC-250 from Linux. It brings monitoring, processes, memory, GPU, CPU OC, 40CU and fan control into one app, with warnings and validations so you do not have to depend on scattered terminal commands.

## Installation

### Arch AUR

The package is available in AUR:

[https://aur.archlinux.org/packages/bc250-control-center-git](https://aur.archlinux.org/packages/bc250-control-center-git)

Install it on Arch/CachyOS/Manjaro with an AUR helper:

```bash
yay -S bc250-control-center-git
```

or:

```bash
paru -S bc250-control-center-git
```

### Packages by distribution

Stable package files are published in the project releases:

[https://github.com/movacx/bc250-control-center/releases](https://github.com/movacx/bc250-control-center/releases)

Download the file for your distribution from the latest release.

Fedora/Nobara:

```bash
sudo dnf install ./bc250-control-center-*.fedora.rpm
```

Bazzite/Fedora Atomic:

```bash
sudo rpm-ostree install ./bc250-control-center-*.bazzite.rpm
systemctl reboot
```

Ubuntu/Debian:

```bash
sudo apt install ./bc250-control-center_*.deb
```

If `apt` cannot resolve it directly, use:

```bash
sudo dpkg -i ./bc250-control-center_*.deb
sudo apt -f install
```

## First use

1. Open `bc250-control-center`.
2. Go to **BC250**.
3. Press **Prepare dependencies**. The app selects an isolated strategy for Arch, Manjaro, CachyOS, Debian, Ubuntu, Fedora, Bazzite or SteamOS. On Arch-family systems it verifies the complete AUR toolchain and installs Yay when no supported helper exists. On Bazzite it downloads the user-space tools first, stages all host packages in one `rpm-ostree` deployment and asks for one reboot; a second press is not required.
4. Open **Fans** and press **Prepare fan PWM** when the nct6687 driver is not ready. The app uses the active distribution strategy and reports missing kernel headers or an immutable-system reboot requirement without disabling read-only monitoring. On Bazzite the module is stored per kernel under `/var` and loaded by a persistent system service instead of modifying the immutable module tree.
5. Read **Information > Safe BC250 use** before applying OC, 40CU, fan PWM or persistent changes.

## Main features

- Processes grouped by application.
- Performance view with CPU, memory, swap, GPU, disk, fans and sensors.
- BC250 panel with live metrics. The power tile reports **Total board power** only when Linux exposes a dedicated whole-system sensor; otherwise it is explicitly labeled **SoC package power** instead of estimating or mislabeling the value.
- GPU control through the `cyan-skillfish-governor-smu` TOML safe-points.
- Temporary and persistent CPU OC with visible limits.
- 40CU/24CU dashboard and actions through `bc250-cu-live-manager`; SteamOS uses a compatible SteamOS live-manager backend.
- Fan module for BC-250 sensors, RPM monitoring, manual fan speed control and a simple GPU temperature curve when `nct6687d` is prepared.
- Local JSONL history.
- Smart, throttled safety alerts for temperature, memory pressure and governor state.
- Live theme, interface scaling and translation from Settings for English, Spanish, Portuguese, Russian, Ukrainian and German.
- Content-aware dialogs that reflow after language changes.
- Optional SteamOS-style gamepad navigation with hot-plug, ABXY hints, D-pad/left-stick focus movement, A/B actions and LB/RB section switching.

## Gamepad navigation

Compatible Xbox/ABXY controllers can navigate the interface without replacing mouse or keyboard use.

- D-pad or left stick: move focus.
- A: activate the focused control.
- B: close dialogs or go back.
- LB/RB: switch modules or Settings sections.

The optional `python-evdev` backend is used when available; otherwise the app falls back to Linux `/dev/input/js*`. No controller is required at startup.

## Fan module

The fan panel is experimental and focused on the BC-250 fan header. It can show the main fan RPM, CPU/GPU temperatures, PWM status, visible fan channels and diagnostic output. When the `nct6687d` driver is prepared, the app can apply manual speed percentages and a simple GPU temperature curve. Splitters or PWM hubs usually share one control signal and may report only one RPM reading.

## Languages

The interface includes language support for:

- English
- Spanish
- Portuguese
- Russian
- Ukrainian
- German

## External tools and credits

BC250 Control Center does not replace or claim ownership of the community tools. The app installs, clones or runs them from their official sources when needed.

Repositories used or referenced:

- `cyan-skillfish-governor`: https://github.com/filippor/cyan-skillfish-governor/tree/smu
- `bc250_smu_oc`: https://github.com/bc250-collective/bc250_smu_oc
- `bc250-cu-live-manager`: https://github.com/WinnieLV/bc250-cu-live-manager
- `bc250-cu-live-manager-SteamOS`: https://github.com/F5GO/bc250-cu-live-manager-SteamOS
- `bc250-40cu-unlock`: https://github.com/duggasco/bc250-40cu-unlock
- `nct6687d`: https://github.com/Fred78290/nct6687d

More details in `docs/THIRD_PARTY_NOTICES.md`.

## Safety

Overclock, 40CU and frequency changes can cause freezes, shutdowns, data loss or hardware damage. Every BC-250 is different. Test step by step and use it under your own responsibility.

## Quick structure

```text
mvc/
├── Controller/      frontend/backend facade
├── Model/           data contracts
├── Repository/      system and hardware access
├── service/         validation and orchestration
├── Daemon/          optional background monitor
├── View/            definitive PyQt6 interface
└── main.py           minimal application entry point
scripts/              launchers and local installer
packaging/            package recipes and outputs
docs/                 architecture and third-party notices only
```

Distribution-specific integration lives in `mvc/Repository/Os_repository/`; the publishable docs folder intentionally keeps only `ARQUITECTURA_MVC.md` and `THIRD_PARTY_NOTICES.md`.
