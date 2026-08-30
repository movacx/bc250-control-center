# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Linux-Kontrollzentrum für die AMD BC-250: Überwachung, GPU-Steuerung, CPU-Tuning, Compute Units und Lüfter in einer Desktop-Anwendung.

## Screenshots

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center Dashboard" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Installation

```bash
# Aus dem Quellcode
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS und Manjaro
yay -S bc250-control-center-git
```

Zum Entfernen einer lokalen Installation `./uninstall-local.sh` im selben Ordner ausführen.

Pakete gibt es im [neuesten Release](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara und Bazzite verwenden dasselbe `noarch`-RPM:

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # nach rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Erster Start

1. `bc250-control-center` öffnen.
2. Im Dashboard **Prepare dependencies** wählen.
3. Status des Moduls prüfen, bevor eine Änderung angewendet wird.

## Funktionen

- Live-Werte für CPU, GPU, Speicher, Datenträger, Netzwerk, Temperaturen und Lüfter.
- GPU-Governor, CPU-Tuning und experimentelles Freischalten von Kernen.
- Steuerung von 24–40 Compute Units, PWM und Lüfterkurven.
- Diagnose, Verlauf, CSV-Export, UI-Skalierung und Controller-Navigation.

## Optionales Decky Quick Access

Unter SteamOS/Game Mode wird das Panel im unteren **Decky**-Bereich des Dashboards installiert. Die App installiert bei Bedarf Decky Loader oder installiert/repariert nur BC250 Quick Access. Siehe [Decky-README](../../integrations/decky/bc250-quick-access/README.md).

## Sicherheit

Übertaktung, Änderungen an Compute Units und Lüftersteuerung können Hänger, Abschaltungen, Datenverlust oder Hardwareschäden verursachen. Immer nur eine Änderung anwenden, einen Wiederherstellungsweg bereithalten und Software-Prüfungen nicht als Hardware-Validierung verstehen.

## Danksagungen

Das Projekt integriert Community-Arbeit über explizite, geprüfte Abläufe. [Hinweise zu Drittanbietern](../THIRD_PARTY_NOTICES.md) enthalten Lizenzen, Prüfstatus und Integrationsgrenzen.

## Sprachen

Die Desktop-Oberfläche unterstützt 30 Sprachen, folgt auf Wunsch der Systemsprache und kann in Settings geändert werden; darunter Englisch, Spanisch, Portugiesisch, Russisch, Ukrainisch, Deutsch, Französisch, Polnisch, Chinesisch, Japanisch, Koreanisch und weitere.

## Projektstruktur

```text
src/bc250cc/   Anwendungs- und Systemlogik
frontends/     Desktop-Qt-, CLI- und Quick-Access-Adapter
privileged/    geschützte Helper und Polkit-Richtlinie
packaging/     Paketmetadaten und Einrichtung je Distribution
scripts/       Starter und lokaler Installer
```

[MIT-Lizenz](../../LICENSE).
