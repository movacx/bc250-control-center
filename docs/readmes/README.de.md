# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Eine Desktop-Anwendung, um die AMD BC-250 unter Linux sinnvoll zu betreiben. Ich hatte es satt, zwischen einem Dutzend Skripten und Forenbeiträgen hin und her zu springen, also stecken Überwachung, GPU-Governor, CPU-Tuning, Compute Units, Lüfter und BIOS jetzt an einem Ort. Jede Änderung an der Hardware hat Grenzen und eine Prüfung, bevor sie angewendet wird, denn diese Platine verzeiht kein Raten.

Sie ist für die BC-250-Community gemacht und mit ihrer Hilfe: Die meisten Funktionen begannen als jemandes Fehlerbericht oder als „Kann es auch X?“ im Discord.

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

Du musst nicht hierher zurückkommen. Gibt es eine neue Version, sagt dir die Übersicht Bescheid, zeigt die Änderungen und installiert sie mit deinem Paketmanager, nachdem sie die SHA-256 geprüft hat.

Unter SteamOS schaltet das Update den Schreibschutz aus, installiert und schaltet ihn wieder ein. Wichtig: Ein SteamOS-Systemupdate löscht alles, was ins System installiert wurde, auch diese Anwendung: Öffnen Sie **Reinstall BC250 Control Center** im Menü des Desktop-Modus und bereiten Sie die Abhängigkeiten erneut vor. SteamOS fragt nach dem Passwort von `deck`; falls Sie nie eines gesetzt haben, führen Sie zuerst `passwd` in Konsole aus.

