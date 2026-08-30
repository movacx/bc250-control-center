# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centrum sterowania Linux dla AMD BC-250: monitoring, obsługa GPU, strojenie CPU, Compute Units i wentylatorów w jednej aplikacji desktopowej.

## Zrzuty ekranu

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Panel BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Instalacja

```bash
# Ze źródeł
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS i Manjaro
yay -S bc250-control-center-git
```

Aby usunąć lokalną instalację, uruchom `./uninstall-local.sh` w tym samym katalogu.

Pakiety są dostępne w [najnowszym wydaniu](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara i Bazzite używają tego samego RPM `noarch`:

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # po rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Pierwsze uruchomienie

1. Otwórz `bc250-control-center`.
2. W Dashboard wybierz **Prepare dependencies**.
3. Sprawdź stan modułu przed zastosowaniem zmiany.

## Funkcje

- Dane na żywo CPU, GPU, pamięci, dysków, sieci, temperatur i wentylatorów.
- GPU governor, strojenie CPU i eksperymentalne odblokowanie rdzeni.
- Sterowanie 24–40 Compute Units, PWM i krzywymi wentylatorów.
- Diagnostyka, historia, eksport CSV, skalowanie interfejsu i obsługa kontrolera.

## Opcjonalny Decky Quick Access

W SteamOS/Game Mode panel instaluje się z sekcji **Decky** na dole Dashboard. Aplikacja instaluje Decky Loader, gdy go brakuje, albo instaluje/naprawia tylko BC250 Quick Access. Zobacz [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Bezpieczeństwo

Podkręcanie, zmiany Compute Units i sterowanie wentylatorami mogą powodować zawieszenia, wyłączenia, utratę danych lub uszkodzenie sprzętu. Wprowadzaj jedną zmianę naraz, zachowaj drogę odzyskiwania i nie traktuj kontroli programowych jako walidacji sprzętu.

## Autorzy i licencje

Projekt korzysta z pracy społeczności przez jawne, sprawdzone procesy. [Informacje o komponentach zewnętrznych](../THIRD_PARTY_NOTICES.md) opisują licencje, stan weryfikacji i granice integracji.

## Języki

Interfejs desktopowy obsługuje 30 języków, może używać języka systemu lub zostać zmieniony w Settings. Obejmuje angielski, hiszpański, portugalski, rosyjski, ukraiński, niemiecki, francuski, polski, chiński, japoński, koreański i inne.

## Struktura projektu

```text
src/bc250cc/   logika aplikacji i systemu
frontends/     adaptery Desktop Qt, CLI i Quick Access
privileged/    chronione helpery i polityka Polkit
packaging/     metadane pakietów i konfiguracja dystrybucji
scripts/       programy uruchamiające i lokalny instalator
```

Licencja [MIT](../../LICENSE).
