# Installation and packaging review — 2026-10-31

## Reported failures

The Ubuntu 26.04 report showed `ModuleNotFoundError: PyQt6.QtSvg` after a
successful DEB installation. Qt's SVG library does not provide its Python
binding: Debian/Ubuntu/Mint also need `python3-pyqt6.qtsvg`.

The Fedora 44 and Linux Mint 22.3 reports could not resolve the native
Cheroot >=11.1.2 dependency. Mint 22 uses the Ubuntu 24.04 package base.
The supported web server requirement remains >=11.1.2,<12; it is now prepared
in an isolated environment owned by the ordinary user when web access starts.
Opening the desktop or asking for CLI help does not install web dependencies.

## Changes

- Updated DEB, RPM, Arch local package, AUR metadata and source tarball builders.
  Every package includes `requirements-web.txt`. Native desktop dependencies
  include pip/bootstrap tools, Qt SVG support, OpenSSL and CA certificates.
- Updated `install-local.sh` and per-distribution dependency preparation scripts.
  The source installer checks the real QtSvg import and SVG image plugin,
  Python >=3.11, pip >=22.3 and trusted CA availability. Failed runtime recovery
  stops before replacing an existing installation. Git is installed for updates.
- Included web requirements in transactional source upgrades and uninstall.
  User configuration and the isolated runtime retain their existing lifecycle.
- Updated CLI web startup, developer launcher checks, container QA and the
  Bazzite reboot detection package list. The terminal-only source profile still
  avoids Qt dependencies.

## Validation scope

Real repository package installation and desktop widget creation were checked
in disposable rootless Fedora 44, Ubuntu 26.04 and Ubuntu 24.04 containers.
Web checks prepare a fresh environment as an ordinary user, start HTTPS on
container loopback, verify the local CA against `/api/version`, and stop the
server. No ports are published and no host hardware settings are changed.

Ubuntu 24.04 covers Mint's package base; this is not a physical Mint boot or
hardware certification. Arch/AUR metadata and source archives are checked
separately. SteamOS and Bazzite scripts have automated coverage; this review
cannot replace testing them on their actual immutable host systems.

Builds retain version 1.21.4. Reinstall the newly built package when replacing
an older package with the same version. No public release is published by
these checks.
