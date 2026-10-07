# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Kontrollzentrum für die AMD BC-250 unter Linux. Überwachung, GPU-Steuerung, CPU-Tuning, Compute Units, Lüfter und BIOS-Aktualisierung in einer Desktop-Anwendung – mit klaren Grenzen und Prüfungen vor jeder Änderung an der Hardware.

## Screenshots

[<img src="../../assets/screenshots/dashboard-overview.png" alt="BC250 Control Center Übersicht" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Alle Screenshots ansehen →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Installation

### Arch, CachyOS und SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Release-Pakete

Lade das Paket für dein System aus dem [neuesten Release](https://github.com/movacx/bc250-control-center/releases/latest) herunter:

| System | Datei |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<Version>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<Version>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<Version>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: dasselbe RPM, danach in das neue Deployment neu starten
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

Unter Debian und Ubuntu `apt install` statt `dpkg -i` verwenden: So lädt APT auch die Abhängigkeiten. Hat `dpkg -i` das Paket nur halb installiert, repariert `sudo apt --fix-broken install` das.

### Aktualisierungen

Du musst nicht auf diese Seite zurückkommen. Wenn eine neue Version erscheint, meldet die Übersicht das, zeigt die Änderungen und installiert sie mit dem Paketmanager deines Systems, nachdem sie die SHA-256 geprüft hat.

Unter SteamOS schaltet das Update den Schreibschutz aus, installiert und schaltet ihn wieder ein. Ein SteamOS-Update entfernt alles, was ins System installiert wurde, auch diese Anwendung: Öffnen Sie **Reinstall BC250 Control Center** im Menü des Desktop-Modus und bereiten Sie die Abhängigkeiten erneut vor. SteamOS fragt nach dem Passwort von `deck`; falls Sie nie eines gesetzt haben, führen Sie zuerst `passwd` in Konsole aus.

**Von 1.19 kommend?** Deren Updater kann keine Pakete installieren. Aktualisieren Sie einmal von Hand mit dem Paket der [neuesten Version](https://github.com/movacx/bc250-control-center/releases/latest); danach aktualisiert sich die Anwendung selbst. Unter Bazzite ersetzen Sie 1.19 in einem Schritt und starten neu; bei einer Installation mit install-local.sh entfernen Sie zuerst diese Kopie:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Erster Start

1. Öffne **BC250 Control Center**.
2. Der Willkommensbildschirm fragt nach Sprache, Aussehen und Seitenleiste und bietet an, die Werkzeuge zu installieren, die die Platine braucht. Alles lässt sich später in den **Einstellungen** ändern.
3. Wenn du möchtest, folge der geführten Tour: Sie besucht jedes Modul und erklärt, was es an der Platine ändert.

Prüfe vor jeder Änderung den Status des Moduls: Er sagt, was bereit ist, was fehlt und warum.

## Funktionen

**Übersicht und Überwachung**
- Übersicht mit Prozessor, Grafik und Kühlung, Kernen live, der Temperatur jedes GDDR6-Chips, den Stromversorgungsschienen (mit I2C-Mod) und dem installierten BIOS.
- Leistungsmodul mit Diagrammen für CPU, GPU, VRAM, RAM, Datenträger und Netzwerk sowie einer Sensoransicht mit Minimum, Durchschnitt und Maximum.

**Hardware**
- **GPU:** sichere Governor-Bereiche für Cyan und Oberon, Spannungslabor und Punkte über 2000 MHz.
- **CPU / SMU:** temporäres und dauerhaftes Tuning, Stabilitätstest und experimentelles Freischalten versteckter Kerne.
- **Compute Units:** 24 bis 40 CU, Live- und Startzustand getrennt angezeigt.
- **Lüfter:** manuelle PWM-Steuerung, Temperaturkurven, Profile, die einen Neustart überstehen, und Export in eine Datei oder zu Decky.
- **Speicher:** VRAM-Größe, ZRAM, ZSWAP und Auslagerungsdatei.
- **Firmware (BIOS):** erstellt einen Update-USB-Stick mit P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 oder P2.00, jede Datei geprüft.

**System**
- Vorbereitung der Abhängigkeiten passend zu jeder Distribution, mit einem eingebauten Terminal, das jeden Befehl zeigt.
- Kompatibilitätskorrekturen: GFX1013 und Async Compute, FSR4 pro Spiel, Telemetrie und ACPI.
- WLAN-, Bluetooth- und Druckertreiber aus den offiziellen Paketquellen deiner Distribution.
- Diagnose, Verlauf und Export der Messwerte als CSV.

**Oberfläche**
- Themes Hell, Dunkel und Nachtblau, Stile Standard und Förmlich, 10 Akzentfarben und Skalierung von 70 % bis 150 %.
- 30 Sprachen und Controller-Navigation.

## Decky Quick Access (optional)

Ein Panel für das Schnellzugriffsmenü von SteamOS und den Steam-Spielmodus. Es bringt die alltäglichen Regler (GPU, CU, CPU, Lüfter und VRAM) ins Spiel; die erweiterte Einrichtung bleibt in der Desktop-Anwendung.

- **Profile pro Spiel:** Weise jedem Spiel ein GPU- und Lüfterprofil zu. Es wird beim Start des Spiels angewendet, und beim Beenden kehrt alles zum vorherigen Zustand zurück.
- **Async Compute live:** zeigt, ob und wie stark das Spiel asynchrones Rechnen nutzt.
- **Lüfter-Presets:** mit den Namen und Drehzahlen, die du vom Desktop exportierst.

Zum Installieren öffne die **Übersicht**, scrolle zum Abschnitt **Decky** und wähle die angebotene Aktion. Fehlt Decky Loader, installiert die Anwendung ihn; ist er schon da, installiert oder repariert sie nur BC250 Quick Access. Die normale Vorbereitung der Abhängigkeiten installiert Decky nie von selbst.

Mehr dazu im [Decky-README](../../integrations/decky/bc250-quick-access/README.md).

## Sicherheit

Übertakten, Änderungen an den Compute Units, Lüftersteuerung und BIOS-Aktualisierungen können das System einfrieren oder abschalten, Daten verlieren oder die Hardware beschädigen. Nimm eine Änderung nach der anderen vor, halte immer einen Weg zurück bereit und betrachte die Prüfungen der Anwendung nicht als Garantie für die Hardware.

## Externe Werkzeuge und Danksagungen

BC250 Control Center baut auf der Arbeit der Community auf und beansprucht keines dieser Projekte für sich. Jedes Werkzeug wird nur über ausdrückliche, geprüfte Abläufe genutzt.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): GPU-Governor.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): unterstützter alternativer Governor.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) und [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): Kernel und Mesa/RADV für GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): abgestimmte Kernel- und Mesa/RADV-Pakete für Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): Async Compute unter Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) und [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 pro Spiel.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): Rekonstruktion mit DLSS Model E für FSR-3.1-Spiele, pro Spiel.

