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

If you are installing from local build folders instead of GitHub releases, use:

```bash
sudo pacman -U packaging/packages/arch/bc250-control-center-git-*.pkg.tar.zst
sudo dnf install packaging/packages/fedora/bc250-control-center-*.rpm
sudo rpm-ostree install packaging/packages/bazzite/bc250-control-center-*.rpm
```

## Local install without package

```bash
PREFIX="$HOME/.local" ./scripts/install-local.sh
bc250-control-center
```

Uninstall:

```bash
PREFIX="$HOME/.local" ./scripts/uninstall-local.sh
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

## Structure

```text
packaging/
  arch/       local Arch PKGBUILD
  rpm/        RPM spec
  bazzite/    RPM builder for Bazzite/Fedora Atomic
  common/     desktop entry, metainfo and systemd user service
  packages/   local copy of final packages
  scripts/    build scripts
```
