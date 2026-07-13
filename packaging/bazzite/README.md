# Bazzite RPM build

Carpeta separada para generar el RPM directamente desde Bazzite/Fedora Atomic.

## Preparar Bazzite

```bash
sudo rpm-ostree install rpm-build rpmdevtools rsync
systemctl reboot
```

## Generar RPM

```bash
cd /ruta/al/ModoJuegoRAM
./packaging/bazzite/build-rpm-bazzite.sh
```

Salida esperada:

```text
packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
```

## Instalar el RPM generado

```bash
sudo rpm-ostree install ./packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
systemctl reboot
```

## Verificar archivo

```bash
file packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
rpm -qip packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
sha256sum packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
```
