# BC250 Control Center

Graphical interface to manage an AMD BC-250 from Linux. It brings monitoring, processes, memory, GPU, CPU OC and 40CU into one app, with warnings and validations so you do not have to depend on scattered terminal commands.

## Installation

### Quick option with script

Use this option when running from the source code or from a tarball:

```bash
PREFIX="$HOME/.local" ./scripts/install-local.sh
"$HOME/.local/bin/bc250-control-center"
```

To uninstall that installation:

```bash
PREFIX="$HOME/.local" ./scripts/uninstall-local.sh
```

If you already deleted the project folder, the installer leaves a copy here:

```bash
PREFIX="$HOME/.local" "$HOME/.local/share/bc250-control-center/scripts/uninstall-local.sh"
```

### Packages by distribution

Stable package files are published in the project releases:

[https://github.com/movacx/bc250-control-center/releases](https://github.com/movacx/bc250-control-center/releases)

Download the file for your distribution from the latest release.

Arch/CachyOS/Manjaro:

```bash
sudo pacman -U ./bc250-control-center-git-*.pkg.tar.zst
```

Fedora/Nobara:

```bash
sudo dnf install ./bc250-control-center-*.fedora.rpm
```

Bazzite/Fedora Atomic:

```bash
sudo rpm-ostree install ./bc250-control-center-*.bazzite.rpm
systemctl reboot
```

## First use

1. Open `bc250-control-center`.
2. Go to **BC250**.
3. Press **Prepare dependencies**.
4. Read **Information > Safe BC250 use** before applying OC, 40CU or persistent changes.

## Main features

- Processes grouped by application.
- Performance view with CPU, memory, swap, GPU, disk, fans and sensors.
- BC250 panel with live metrics.
- GPU control through the `cyan-skillfish-governor-smu` TOML safe-points.
- Temporary and persistent CPU OC with visible limits.
- 40CU/24CU dashboard and actions through `bc250-cu-live-manager`.
- Local JSONL history.
- Translations from settings.

## External tools and credits

BC250 Control Center does not replace or claim ownership of the community tools. The app installs, clones or runs them from their official sources when needed.

Repositories used or referenced:

- `cyan-skillfish-governor`: https://github.com/Magnap/cyan-skillfish-governor
- `bc250_smu_oc`: https://github.com/bc250-collective/bc250_smu_oc
- `bc250-cu-live-manager`: https://github.com/WinnieLV/bc250-cu-live-manager
- `bc250-40cu-unlock`: https://github.com/duggasco/bc250-40cu-unlock

More details in `docs/THIRD_PARTY_NOTICES.md`.

## Safety

Overclock, 40CU and frequency changes can cause freezes, shutdowns, data loss or hardware damage. Every BC-250 is different. Test step by step and use it under your own responsibility.

## Quick structure

```text
mvc/                 PyQt6 application
scripts/             launchers and local installer
packaging/           package recipes and outputs
docs/                credits, architecture and project notes
```