**Von 1.19 kommend?** Deren Updater kann leider keine Pakete installieren. Aktualisieren Sie einmal von Hand mit dem Paket der [neuesten Version](https://github.com/movacx/bc250-control-center/releases/latest); danach aktualisiert sich die Anwendung selbst. Unter Bazzite ersetzen Sie 1.19 in einem Schritt und starten neu; bei einer Installation mit install-local.sh entfernen Sie zuerst diese Kopie:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Erster Start

1. Öffne **BC250 Control Center**.
2. Der Willkommensbildschirm fragt nach Sprache, Aussehen und Seitenleiste und bietet an, zu installieren, was die Platine braucht. Alles lässt sich später in den **Einstellungen** ändern.
3. Die geführte Tour ist eine Minute wert: Sie geht jedes Modul durch und sagt, was es an der Platine anfasst.

Bevor du etwas anwendest, wirf einen Blick auf die Statuszeile des Moduls. Sie sagt, was bereit ist, was fehlt und warum.

## Funktionen

**Übersicht und Überwachung**
- Eine Übersicht mit Prozessor, Grafik und Kühlung, Kernen live, der Temperatur jedes GDDR6-Chips, den Stromversorgungsschienen (falls du den I2C-Mod gemacht hast) und dem installierten BIOS.
- Leistungsmodul mit Diagrammen für CPU, GPU, VRAM, RAM, Datenträger und Netzwerk sowie einer Sensoransicht mit Minimum, Durchschnitt und Maximum.

**Hardware**
- **GPU:** sichere Governor-Bereiche für Cyan und Oberon, Spannungslabor und Punkte über 2000 MHz.
- **CPU / SMU:** temporäres und dauerhaftes Tuning, Stabilitätstest und experimentelles Freischalten versteckter Kerne.
- **Compute Units:** 24 bis 40 CU, Live- und Startzustand getrennt angezeigt.
- **Lüfter:** manuelle PWM-Steuerung, Temperaturkurven, Profile, die einen Neustart überstehen, und Export in eine Datei oder zu Decky.
- **Speicher:** VRAM-Größe, ZRAM, ZSWAP und Auslagerungsdatei.
- **Firmware (BIOS):** erstellt einen Update-USB-Stick mit P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 oder P2.00, jede Datei geprüft.

**System**
- Einrichtung der Abhängigkeiten, die sich an deine Distribution anpasst. Sie läuft in einem eingebauten Terminal, damit du jeden Befehl siehst.
- Kompatibilitätskorrekturen: GFX1013 und Async Compute, FSR4 pro Spiel, Telemetrie und ACPI. Unter Ubuntu und Fedora warnt sie dich außerdem, wenn dein Desktop wegen eines zu alten Mesa von der CPU gezeichnet wird (llvmpipe), und unter Ubuntu kann sie das über das kisak-PPA beheben.
- Dolby Digital 5.1 über HDMI für Receiver und Soundbars sowie TV-Steuerung über HDMI-CEC mit Valves cecd.
- WLAN-, Bluetooth- und Druckertreiber aus den offiziellen Paketquellen deiner Distribution.
- Diagnose, Verlauf und Export der Messwerte als CSV.

**Oberfläche**
- Themes Hell, Dunkel und Nachtblau, Stile Standard und Förmlich, 10 Akzentfarben und Skalierung von 70 % bis 150 %.
- 30 Sprachen und Controller-Navigation.

## Decky Quick Access (optional)

Ein Panel für das Schnellzugriffsmenü im Spielmodus, damit du die alltäglichen Dinge (GPU, CU, CPU, Lüfter, VRAM) ändern kannst, ohne das Spiel zu verlassen. Die erweiterte Einrichtung bleibt in der Desktop-Anwendung.

- **Profile pro Spiel:** Weise jedem Spiel ein GPU- und Lüfterprofil zu. Es wird beim Start des Spiels angewendet, und beim Beenden kehrt alles zum vorherigen Zustand zurück.
- **Async Compute live:** zeigt, ob und wie stark das Spiel asynchrones Rechnen nutzt.
- **Lüfter-Presets:** mit den Namen und Drehzahlen, die du vom Desktop exportierst.

Zum Installieren öffne die **Übersicht**, scrolle zu **Decky** und wähle die angebotene Aktion. Fehlt Decky Loader, wird er mit installiert; ist er schon da, wird nur BC250 Quick Access installiert oder repariert. Das Vorbereiten der Abhängigkeiten installiert Decky nie von selbst.

Mehr dazu im [Decky-README](../../integrations/decky/bc250-quick-access/README.md).

## Probleme melden

Fehlerfenster zeigen einen Diagnosecode (zum Beispiel `BC250-UPSCALE-001`), einen Herkunftscode, der die Funktion des Fehlers angibt (zum Beispiel `GPU-0142`), sowie den Rohfehler mit Traceback.

Verwende **Dieses Problem melden** im Fehlerfenster oder **Einstellungen › Diagnose › Bericht senden**. Das Formular öffnet sich in der Anwendung und enthält bereits die Codes, den Rohfehler, Systemspezifikationen und die letzten Fehler. Du kannst alles vor dem Senden prüfen; Pfade im Home-Verzeichnis werden durch `~` ersetzt. Kann das Formular nicht gesendet werden, öffnet es sich mit deinen Antworten im Browser. Das Formular ist auch [im Web](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform) verfügbar.

Der Bericht enthält außerdem eine Hardwarediagnose, die auf jeder Distribution ohne root gesammelt wird: Kernel und Header, geladene Sensormodule und ihre Kernelmeldungen (NCT6687, amdgpu), hwmon- und `sensors`-Messwerte, GPU- und Absturzzeilen aus dem Kernelprotokoll, das Ende des vorherigen Starts (sauberes Herunterfahren oder abrupter Reset), Dienste, Pakete und das Ende des letzten Workflow-Protokolls. Ist das Kernelprotokoll für deinen Benutzer gesperrt, fragt der Desktop einmal über polkit nach dem Passwort. Zu große Berichte werden automatisch gekürzt, beginnend mit den unwichtigsten Teilen; **Im Browser öffnen** kopiert weiterhin den vollständigen Text.

### Black box (Einfrieren und Resets)

Bei einem harten Freeze bleibt nichts im Kernelprotokoll. Die Black Box zeichnet GPU-Takt, Auslastung, Temperaturen, GFX-Spannung, Leistung, Lüfterdrehzahl, CPU-Takt und freien Speicher viermal pro Sekunde auf und schreibt jede Zeile sofort auf die Festplatte. Dadurch zeigt der nächste Bericht die letzten Sekunden vor einem Freeze oder Reset. Sie benötigt kein root, und ihre Datei ist begrenzt (512 KB, danach Rotation).

```bash
# Desktop-Modus: Lass das Terminal beim Spielen geöffnet, beende mit Ctrl+C
bc250-control-center-cli black-box

# Spielmodus (SteamOS): Starte sie vor dem Wechsel im Hintergrund
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

Das Protokoll wird in `~/.local/state/bc250-control-center/black-box/` gespeichert. `bc250-control-center-cli diagnose` gibt dieselbe Hardwarediagnose aus, die der Bericht sendet.

## Sicherheit

Übertakten, das Freischalten von Compute Units, Lüftersteuerung und das Flashen eines BIOS können die Maschine einfrieren, Daten kosten oder die Platine töten. Ändere immer nur eine Sache, halte einen Weg zurück bereit und verstehe die Prüfungen der Anwendung nicht als Garantie. Sie fangen die offensichtlichen Fehler ab, nicht alle.

## Externe Werkzeuge und Danksagungen

Ohne die Leute, die die Platine per Reverse Engineering erschlossen haben, gäbe es nichts davon. Die Projekte unten gehören ihnen, nicht mir, und die Anwendung berührt sie nur über Abläufe, die ich gelesen und auf eine Revision festgelegt habe.

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
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, Valves HDMI-CEC-Dienst.

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
└── tests/                Über 5000 automatische Tests, mit os-release-Dateien von 37 echten Distributionen
```

## Mitmachen

Am meisten hilft mir ein Fehlerbericht, vor allem mit deiner Distribution, dem Kernel und dem, was das Terminal ausgegeben hat. Wenn du eine Distribution nutzt, die oben nicht aufgeführt ist, erzähl mir, wie es lief, egal ob gut oder schlecht.

Lizenziert unter der [MIT-Lizenz](../../LICENSE).
