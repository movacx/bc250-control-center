# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centrum sterowania dla AMD BC-250 w Linuksie. Monitorowanie, sterowanie GPU, strojenie CPU, Compute Units, wentylatory i aktualizacja BIOS-u w jednej aplikacji na pulpit – z jasnymi ograniczeniami i kontrolą przed każdą zmianą sprzętu.

## Zrzuty ekranu

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Panel BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Zobacz wszystkie zrzuty →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Instalacja

### Arch, CachyOS i SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Pakiety wydań

Pobierz pakiet dla swojego systemu z [najnowszego wydania](https://github.com/movacx/bc250-control-center/releases/latest):

| System | Plik |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<wersja>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<wersja>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<wersja>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: ten sam RPM, potem uruchom ponownie w nowym wdrożeniu
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

W Debianie i Ubuntu używaj `apt install`, a nie `dpkg -i`: wtedy APT pobierze też zależności. Jeśli `dpkg -i` zostawił pakiet w połowie instalacji, naprawi to `sudo apt --fix-broken install`.

### Aktualizacje

Nie trzeba wracać na tę stronę. Gdy pojawi się nowa wersja, panel o tym powie, pokaże zmiany i zainstaluje ją menedżerem pakietów twojego systemu, najpierw sprawdzając SHA-256.

W SteamOS aktualizacja wyłącza ochronę tylko do odczytu, instaluje pakiet i włącza ją ponownie. Aktualizacja SteamOS usuwa wszystko, co zainstalowano w systemie, również tę aplikację: otwórz **Reinstall BC250 Control Center** z menu trybu pulpitu i ponownie przygotuj zależności. SteamOS pyta o hasło `deck`; jeśli nigdy go nie ustawiono, najpierw uruchom `passwd` w Konsole.

**Przechodzisz z 1.19?** Jej wbudowany aktualizator nie instaluje pakietów. Zaktualizuj raz ręcznie pakietem z [najnowszego wydania](https://github.com/movacx/bc250-control-center/releases/latest); potem aplikacja aktualizuje się sama. W Bazzite zastąp 1.19 jednym krokiem i uruchom ponownie; jeśli użyto install-local.sh, najpierw usuń tamtą kopię:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Pierwsze uruchomienie

1. Otwórz **BC250 Control Center**.
2. Ekran powitalny zapyta o język, wygląd i pasek boczny oraz zaproponuje instalację narzędzi potrzebnych płycie. Wszystko można później zmienić w **Ustawieniach**.
3. Jeśli chcesz, przejdź przewodnik: odwiedza każdy moduł i wyjaśnia, co każdy z nich zmienia na płycie.

Przed każdą zmianą sprawdź stan modułu: mówi, co jest gotowe, czego brakuje i dlaczego.

## Co potrafi

**Panel i monitorowanie**
- Panel z procesorem, grafiką i chłodzeniem, rdzeniami na żywo, temperaturą każdego układu GDDR6, liniami zasilania (z modem I2C) i zainstalowanym BIOS-em.
- Moduł Wydajność z wykresami CPU, GPU, VRAM, RAM, dysku i sieci oraz widokiem Czujniki z minimum, średnią i maksimum.

**Sprzęt**
- **GPU:** bezpieczne zakresy governora dla Cyan i Oberon, laboratorium napięć i punkty powyżej 2000 MHz.
- **CPU / SMU:** strojenie tymczasowe i trwałe, test stabilności i eksperymentalne odblokowanie ukrytych rdzeni.
- **Compute Units:** od 24 do 40 CU, ze stanem bieżącym i startowym pokazanymi osobno.
- **Wentylatory:** ręczne sterowanie PWM, krzywe temperaturowe, profile zachowywane po restarcie i eksport do pliku lub do Decky.
- **Pamięć:** rozmiar VRAM, ZRAM, ZSWAP i plik wymiany.
- **Firmware (BIOS):** przygotowuje USB z aktualizacją P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 lub P2.00, każdy plik sprawdzony.

**System**
- Przygotowanie zależności dopasowane do każdej dystrybucji, z wbudowanym terminalem pokazującym każde polecenie.
- Poprawki zgodności: GFX1013 i async compute, FSR4 dla poszczególnych gier, telemetria i ACPI.
- Sterowniki Wi-Fi, Bluetooth i drukarek z oficjalnych repozytoriów twojej dystrybucji.
- Diagnostyka, historia i eksport pomiarów do CSV.

**Interfejs**
- Motywy Jasny, Ciemny i Nocny błękit, style Standardowy i Formalny, 10 kolorów akcentu i skala od 70 % do 150 %.
- 30 języków i nawigacja kontrolerem.

## Decky Quick Access (opcjonalnie)

Panel dla menu szybkiego dostępu SteamOS i trybu gry Steam. Daje codzienne ustawienia (GPU, CU, CPU, wentylatory i VRAM) bez wychodzenia z gry; zaawansowana konfiguracja zostaje w aplikacji na pulpit.

- **Profile dla gier:** przypisz każdej grze profil GPU i wentylatorów. Stosuje się go przy uruchomieniu gry, a po jej zamknięciu wszystko wraca do poprzedniego stanu.
- **Async compute na żywo:** pokazuje, czy i jak bardzo gra korzysta z obliczeń asynchronicznych.
- **Presety wentylatorów:** z nazwami i prędkościami wyeksportowanymi z pulpitu.

Aby zainstalować, otwórz **Panel**, przewiń do sekcji **Decky** i wybierz proponowaną akcję. Jeśli brakuje Decky Loadera, aplikacja go zainstaluje; jeśli już jest, zainstaluje lub naprawi tylko BC250 Quick Access. Zwykłe przygotowanie zależności nigdy samo nie instaluje Decky.

Więcej w [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Bezpieczeństwo

Podkręcanie, zmiany Compute Units, sterowanie wentylatorami i aktualizacja BIOS-u mogą zawiesić lub wyłączyć system, spowodować utratę danych albo uszkodzić sprzęt. Wprowadzaj jedną zmianę naraz, zawsze miej drogę powrotu i nie traktuj kontroli aplikacji jako gwarancji dla sprzętu.

## Narzędzia zewnętrzne i podziękowania

BC250 Control Center opiera się na pracy społeczności i nie przypisuje sobie żadnego z tych projektów. Każde narzędzie jest używane wyłącznie przez jawne, sprawdzone procedury.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): obsługiwany alternatywny governor.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) i [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): jądro i Mesa/RADV dla GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): dopasowane jądro i Mesa/RADV dla Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute w Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) i [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 dla poszczególnych gier.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): rekonstrukcja DLSS Model E dla gier z FSR 3.1, dla poszczególnych gier.

