# Packaging

This folder contains the package recipes and local package outputs for BC250 Control Center.

## Ready packages

Stable package files are published in the project releases:

[https://github.com/movacx/bc250-control-center/releases](https://github.com/movacx/bc250-control-center/releases)

Download the file for your distribution from the latest release.

Local builds can also be copied to:

```text
packaging/packages/arch/      .pkg.tar.zst for Arch, CachyOS and Manjaro
packaging/packages/fedora/    .rpm for Fedora and Nobara
packaging/packages/bazzite/   .rpm for Bazzite / Fedora Atomic
packaging/packages/debian/    .deb for Ubuntu and Debian
```

Those binaries are for local testing or release preparation. They are not meant to be committed to the source repository.

## Install packages

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

Ubuntu/Debian:

```bash
sudo apt install ./bc250-control-center_*.deb
```

Alternative:

```bash
sudo dpkg -i ./bc250-control-center_*.deb
sudo apt -f install
```

If you are installing from local build folders instead of GitHub releases, use:

```bash
sudo pacman -U packaging/packages/arch/bc250-control-center-git-*.pkg.tar.zst
sudo dnf install packaging/packages/fedora/bc250-control-center-*.rpm
sudo rpm-ostree install packaging/packages/bazzite/bc250-control-center-*.rpm
sudo apt install ./packaging/packages/debian/bc250-control-center_*.deb
```

## Local install without package

```bash
./scripts/install-local.sh
bc250-control-center
```

The installer keeps the GUI under `~/.local` by default and requests `sudo` only for
missing system dependencies plus the fixed root-owned PWM helper and its Polkit action.
Set `BC250_SKIP_PRIVILEGED_HELPER=1` only for development or GUI-only testing.
On Bazzite/Fedora Atomic, prefer the RPM installed through `rpm-ostree`; a local install
cannot place the hardened helper inside the immutable `/usr` deployment.

If your shell does not find the command, run:

```bash
"$HOME/.local/bin/bc250-control-center"
```

Uninstall:

```bash
./scripts/uninstall-local.sh
```

If the source folder was deleted:

```bash
"$HOME/.local/share/bc250-control-center/scripts/uninstall-local.sh"
```

## Build packages

Arch-like:

```bash
./packaging/scripts/build-local-pkg.sh
```

Fedora/Nobara:

```bash
./packaging/scripts/build-rpm.sh
```

Bazzite/Fedora Atomic, executed from Bazzite:

```bash
./packaging/bazzite/build-rpm-bazzite.sh
```

Ubuntu/Debian `.deb`:

```bash
./packaging/debian/build-deb.sh
```

## Structure

```text
packaging/
  arch/       local Arch PKGBUILD
  rpm/        RPM spec
  bazzite/    RPM builder for Bazzite/Fedora Atomic
  debian/     DEB builder for Ubuntu and Debian
  common/     desktop entry, metainfo and systemd user service
  packages/   local copy of final packages
  scripts/    build scripts
```

## AUR recipe backup

The AUR publication files are kept in `packaging/arch/aur/`. They are useful when moving to another PC: clone the AUR package repository, copy those files, regenerate `.SRCINFO` if needed, then commit and push to AUR. Built packages should stay out of AUR.
