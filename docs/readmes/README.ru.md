# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

<a href="https://ko-fi.com/movacx"><img src="https://img.shields.io/badge/Ko--fi-%D0%9F%D0%BE%D0%B4%D0%B4%D0%B5%D1%80%D0%B6%D0%B0%D1%82%D1%8C-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Поддержать · Ko-fi"></a>

Настольное приложение для настройки, разгона и мониторинга AMD BC-250 в Linux.

Оно охватывает управление частотами GPU (governor), настройку CPU, Compute Units (CU), вентиляторы, память, обновление BIOS, апскейлинг и подготовку системы для поддерживаемых дистрибутивов. Каждое изменение аппаратной части проверяется по своим пределам и подтверждается перед применением. Необязательный плагин Decky переносит повседневные настройки в игровой режим Steam.

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="../../assets/screenshots/dashboard-overview.png" alt="Панель BC250 Control Center" width="100%"></a>
</p>

Больше скриншотов в [галерее](https://movacx.github.io/bc250-control-center/gallery/).

## Возможности

- Панель с CPU, GPU, охлаждением, нагрузкой по ядрам, температурой GDDR6 по каждому чипу, установленным BIOS и линиями питания (для линий нужна аппаратная модификация I2C; в приложении есть фотоинструкция)
- Графики производительности CPU, GPU, VRAM, RAM, диска и сети, с обзором датчиков и экспортом в CSV
- Управление governor GPU (Cyan, с Oberon как альтернативой), безопасные диапазоны частот и лаборатория напряжения
- Настройка CPU через SMU, тест стабильности и необязательная разблокировка ядер
- Compute Units: от 24 до 40 CU, с отдельным отображением текущего состояния и состояния при загрузке
- Управление вентиляторами: ручной PWM, температурные кривые, постоянные профили или передача CoolerControl, fancontrol или fan2go
- Память: размер VRAM, ZRAM, ZSWAP и swap
- Создание USB-накопителя для обновления BIOS (P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00, P2.00), каждый файл проверяется
- Апскейлинг для каждой игры: FSR4 INT8 через OptiScaler Client и HelixSR, с резервным копированием и восстановлением файлов игры
- Подготовка системы в зависимости от дистрибутива, выполняемая во встроенном терминале
- Исправления совместимости для GFX1013, async compute, ACPI и Mesa; Dolby Digital 5.1 через HDMI; управление телевизором через HDMI-CEC
- Отчёты о проблемах внутри приложения, с кодами ошибок, кодами источника и приложенной необработанной ошибкой
- 30 языков, светлая и тёмная темы, масштабирование интерфейса и навигация с геймпада

## Поддерживаемые дистрибутивы

- Arch Linux, CachyOS, Manjaro
- Fedora, Nobara
- Bazzite и другие варианты Fedora Atomic
- SteamOS (бета)
- Ubuntu, Linux Mint, Debian 13

Требуется Python 3.11 или новее. Другие дистрибутивы, включая системы с OpenRC, распознаются и по возможности поддерживаются, но тестируются не в каждом выпуске.

## Установка

### AUR

Для Arch Linux, CachyOS и SteamOS:

```bash
yay -S bc250-control-center-git
```

### Пакеты выпусков

Скачайте пакет для своего дистрибутива из [последнего выпуска](https://github.com/movacx/bc250-control-center/releases/latest).

Arch Linux, CachyOS, Manjaro:

```bash
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
```

Fedora, Nobara:

```bash
sudo dnf install ./bc250-control-center-*.rpm
```

Bazzite и Fedora Atomic (нужна перезагрузка):

```bash
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot
```

Ubuntu, Linux Mint, Debian:

```bash
sudo apt install ./bc250-control-center_*.deb
```

Используйте `apt install`, а не `dpkg -i`, чтобы зависимости установились автоматически. Если пакет остался наполовину установленным после `dpkg -i`, выполните `sudo apt --fix-broken install`.

### SteamOS

SteamOS держит системный раздел в режиме только для чтения, поэтому пакет можно установить только при отключённой защите. Откройте Konsole в режиме рабочего стола и выполните:

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
sudo pacman -Syy
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
sudo steamos-readonly enable
```

Строки `pacman-key` и `pacman -Syy` обновляют ключи и базы пакетов, которые сбрасываются при обновлении SteamOS. Если пароль для пользователя `deck` ещё не задан, сначала выполните `passwd`. После обновления SteamOS пункт **Reinstall BC250 Control Center** в меню режима рабочего стола выполнит эти шаги за вас.

### Из исходного кода

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center
./run.sh                          # запуск из рабочей копии
bash scripts/install-local.sh     # или установка для текущего пользователя
```

## Обновления

Приложение проверяет новые выпуски, показывает список изменений, проверяет контрольную сумму пакета и устанавливает обновление менеджером пакетов системы.

**SteamOS:** системное обновление SteamOS удаляет пакеты, установленные в систему, включая это приложение. После системного обновления выполните **Reinstall BC250 Control Center** в меню режима рабочего стола, а затем снова запустите Prepare BC250 system. SteamOS запрашивает пароль пользователя `deck`; если его нет, задайте его командой `passwd`.

**Переход с 1.19:** программа обновления 1.19 не умеет устанавливать пакеты. Установите текущую версию вручную один раз; последующие версии будут обновляться сами.

```bash
# Bazzite / Fedora Atomic: заменить наложенный пакет 1.19
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# Копия, установленная через install-local.sh: удалите её, затем установите пакет
bash scripts/uninstall-local.sh
```

## Первые шаги

1. Запустите BC250 Control Center. Экран первого запуска задаёт язык и оформление и предлагает установить необходимые компоненты.
2. По желанию пройдите экскурсию, которая объясняет, что каждый модуль меняет на плате.
3. На панели запустите **Prepare BC250 system**. Приложение покажет, что будет установлено для вашего дистрибутива, и выполнит это во встроенном терминале.
4. Перед применением изменений читайте строку состояния модуля: она показывает, что готово и чего не хватает.

## Плагин Decky

BC250 Quick Access — необязательная панель в меню быстрого доступа игрового режима Steam. Она даёт управление GPU, Compute Units, CPU, вентиляторами и VRAM, профили GPU и вентиляторов для каждой игры, а также показания async compute в реальном времени. Расширенная настройка остаётся в настольном приложении.

Установите его из раздела **Decky** на панели. Decky Loader тоже установится, если его нет; больше ничто в приложении Decky не устанавливает. Подробности — в [README плагина](../../integrations/decky/bc250-quick-access/README.md).

## Сообщения о проблемах

В окнах ошибок показаны диагностический код (например, `BC250-UPSCALE-001`), код источника, указывающий функцию, где произошла ошибка (например, `GPU-0142`), и необработанная ошибка с трассировкой.

Используйте **Сообщить о проблеме** в окне ошибки или **Настройки › Диагностика › Отправить отчёт**. Форма открывается в приложении с уже заполненными кодами, необработанной ошибкой, характеристиками системы и последними ошибками. Перед отправкой можно всё проверить; пути к домашнему каталогу заменяются на `~`. Если форму не удаётся отправить, она откроется в браузере с сохранёнными ответами. Форма также доступна [в сети](https://docs.google.com/forms/d/e/1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA/viewform).

К отчёту также прикладывается аппаратная диагностика, собираемая без root на любом дистрибутиве: ядро и заголовки, загруженные модули датчиков и их сообщения ядра (NCT6687, amdgpu), показания hwmon и `sensors`, строки GPU и сбоев из журнала ядра, как завершилась предыдущая загрузка (чистое выключение или внезапный сброс), службы, пакеты и конец последнего журнала рабочего процесса. Если журнал ядра недоступен вашему пользователю, рабочий стол один раз запросит пароль через polkit. Отчёты, слишком большие для формы, автоматически сокращаются, начиная с наименее важных частей; **Открыть в браузере** по-прежнему копирует полный текст.

### Чёрный ящик (зависания и сбросы)

Жёсткое зависание не оставляет ничего в журнале ядра. Чёрный ящик четыре раза в секунду записывает частоту и нагрузку GPU, температуры, напряжение GFX, мощность, скорость вентилятора, частоту CPU и свободную память, сбрасывая каждую строку на диск. Поэтому следующий отчёт покажет последние секунды работы платы до зависания или сброса. Он не требует root, а его файл ограничен по размеру (512 КБ, затем ротация).

```bash
# Режим рабочего стола: оставьте терминал открытым во время игры, остановите Ctrl+C
bc250-control-center-cli black-box

# Игровой режим (SteamOS): запустите в фоне до переключения
systemd-run --user --unit=bc250-black-box bc250-control-center-cli black-box
systemctl --user stop bc250-black-box
```

Журнал хранится в `~/.local/state/bc250-control-center/black-box/`. Команда `bc250-control-center-cli diagnose` выводит ту же аппаратную диагностику, что отправляет отчёт.

Сообщения о проблемах на GitHub также приветствуются. Укажите дистрибутив, версию ядра и вывод терминала.

## Безопасность

Разгон, разблокировка Compute Units, изменение управления вентиляторами и прошивка BIOS могут сделать систему нестабильной, привести к потере данных или повредить плату. Меняйте одну настройку за раз и держите способ откатить изменения. Проверки приложения ловят типичные ошибки, но не являются гарантией.

## Благодарности

Этот проект опирается на работу сообщества BC-250. Перечисленные ниже проекты принадлежат их авторам; приложение интегрирует их через проверенные, закреплённые за версией процессы. Лицензии и объём каждой интеграции указаны в [уведомлениях о сторонних компонентах](../THIRD_PARTY_NOTICES.md).

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor GPU
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): альтернативный governor
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) и [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): ядро и Mesa/RADV для GFX1013
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): ядро и Mesa/RADV для Arch и CachyOS
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute на Bazzite 44, с патчами RADV, которые также собираются для Arch, CachyOS и Fedora с ядром 7.2 или новее

