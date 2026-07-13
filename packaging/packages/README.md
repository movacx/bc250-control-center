# Paquetes listos para probar

Esta carpeta es solo para dejar juntos los paquetes generados localmente antes de compartir una version.
Los binarios no se suben al repositorio; se generan en tu maquina y quedan ignorados por Git.

```text
packaging/packages/
  arch/      .pkg.tar.zst para Arch, CachyOS y Manjaro
  fedora/    .rpm para Fedora y Nobara
  bazzite/   .rpm generado desde Bazzite/Fedora Atomic
```

## Comandos de instalacion

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
