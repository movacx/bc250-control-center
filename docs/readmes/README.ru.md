# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Центр управления AMD BC-250 для Linux. Мониторинг, управление GPU, настройка CPU, Compute Units, вентиляторы и обновление BIOS в одном настольном приложении — с понятными ограничениями и проверками перед каждым изменением оборудования.

## Снимки экрана

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Панель BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Все снимки экрана →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Установка

### Arch, CachyOS и SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Пакеты выпусков

Скачайте пакет для своей системы из [последнего выпуска](https://github.com/movacx/bc250-control-center/releases/latest):

| Система | Файл |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<версия>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<версия>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<версия>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: тот же RPM, затем перезагрузка в новое развёртывание
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

В Debian и Ubuntu используйте `apt install`, а не `dpkg -i`: так APT скачает и зависимости. Если после `dpkg -i` пакет остался недоустановленным, это исправит `sudo apt --fix-broken install`.

### Обновления

Возвращаться на эту страницу не нужно. Когда выходит новая версия, панель сообщает об этом, показывает, что изменилось, и устанавливает её менеджером пакетов вашей системы, предварительно проверив SHA-256.

В SteamOS обновление отключает защиту только для чтения, устанавливает пакет и снова её включает. Обновление SteamOS удаляет всё, что было установлено в систему, включая это приложение: откройте **Reinstall BC250 Control Center** в меню режима рабочего стола и снова подготовьте зависимости. SteamOS запрашивает пароль `deck`; если вы его не задавали, сначала выполните `passwd` в Konsole.

**Переходите с 1.19?** Её встроенный механизм обновления не умеет устанавливать пакеты. Обновитесь один раз вручную пакетом из [последнего выпуска](https://github.com/movacx/bc250-control-center/releases/latest); дальше приложение обновляется само. В Bazzite замените 1.19 за один шаг и перезагрузитесь; если ставили через install-local.sh, сначала удалите ту копию:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Первый запуск

1. Откройте **BC250 Control Center**.
2. Экран приветствия спросит язык, оформление и вид боковой панели и предложит установить инструменты, нужные плате. Всё это можно изменить позже в **Настройках**.
3. При желании пройдите обзор: он проведёт по каждому модулю и объяснит, что каждый из них меняет на плате.

Перед любым изменением проверьте состояние модуля: он сообщает, что готово, чего не хватает и почему.

## Возможности

**Панель и мониторинг**
- Панель с процессором, графикой и охлаждением, ядрами в реальном времени, температурой каждого чипа GDDR6, линиями питания (с модом I2C) и установленным BIOS.
- Модуль «Производительность» с графиками CPU, GPU, VRAM, RAM, диска и сети и представлением «Датчики» с минимумом, средним и максимумом.

**Оборудование**
- **GPU:** безопасные диапазоны governor для Cyan и Oberon, лаборатория напряжений и точки выше 2000 МГц.
- **CPU / SMU:** временная и постоянная настройка, тест стабильности и экспериментальная разблокировка скрытых ядер.
- **Compute Units:** от 24 до 40 CU, текущее состояние и состояние при загрузке показываются отдельно.
- **Вентиляторы:** ручное управление PWM, кривые по температуре, профили, сохраняющиеся после перезагрузки, и экспорт в файл или в Decky.
- **Память:** размер VRAM, ZRAM, ZSWAP и файл подкачки.
- **Прошивка (BIOS):** готовит USB для обновления с P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 или P2.00, каждый файл проверяется.

**Система**
- Подготовка зависимостей для каждого дистрибутива со встроенным терминалом, где видна каждая команда.
- Исправления совместимости: GFX1013 и async compute, FSR4 для отдельных игр, телеметрия и ACPI.
- Драйверы Wi-Fi, Bluetooth и принтеров из официальных репозиториев вашего дистрибутива.
- Диагностика, история и экспорт метрик в CSV.

**Интерфейс**
- Темы «Светлая», «Тёмная» и «Ночной синий», стили «Стандартный» и «Строгий», 10 акцентных цветов и масштаб от 70 % до 150 %.
- 30 языков и управление геймпадом.

## Decky Quick Access (дополнительно)

Панель для меню быстрого доступа SteamOS и игрового режима Steam. Повседневные настройки (GPU, CU, CPU, вентиляторы и VRAM) доступны прямо из игры; расширенная настройка остаётся в настольном приложении.

- **Профили для игр:** назначьте каждой игре профиль GPU и вентиляторов. Он применяется при запуске игры, а после её закрытия всё возвращается как было.
- **Async compute в реальном времени:** показывает, использует ли игра асинхронные вычисления и насколько.
- **Пресеты вентиляторов:** с названиями и скоростями, экспортированными из настольного приложения.

Чтобы установить, откройте **Панель**, прокрутите до раздела **Decky** и выберите предложенное действие. Если Decky Loader отсутствует, приложение установит его; если он уже есть — установит или восстановит только BC250 Quick Access. Обычная подготовка зависимостей никогда не устанавливает Decky сама.

Подробнее в [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Безопасность

Разгон, изменение Compute Units, управление вентиляторами и обновление BIOS могут привести к зависанию или выключению системы, потере данных или повреждению оборудования. Применяйте изменения по одному, всегда держите путь назад и не считайте проверки приложения гарантией для оборудования.

## Внешние инструменты и благодарности

BC250 Control Center опирается на работу сообщества и не присваивает ни один из этих проектов. Каждый инструмент используется только через явные, проверенные сценарии.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): поддерживаемый альтернативный governor.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) и [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): ядро и Mesa/RADV для GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): согласованные ядро и Mesa/RADV для Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute в Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) и [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 для отдельных игр.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): реконструкция DLSS Model E для игр с FSR 3.1, для отдельных игр.

