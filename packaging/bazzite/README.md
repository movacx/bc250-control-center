# Bazzite RPM build

Separate folder to generate the RPM directly from Bazzite/Fedora Atomic.

Stable package files are published in the project releases:

[https://github.com/movacx/bc250-control-center/releases](https://github.com/movacx/bc250-control-center/releases)

## Prepare Bazzite

```bash
sudo rpm-ostree install rpm-build rpmdevtools rsync
systemctl reboot
```

## Build RPM

```bash
cd /path/to/bc250-control-center
./packaging/bazzite/build-rpm-bazzite.sh
```

Expected output:

```text
packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
```

## Install the generated RPM

```bash
sudo rpm-ostree install ./packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
systemctl reboot
```

## Check the file

```bash
file packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
rpm -qip packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
sha256sum packaging/bazzite/out/bc250-control-center-0.1.0-*.noarch.rpm
```