**CPU und Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): CPU-Erkennung und -Tuning über die SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) und [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): Freischalten von Kernen.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) und [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): CPU-Leistungszustände über ACPI.

**Sensoren, Speicher und Lüfter**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): Telemetrie der Spannungsregler (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): Temperatur des GDDR6-Speichers.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): VRAM-Größe über CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): NCT-Sensoren und Lüfter-PWM.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): originales P3.00- und Chipset-Menu-BIOS.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell und MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): Kopie des ASRock-Update-Kits (P2.00 und P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): eigenes Boot-Logo.

Lizenzen, Prüfstatus und der genaue Umfang jeder Integration stehen in den [Hinweisen zu Drittanbietern](../THIRD_PARTY_NOTICES.md).

## Projektstruktur

```text
bc250-control-center/
├── src/bc250cc/          Der Kern, ohne grafische Oberfläche
│   ├── domain/           Regeln und Grenzen jedes Moduls (GPU, CPU, CU, Lüfter, Firmware…)
│   ├── application/      Anwendungsfälle, die diese Regeln kombinieren
│   ├── infrastructure/   Systemzugriff: Sensoren, Dienste, Pakete, GitHub
│   ├── platform/         Unterschiede zwischen Distributionen und Init-Systemen
│   └── shared/           Version, Pfade und Verträge, die alle Prozesse teilen
├── frontends/
│   ├── desktop/          Qt-Desktop-Anwendung
│   │   ├── pages/        Eine Datei pro Modul (Übersicht, GPU, CPU, Lüfter, Firmware…)
│   │   ├── components/   Wiederverwendbare Oberflächenteile
│   │   ├── onboarding/   Willkommensbildschirm und geführte Tour
│   │   ├── console/      Eingebautes Terminal
│   │   ├── theme/        Themes, Stile, Farben und Symbole
│   │   └── i18n/         Übersetzungen in 30 Sprachen
│   └── cli.py            Befehlszeilenmodus
├── integrations/decky/   Decky-Quick-Access-Plugin für den Spielmodus
├── privileged/           Was als root läuft, isoliert und geprüft
│   ├── helpers/          Ein Helfer pro privilegierter Aufgabe
│   ├── lib/              Von diesen Helfern gemeinsam genutzter Code
│   └── policies/         Polkit-Berechtigungen
├── packaging/            Die Pakete .pkg.tar.zst, .rpm und .deb sowie das AUR-PKGBUILD
├── scripts/              Starter, lokaler Installer und Systemwerkzeuge
├── assets/               Symbole, Screenshots und Web-Galerie
├── docs/                 Dokumentation, Drittanbieterhinweise und Übersetzungen dieses README
└── tests/                Mehr als 4000 automatische Tests
```

Lizenziert unter der [MIT-Lizenz](../../LICENSE).