**CPU и Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): обнаружение и настройка CPU через SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) и [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): разблокировка ядер.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) и [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): состояния производительности CPU через ACPI.

**Датчики, память и вентиляторы**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): телеметрия регуляторов напряжения (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): температура памяти GDDR6.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): размер VRAM через CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): датчики NCT и PWM вентиляторов.

**Прошивка**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): стоковый BIOS P3.00 и Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell и MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): копия набора обновления ASRock (P2.00 и P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): собственный логотип загрузки.

Лицензии, статус проверки и точные границы каждой интеграции описаны в [уведомлениях о сторонних компонентах](../THIRD_PARTY_NOTICES.md).

## Структура проекта

```text
bc250-control-center/
├── src/bc250cc/          Ядро, без графического интерфейса
│   ├── domain/           Правила и ограничения каждого модуля (GPU, CPU, CU, вентиляторы, прошивка…)
│   ├── application/      Сценарии, объединяющие эти правила
│   ├── infrastructure/   Доступ к системе: датчики, службы, пакеты, GitHub
│   ├── platform/         Различия между дистрибутивами и системами инициализации
│   └── shared/           Версия, пути и контракты, общие для всех процессов
├── frontends/
│   ├── desktop/          Настольное приложение на Qt
│   │   ├── pages/        Один файл на модуль (панель, GPU, CPU, вентиляторы, прошивка…)
│   │   ├── components/   Повторно используемые элементы интерфейса
│   │   ├── onboarding/   Экран приветствия и обзор
│   │   ├── console/      Встроенный терминал
│   │   ├── theme/        Темы, стили, цвета и значки
│   │   └── i18n/         Переводы на 30 языков
│   └── cli.py            Режим командной строки
├── integrations/decky/   Плагин Decky Quick Access для игрового режима
├── privileged/           То, что выполняется от root, изолированно и проверенно
│   ├── helpers/          Один помощник на каждую привилегированную задачу
│   ├── lib/              Код, общий для этих помощников
│   └── policies/         Разрешения Polkit
├── packaging/            Пакеты .pkg.tar.zst, .rpm и .deb и PKGBUILD для AUR
├── scripts/              Лаунчеры, локальный установщик и системные утилиты
├── assets/               Значки, снимки экрана и веб-галерея
├── docs/                 Документация, уведомления о сторонних компонентах и переводы этого README
└── tests/                Более 4000 автоматических тестов
```

Лицензия [MIT](../../LICENSE).