**Апскейлинг**
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) и [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork): OptiScaler Client, FSR4 для каждой игры
- [HelixSR](https://github.com/lonewolf0622/HelixSR): реконструкция DLSS Model E в играх с FSR 3.1

**CPU и Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): определение и настройка CPU через SMU
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) и [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): разблокировка ядер
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): состояния производительности CPU через ACPI
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) и [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units

**Датчики, память и вентиляторы**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): телеметрия регуляторов напряжения (VRM) и фотографии для инструкции I2C
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): температура GDDR6
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): размер VRAM через CMOS
- [nct6687d](https://github.com/Fred78290/nct6687d): датчики NCT и PWM вентиляторов
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, демон HDMI-CEC от Valve

**Прошивка**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): исходный BIOS P3.00 и Chipset Menu
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell и MeiMeiDXE v3
- [BC-250](https://github.com/kenavru/BC-250): зеркало набора обновления ASRock (P2.00 и P5.00)
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): пользовательский логотип загрузки

**Связанные проекты** (приложение их не использует; лицензии по данным GitHub)
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) и [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0): температуры VRM и памяти как модули ядра
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0): набор для настройки Bazzite
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) и [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm): исследование кодирования видео VCN и открытый драйвер для Windows (лицензия не объявлена; только ссылки)

