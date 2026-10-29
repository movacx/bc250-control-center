# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

<a href="https://ko-fi.com/movacx"><img src="https://img.shields.io/badge/Ko--fi-Wesprzyj-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Wesprzyj · Ko-fi"></a>

Aplikacja desktopowa do konfigurowania, strojenia i monitorowania AMD BC-250 w Linuksie.

Obejmuje governor GPU, strojenie CPU, Compute Units (CU), wentylatory, pamięć, aktualizację BIOS-u, upscaling oraz przygotowanie systemu dla obsługiwanych dystrybucji. Każda zmiana sprzętowa jest sprawdzana względem swoich limitów i potwierdzana przed zastosowaniem. Opcjonalna wtyczka Decky przenosi codzienne ustawienia do Trybu Gry Steam.

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="../../assets/screenshots/dashboard-overview.png" alt="Pulpit BC250 Control Center" width="100%"></a>
</p>

Więcej zrzutów ekranu znajdziesz w [galerii](https://movacx.github.io/bc250-control-center/gallery/).

## Funkcje

- Pulpit z CPU, GPU, chłodzeniem, obciążeniem każdego rdzenia, temperaturą GDDR6 dla każdego układu, zainstalowanym BIOS-em i szynami zasilania (szyny wymagają modyfikacji sprzętowej I2C; aplikacja zawiera przewodnik ze zdjęciami)
- Wykresy wydajności CPU, GPU, VRAM, RAM, dysku i sieci, z widokiem czujników i eksportem do CSV
- Zarządzanie governorem GPU (Cyan, z Oberon jako alternatywą), bezpieczne zakresy częstotliwości i laboratorium napięć
- Strojenie CPU przez SMU, test stabilności i opcjonalne odblokowanie rdzeni
- Compute Units: od 24 do 40 CU, z osobno pokazanym stanem bieżącym i stanem po starcie
- Sterowanie wentylatorami: ręczny PWM, krzywe temperaturowe, trwałe profile lub przekazanie do CoolerControl, fancontrol albo fan2go
- Pamięć: rozmiar VRAM, ZRAM, ZSWAP i swap
- Tworzenie nośnika USB do aktualizacji BIOS-u (P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00, P2.00), z weryfikacją każdego pliku
- Upscaling dla poszczególnych gier: FSR4 INT8 przez OptiScaler Client i HelixSR, z kopią zapasową i przywracaniem plików gry
- Przygotowanie systemu dostosowane do dystrybucji, uruchamiane w zintegrowanym terminalu
- Poprawki zgodności dla GFX1013, async compute, ACPI i Mesa; Dolby Digital 5.1 przez HDMI; sterowanie telewizorem przez HDMI-CEC
- Zgłoszenia problemów w aplikacji, z kodami błędów, kodami pochodzenia i surowym błędem w załączniku
- 30 języków, jasny i ciemny motyw, skalowanie interfejsu i nawigacja padem

## Obsługiwane dystrybucje

- Arch Linux, CachyOS, Manjaro
- Fedora, Nobara
- Bazzite i inne warianty Fedora Atomic
- SteamOS (beta)
- Ubuntu, Linux Mint, Debian 13

Wymagany jest Python 3.11 lub nowszy. Inne dystrybucje, w tym systemy z OpenRC, są wykrywane i obsługiwane w miarę możliwości, ale nie są testowane przy każdym wydaniu.

## Instalacja

### AUR

Dla Arch Linux, CachyOS i SteamOS:

```bash
yay -S bc250-control-center-git
```

### Pakiety wydań

Pobierz pakiet dla swojej dystrybucji z [najnowszego wydania](https://github.com/movacx/bc250-control-center/releases/latest).

Arch Linux, CachyOS, Manjaro:

```bash
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
```

Fedora, Nobara:

```bash
sudo dnf install ./bc250-control-center-*.rpm
```

Bazzite i Fedora Atomic (wymagany restart):

```bash
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot
```

Ubuntu, Linux Mint, Debian:

```bash
sudo apt install ./bc250-control-center_*.deb
```

Używaj `apt install` zamiast `dpkg -i`, aby zależności zostały zainstalowane. Jeśli pakiet został w połowie zainstalowany przez `dpkg -i`, uruchom `sudo apt --fix-broken install`.

### SteamOS

SteamOS utrzymuje partycję systemową w trybie tylko do odczytu, dlatego pakiet można zainstalować tylko przy wyłączonej tej ochronie. Otwórz Konsole w Trybie Pulpitu i uruchom:

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
sudo pacman -Syy
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
sudo steamos-readonly enable
```

Linie `pacman-key` i `pacman -Syy` odświeżają klucze i bazy pakietów, które aktualizacja SteamOS resetuje. Jeśli nie ustawiono jeszcze hasła dla użytkownika `deck`, najpierw uruchom `passwd`. Po aktualizacji SteamOS wpis **Reinstall BC250 Control Center** w menu Trybu Pulpitu wykona te kroki za Ciebie.

### Ze źródeł

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center
./run.sh                          # uruchom z katalogu repozytorium
bash scripts/install-local.sh     # albo zainstaluj dla bieżącego użytkownika
```

## Aktualizacje

Aplikacja sprawdza nowe wydania, pokazuje listę zmian, weryfikuje sumę kontrolną pakietu i instaluje aktualizację przez menedżera pakietów systemu.

**SteamOS:** aktualizacja systemu SteamOS usuwa pakiety zainstalowane w systemie, w tym tę aplikację. Po aktualizacji systemu uruchom **Reinstall BC250 Control Center** z menu Trybu Pulpitu, a następnie ponownie uruchom Prepare BC250 system. SteamOS pyta o hasło użytkownika `deck`; jeśli go nie masz, ustaw je poleceniem `passwd`.

**Aktualizacja z 1.19:** aktualizator wersji 1.19 nie potrafi instalować pakietów. Zainstaluj aktualną wersję raz ręcznie; kolejne wersje będą aktualizować się same.

```bash
# Bazzite / Fedora Atomic: zastąp nałożony pakiet 1.19
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# Kopia zainstalowana przez install-local.sh: usuń ją, a potem zainstaluj pakiet
bash scripts/uninstall-local.sh
```

## Pierwsze kroki

1. Uruchom BC250 Control Center. Ekran pierwszego uruchomienia ustawia język i wygląd oraz proponuje zainstalowanie wymaganych komponentów.
2. Opcjonalnie przejdź przewodnik, który wyjaśnia, co każdy moduł zmienia na płycie.
3. Na pulpicie uruchom **Prepare BC250 system**. Pokaże, co zostanie zainstalowane dla Twojej dystrybucji, i wykona to w zintegrowanym terminalu.
4. Przed zastosowaniem zmian przeczytaj linię stanu modułu; informuje, co jest gotowe, a czego brakuje.

## Wtyczka Decky

BC250 Quick Access to opcjonalny panel w menu szybkiego dostępu Trybu Gry Steam. Zapewnia sterowanie GPU, Compute Units, CPU, wentylatorami i VRAM, profile GPU i wentylatorów dla poszczególnych gier oraz odczyty async compute na żywo. Zaawansowana konfiguracja pozostaje w aplikacji desktopowej.

Zainstaluj ją z sekcji **Decky** na pulpicie. Decky Loader zostanie zainstalowany, jeśli go brakuje; żadna inna część aplikacji nie instaluje Decky. Szczegóły znajdziesz w [README wtyczki](../../integrations/decky/bc250-quick-access/README.md).

## Zgłaszanie problemów

Okna błędów pokazują kod diagnostyczny (na przykład `BC250-UPSCALE-001`), kod pochodzenia wskazujący funkcję, w której wystąpił błąd (na przykład `GPU-0142`), oraz surowy błąd wraz ze śladem stosu.

Użyj **Zgłoś ten problem** w oknie błędu lub **Ustawienia › Diagnostyka › Wyślij raport**. Formularz otwiera się w aplikacji z już wypełnionymi kodami, surowym błędem, danymi systemu i ostatnimi błędami. Możesz wszystko przejrzeć przed wysłaniem; ścieżki do katalogu domowego są zamieniane na `~`. Jeśli formularza nie da się wysłać, otworzy się w przeglądarce z zachowanymi odpowiedziami. Formularz jest też [dostępny w sieci](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform).

Raport dołącza również diagnostykę sprzętu, zbieraną bez roota na każdej dystrybucji: jądro i nagłówki, załadowane moduły czujników i ich komunikaty z jądra (NCT6687, amdgpu), odczyty hwmon i `sensors`, wiersze GPU i awarii z logu jądra, sposób zakończenia poprzedniego uruchomienia (czyste wyłączenie lub nagły reset), usługi, pakiety oraz koniec ostatniego logu przepływu pracy. Gdy log jądra jest niedostępny dla Twojego użytkownika, pulpit raz zapyta o hasło przez polkit. Raporty zbyt duże dla formularza są automatycznie skracane, zaczynając od najmniej ważnych części; **Otwórz w przeglądarce** nadal kopiuje pełny tekst.

### Czarna skrzynka (zawieszenia i resety)

Twarde zawieszenie nie zostawia nic w logu jądra. Czarna skrzynka zapisuje cztery razy na sekundę zegar i obciążenie GPU, temperatury, napięcie GFX, moc, prędkość wentylatora, zegar CPU i wolną pamięć, zapisując każdą linię na dysk. Dzięki temu następny raport pokazuje ostatnie sekundy pracy płyty przed zawieszeniem lub resetem. Nie wymaga roota, a jej plik ma ograniczony rozmiar (512 KB, potem rotacja).

```bash
# Tryb pulpitu: zostaw terminal otwarty podczas gry, zatrzymaj Ctrl+C
bc250-control-center-cli black-box

# Tryb gry (SteamOS): uruchom w tle przed przełączeniem
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

Log znajduje się w `~/.local/state/bc250-control-center/black-box/`. `bc250-control-center-cli diagnose` wypisuje tę samą diagnostykę sprzętu, którą wysyła raport.

Terminal nie jest potrzebny: otwórz **Czarną skrzynkę** na pasku bocznym (nad Firmware (BIOS)), aby uruchamiać i zatrzymywać nagrywanie, zobaczyć w tabeli ostatnio zapisane wiersze i włączyć *Uruchamiaj z sesją*, by działała przy każdym logowaniu (tylko systemd). Nagranie przerwane restartem lub zawieszeniem jest tam oznaczone.

Aby przeczytać wszystko, co raport dołącza, przed wysłaniem, otwórz **Ustawienia › Diagnostyka › Pokaż pełną diagnostykę**: każda sekcja (jądro, poprzedni rozruch, czarna skrzynka, czujniki, GPU, usługi, konfiguracja, pakiety, logi) rozwija się, jest podzielona na karty, można ją przeszukać, skopiować lub zapisać do pliku. Terminal wypisuje to samo poleceniem `bc250-control-center-cli diagnose --full`.

Zgłoszenia na GitHubie są również mile widziane. Podaj swoją dystrybucję, wersję jądra i wynik terminala.

## Bezpieczeństwo

Overclocking, odblokowywanie Compute Units, zmiana sterowania wentylatorami i flashowanie BIOS-u mogą spowodować niestabilność systemu, utratę danych lub uszkodzenie płyty. Zmieniaj jedno ustawienie naraz i miej sposób na cofnięcie zmiany. Sprawdzenia aplikacji wychwytują typowe błędy, ale nie dają gwarancji.

## Podziękowania

Ten projekt opiera się na pracy społeczności BC-250. Poniższe projekty należą do ich autorów; aplikacja integruje je przez sprawdzone, przypięte do wersji przepływy. Licencje i zakres każdej integracji są opisane w [uwagach o komponentach firm trzecich](../THIRD_PARTY_NOTICES.md).

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor GPU
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): alternatywny governor
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) i [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): kernel i Mesa/RADV dla GFX1013
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): kernel i Mesa/RADV dla Arch i CachyOS
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute na Bazzite 44, z poprawkami RADV budowanymi również dla Arch, CachyOS i Fedory z jądrem 7.2 lub nowszym

**Upscaling**
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) i [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork): OptiScaler Client, FSR4 dla każdej gry
- [HelixSR](https://github.com/lonewolf0622/HelixSR): rekonstrukcja DLSS Model E w grach z FSR 3.1

**CPU i Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): wykrywanie i strojenie CPU przez SMU
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) i [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): odblokowywanie rdzeni
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): stany wydajności CPU przez ACPI
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) i [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units

**Czujniki, pamięć i wentylatory**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): telemetria regulatorów napięcia (VRM) i zdjęcia z przewodnika I2C
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): temperatura GDDR6
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): rozmiar VRAM przez CMOS
- [nct6687d](https://github.com/Fred78290/nct6687d): czujniki NCT i PWM wentylatorów
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, demon HDMI-CEC firmy Valve

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): oryginalny BIOS P3.00 i Chipset Menu
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell i MeiMeiDXE v3
- [BC-250](https://github.com/kenavru/BC-250): lustro zestawu aktualizacyjnego ASRock (P2.00 i P5.00)
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): niestandardowe logo startowe

**Powiązane projekty** (aplikacja ich nie używa; licencje wg GitHuba)
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) i [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0): temperatury VRM i pamięci jako moduły jądra
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0): zestaw konfiguracyjny dla Bazzite
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) i [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm): badania nad kodowaniem wideo VCN i otwarty sterownik dla Windows (brak zadeklarowanej licencji; tylko linki)

## Struktura projektu

```text
bc250-control-center/
├── src/bc250cc/              Rdzeń, bez interfejsu graficznego
│   ├── domain/               Reguły i limity każdego modułu (GPU, CPU, CU, wentylatory, firmware…)
│   ├── application/          Przypadki użycia łączące te reguły
│   ├── infrastructure/       Dostęp do systemu: czujniki, usługi, pakiety, GitHub
│   ├── platform/             Różnice między dystrybucjami i systemami rozruchu
│   └── shared/               Wersja, ścieżki i kontrakty wspólne dla wszystkich procesów
├── frontends/
│   ├── desktop/              Aplikacja desktopowa w Qt
│   │   ├── pages/            Jeden plik na moduł (pulpit, GPU, CPU, wentylatory, firmware…)
│   │   ├── components/       Wielokrotnego użytku elementy interfejsu
│   │   ├── onboarding/       Ekran powitalny i przewodnik
│   │   ├── console/          Zintegrowany terminal
│   │   ├── theme/            Motywy, style, kolory i ikony
│   │   └── i18n/             Tłumaczenia na 30 języków
│   └── cli.py                Tryb wiersza poleceń
├── integrations/decky/       Wtyczka Decky Quick Access dla Trybu Gry
├── privileged/               To, co działa jako root: odizolowane i sprawdzone
│   ├── helpers/              Jeden pomocnik na zadanie uprzywilejowane
│   ├── lib/                  Kod wspólny dla tych pomocników
│   └── policies/             Uprawnienia Polkit
├── packaging/                Pakiety .pkg.tar.zst, .rpm i .deb oraz PKGBUILD dla AUR
├── scripts/                  Skrypty uruchamiające, lokalny instalator i narzędzia systemowe
├── assets/                   Ikony, zrzuty ekranu i galeria internetowa
├── docs/                     Dokumentacja, uwagi o komponentach firm trzecich i tłumaczenia tego README
└── tests/                    Ponad 5000 testów automatycznych, z plikami os-release 37 prawdziwych dystrybucji
```

## Współtworzenie

Najbardziej przydatne jest zgłoszenie błędu, zwłaszcza z informacją o dystrybucji, wersji jądra i tym, co pokazał terminal. Jeśli używasz dystrybucji, której nie ma powyżej, napisz, jak się sprawdziła, dobrze czy źle.

Licencja [MIT](../../LICENSE).