**CPU i Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): wykrywanie i strojenie CPU przez SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) i [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): odblokowanie rdzeni.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) i [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): stany wydajności CPU przez ACPI.

**Czujniki, pamięć i wentylatory**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): telemetria regulatorów napięcia (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): temperatura pamięci GDDR6.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): rozmiar VRAM przez CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): czujniki NCT i PWM wentylatorów.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): fabryczny BIOS P3.00 i Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell i MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): kopia zestawu aktualizacji ASRock (P2.00 i P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): własne logo startowe.

Licencje, stan weryfikacji i dokładny zakres każdej integracji opisują [informacje o komponentach zewnętrznych](../THIRD_PARTY_NOTICES.md).

## Struktura projektu

```text
bc250-control-center/
├── src/bc250cc/          Rdzeń, bez interfejsu graficznego
│   ├── domain/           Reguły i ograniczenia każdego modułu (GPU, CPU, CU, wentylatory, firmware…)
│   ├── application/      Przypadki użycia łączące te reguły
│   ├── infrastructure/   Dostęp do systemu: czujniki, usługi, pakiety, GitHub
│   ├── platform/         Różnice między dystrybucjami i systemami init
│   └── shared/           Wersja, ścieżki i kontrakty wspólne dla wszystkich procesów
├── frontends/
│   ├── desktop/          Aplikacja na pulpit w Qt
│   │   ├── pages/        Jeden plik na moduł (panel, GPU, CPU, wentylatory, firmware…)
│   │   ├── components/   Elementy interfejsu wielokrotnego użytku
│   │   ├── onboarding/   Ekran powitalny i przewodnik
│   │   ├── console/      Wbudowany terminal
│   │   ├── theme/        Motywy, style, kolory i ikony
│   │   └── i18n/         Tłumaczenia na 30 języków
│   └── cli.py            Tryb wiersza poleceń
├── integrations/decky/   Wtyczka Decky Quick Access dla trybu gry
├── privileged/           To, co działa jako root, odizolowane i sprawdzone
│   ├── helpers/          Jeden pomocnik na każde uprzywilejowane zadanie
│   ├── lib/              Kod wspólny dla tych pomocników
│   └── policies/         Uprawnienia Polkit
├── packaging/            Pakiety .pkg.tar.zst, .rpm i .deb oraz PKGBUILD dla AUR
├── scripts/              Programy uruchamiające, lokalny instalator i narzędzia systemowe
├── assets/               Ikony, zrzuty ekranu i galeria WWW
├── docs/                 Dokumentacja, informacje o komponentach zewnętrznych i tłumaczenia tego README
└── tests/                Ponad 4000 testów automatycznych
```

Licencja [MIT](../../LICENSE).