## Структура проекта

```text
bc250-control-center/
├── src/bc250cc/              Ядро без графического интерфейса
│   ├── domain/               Правила и пределы каждого модуля (GPU, CPU, CU, вентиляторы, прошивка…)
│   ├── application/          Сценарии использования, объединяющие эти правила
│   ├── infrastructure/       Доступ к системе: датчики, службы, пакеты, GitHub
│   ├── platform/             Различия между дистрибутивами и системами загрузки
│   └── shared/               Версия, пути и контракты, общие для всех процессов
├── frontends/
│   ├── desktop/              Настольное приложение на Qt
│   │   ├── pages/            Один файл на модуль (панель, GPU, CPU, вентиляторы, прошивка…)
│   │   ├── components/       Переиспользуемые части интерфейса
│   │   ├── onboarding/       Экран приветствия и экскурсия
│   │   ├── console/          Встроенный терминал
│   │   ├── theme/            Темы, стили, цвета и значки
│   │   └── i18n/             Переводы на 30 языков
│   └── cli.py                Режим командной строки
├── integrations/decky/       Плагин Decky Quick Access для игрового режима
├── privileged/               То, что работает от root: изолировано и проверено
│   ├── helpers/              Один помощник на каждую привилегированную задачу
│   ├── lib/                  Код, общий для этих помощников
│   └── policies/             Разрешения Polkit
├── packaging/                Пакеты .pkg.tar.zst, .rpm и .deb и PKGBUILD для AUR
├── scripts/                  Запускающие скрипты, локальный установщик и системные утилиты
├── assets/                   Значки, скриншоты и веб-галерея
├── docs/                     Документация, уведомления о сторонних компонентах и переводы этого README
└── tests/                    Более 5000 автоматических тестов, с файлами os-release 37 реальных дистрибутивов
```

## Участие в проекте

Самый полезный вклад — отчёт об ошибке, особенно с указанием дистрибутива, версии ядра и того, что вывел терминал. Если вы используете дистрибутив, которого нет выше, расскажите, как он работает, хорошо или плохо.

Лицензия [MIT](../../LICENSE).
