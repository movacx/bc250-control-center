# Packaging

Aqui estan las recetas y salidas de paquetes para BC250 Control Center.

## Paquetes listos

Cuando se construyen paquetes, tambien se copian a:

```text
packaging/packages/arch/      .pkg.tar.zst para Arch, CachyOS y Manjaro
packaging/packages/fedora/    .rpm para Fedora y Nobara
packaging/packages/bazzite/   .rpm para Bazzite / Fedora Atomic
```

Esos binarios son para compartir releases o pruebas locales. No se suben al repositorio fuente.

## Instalar paquetes

Arch/CachyOS/Manjaro:

```bash
sudo pacman -U packaging/packages/arch/bc250-control-center-git-*.pkg.tar.zst
```

Fedora/Nobara:

```bash
sudo dnf install packaging/packages/fedora/bc250-control-center-*.noarch.rpm
```

Bazzite/Fedora Atomic:

```bash
sudo rpm-ostree install packaging/packages/bazzite/bc250-control-center-*.noarch.rpm
systemctl reboot
```

## Instalacion local sin paquete

```bash
PREFIX="$HOME/.local" ./scripts/install-local.sh
bc250-control-center
```

Desinstalar:

```bash
PREFIX="$HOME/.local" ./scripts/uninstall-local.sh
```

## Construir paquetes

Arch-like:

```bash
./packaging/scripts/build-local-pkg.sh
```

Fedora/Nobara:

```bash
./packaging/scripts/build-rpm.sh
```

Bazzite/Fedora Atomic, ejecutado desde Bazzite:

```bash
./packaging/bazzite/build-rpm-bazzite.sh
```

## Estructura

```text
packaging/
  arch/       PKGBUILD local y AUR
  rpm/        spec RPM
  bazzite/    builder RPM para Bazzite/Fedora Atomic
  common/     desktop entry, metainfo y systemd user service
  packages/   copia local de paquetes finales
  scripts/    scripts de construccion
```
