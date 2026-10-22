# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Aplikacja na pulpit do codziennej pracy z AMD BC-250 w Linuksie. Miałem dość żonglowania tuzinem skryptów i wpisów z forów, więc monitorowanie, governor GPU, strojenie CPU, Compute Units, wentylatory i aktualizacje BIOS-u są teraz w jednym miejscu. Każda zmiana w sprzęcie ma limity i kontrolę przed zastosowaniem, bo ta płyta nie wybacza zgadywania.

Powstała dla społeczności BC-250 i z jej pomocą: większość funkcji zaczęła się od czyjegoś zgłoszenia błędu albo pytania „czy to da się zrobić?” na Discordzie.

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

Nie musisz tu wracać. Gdy pojawi się nowa wersja, panel da ci znać, pokaże listę zmian i zainstaluje ją menedżerem pakietów, po sprawdzeniu SHA-256.

W SteamOS aktualizacja wyłącza ochronę tylko do odczytu, instaluje pakiet i włącza ją z powrotem. Pamiętaj, że systemowa aktualizacja SteamOS kasuje wszystko, co zainstalowano w systemie, tę aplikację też: otwórz **Reinstall BC250 Control Center** z menu trybu pulpitu i ponownie przygotuj zależności. SteamOS pyta o hasło `deck`; jeśli nigdy go nie ustawiono, najpierw uruchom `passwd` w Konsole.

