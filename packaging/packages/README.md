# Ready packages

This folder is only used to keep locally generated packages together before sharing a version.
Binary packages are not committed to the source repository; they are generated on your machine and ignored by Git.

Stable package files are published in the project releases:

[https://github.com/movacx/bc250-control-center/releases](https://github.com/movacx/bc250-control-center/releases)

```text
packaging/packages/
  arch/      .pkg.tar.zst for Arch, CachyOS and Manjaro
  fedora/    .rpm for Fedora and Nobara
  bazzite/   .rpm generated from Bazzite/Fedora Atomic
```

## Install commands

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