**Przechodzisz z 1.19?** Jej aktualizator nie umie instalować pakietów, przepraszam. Zaktualizuj raz ręcznie pakietem z [najnowszego wydania](https://github.com/movacx/bc250-control-center/releases/latest), a potem aplikacja zadba o siebie sama. W Bazzite zastąp 1.19 jednym krokiem i uruchom ponownie; jeśli użyto install-local.sh, najpierw usuń tamtą kopię:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Pierwsze uruchomienie

1. Otwórz **BC250 Control Center**.
2. Ekran powitalny pyta o język, wygląd i pasek boczny oraz proponuje zainstalować to, czego potrzebuje płyta. Wszystko zmienisz później w **Ustawieniach**.
3. Warto poświęcić minutę na przewodnik. Przechodzi przez każdy moduł i mówi, czego dotyka na płycie.

Zanim cokolwiek zastosujesz, zerknij na linię stanu modułu. Mówi, co jest gotowe, czego brakuje i dlaczego.

## Co potrafi

**Panel i monitorowanie**
- Panel z procesorem, grafiką i chłodzeniem, rdzeniami na żywo, temperaturą każdej kostki GDDR6, liniami zasilania (jeśli zrobiłeś mod I2C) i zainstalowanym BIOS-em.
- Moduł Wydajność z wykresami CPU, GPU, VRAM, RAM, dysku i sieci oraz widokiem Czujniki z minimum, średnią i maksimum.

**Sprzęt**
- **GPU:** bezpieczne zakresy governora dla Cyan i Oberon, laboratorium napięć i punkty powyżej 2000 MHz.
- **CPU / SMU:** strojenie tymczasowe i trwałe, test stabilności i eksperymentalne odblokowanie ukrytych rdzeni.
- **Compute Units:** od 24 do 40 CU, ze stanem bieżącym i startowym pokazanymi osobno.
- **Wentylatory:** ręczne sterowanie PWM, krzywe temperaturowe, profile zachowywane po restarcie i eksport do pliku lub do Decky.
- **Pamięć:** rozmiar VRAM, ZRAM, ZSWAP i plik wymiany.
- **Firmware (BIOS):** przygotowuje USB z aktualizacją P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 lub P2.00, każdy plik sprawdzony.

**System**
- Przygotowanie zależności dopasowane do twojej dystrybucji. Działa we wbudowanym terminalu, więc widzisz każde polecenie.
- Poprawki zgodności: GFX1013 i async compute, FSR4 i HelixSR dla poszczególnych gier, telemetria i ACPI. W Ubuntu i Fedorze ostrzega też, gdy pulpit jest rysowany przez CPU (llvmpipe), bo Mesa jest za stara, a w Ubuntu potrafi to naprawić z PPA kisak.
- Dolby Digital 5.1 przez HDMI dla amplitunerów i soundbarów oraz sterowanie telewizorem przez HDMI-CEC za pomocą cecd od Valve.
- Sterowniki Wi-Fi, Bluetooth i drukarek z oficjalnych repozytoriów twojej dystrybucji.
- Diagnostyka, historia i eksport pomiarów do CSV.

**Interfejs**
- Motywy Jasny, Ciemny i Nocny błękit, style Standardowy i Formalny, 10 kolorów akcentu i skala od 70 % do 150 %.
- 30 języków i nawigacja kontrolerem.

## Decky Quick Access (opcjonalnie)

Panel dla menu szybkiego dostępu w trybie gry, żeby zmieniać codzienne rzeczy (GPU, CU, CPU, wentylatory, VRAM) bez wychodzenia z gry. Zaawansowana konfiguracja zostaje w aplikacji na pulpit.

- **Profile dla gier:** przypisz każdej grze profil GPU i wentylatorów. Stosuje się go przy uruchomieniu gry, a po jej zamknięciu wszystko wraca do poprzedniego stanu.
- **Async compute na żywo:** pokazuje, czy i jak bardzo gra korzysta z obliczeń asynchronicznych.
- **Presety wentylatorów:** z nazwami i prędkościami wyeksportowanymi z pulpitu.

Aby zainstalować, otwórz **Panel**, przewiń do **Decky** i wybierz proponowaną akcję. Jeśli brakuje Decky Loadera, zainstaluje też jego; jeśli jest, zainstaluje lub naprawi tylko BC250 Quick Access. Przygotowanie zależności nigdy samo nie instaluje Decky.

Więcej w [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Zgłaszanie problemów

Okna błędów pokazują kod diagnostyczny (na przykład `BC250-UPSCALE-001`), kod źródłowy wskazujący funkcję, w której wystąpił błąd (na przykład `GPU-0142`), oraz surowy błąd z jego śladem.

Użyj opcji **Zgłoś ten problem** w oknie błędu albo **Ustawienia › Diagnostyka › Wyślij raport**. Formularz otwiera się w aplikacji z wypełnionymi kodami, surowym błędem, specyfikacją systemu i ostatnimi błędami. Przed wysłaniem możesz wszystko sprawdzić; ścieżki katalogu domowego są zastępowane przez `~`. Jeśli formularza nie można wysłać, otworzy się w przeglądarce z zachowanymi odpowiedziami. Formularz jest również dostępny [w sieci](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform).

Raport dołącza także diagnostykę sprzętu, zbieraną bez uprawnień root na każdej dystrybucji: jądro i nagłówki, załadowane moduły czujników oraz ich komunikaty jądra (NCT6687, amdgpu), odczyty hwmon i `sensors`, wpisy dotyczące GPU i awarii z dziennika jądra, sposób zakończenia poprzedniego uruchomienia (prawidłowe wyłączenie lub nagły reset), usługi, pakiety i końcówkę ostatniego dziennika przepływu pracy. Gdy dziennik jądra jest niedostępny dla użytkownika, pulpit jednorazowo poprosi o hasło przez polkit. Raporty zbyt duże dla formularza są automatycznie skracane, zaczynając od najmniej ważnych części; **Otwórz w przeglądarce** nadal kopiuje pełny tekst.

### Black box (zawieszanie i resety)

Twarde zawieszenie nie zostawia nic w dzienniku jądra. Czarna skrzynka cztery razy na sekundę rejestruje zegar i obciążenie GPU, temperatury, napięcie GFX, pobór mocy, prędkość wentylatora, zegar CPU i wolną pamięć, zapisując każdą linię na dysku. Dzięki temu następny raport pokazuje ostatnie sekundy przed zawieszeniem lub resetem. Nie wymaga uprawnień root, a jej plik ma ograniczony rozmiar (512 KB, potem jest rotowany).

```bash
# Tryb pulpitu: pozostaw terminal otwarty podczas gry, zatrzymaj przez Ctrl+C
bc250-control-center-cli black-box

# Tryb gry (SteamOS): uruchom w tle przed przełączeniem
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

Dziennik jest przechowywany w `~/.local/state/bc250-control-center/black-box/`. `bc250-control-center-cli diagnose` wyświetla tę samą diagnostykę sprzętu, którą wysyła raport.

## Bezpieczeństwo

Podkręcanie, odblokowywanie Compute Units, sterowanie wentylatorami i wgrywanie BIOS-u mogą zawiesić komputer, spowodować utratę danych albo zabić płytę. Zmieniaj jedną rzecz naraz, miej drogę powrotu i nie traktuj kontroli aplikacji jako gwarancji. Łapią oczywiste błędy, nie wszystkie.

## Narzędzia zewnętrzne i podziękowania

Nic z tego by nie istniało bez ludzi, którzy zrobili inżynierię wsteczną tej płyty. Poniższe projekty są ich, nie moje, a aplikacja dotyka ich tylko przez procedury, które przeczytałem i przypiąłem do konkretnej wersji.

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
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, demon HDMI-CEC od Valve.

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
└── tests/                Ponad 5000 testów automatycznych, w tym pliki os-release z 37 prawdziwych dystrybucji
```

## Współtworzenie

Najwięcej pomagają zgłoszenia błędów, zwłaszcza z twoją dystrybucją, jądrem i tym, co wypisał terminal. Jeśli używasz dystrybucji, której nie ma na liście wyżej, napisz mi, jak poszło, dobrze czy źle.

Licencja [MIT](../../LICENSE).
