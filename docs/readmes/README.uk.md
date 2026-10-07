# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Центр керування AMD BC-250 для Linux. Моніторинг, керування GPU, налаштування CPU, Compute Units, вентилятори й оновлення BIOS в одному настільному застосунку — з чіткими обмеженнями та перевірками перед кожною зміною обладнання.

## Знімки екрана

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Панель BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Усі знімки екрана →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Встановлення

### Arch, CachyOS і SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Пакети випусків

Завантажте пакет для своєї системи з [останнього випуску](https://github.com/movacx/bc250-control-center/releases/latest):

| Система | Файл |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<версія>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<версія>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<версія>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: той самий RPM, потім перезавантаження в нове розгортання
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

У Debian та Ubuntu використовуйте `apt install`, а не `dpkg -i`: так APT завантажить і залежності. Якщо після `dpkg -i` пакет лишився недовстановленим, це виправить `sudo apt --fix-broken install`.

### Оновлення

Повертатися на цю сторінку не потрібно. Коли виходить нова версія, панель повідомляє про це, показує, що змінилося, і встановлює її менеджером пакетів вашої системи, попередньо перевіривши SHA-256.

У SteamOS оновлення вимикає захист лише для читання, встановлює пакет і знову його вмикає. Оновлення SteamOS видаляє все, що встановлено в систему, зокрема цю програму: відкрийте **Reinstall BC250 Control Center** у меню режиму робочого столу й знову підготуйте залежності. SteamOS запитує пароль `deck`; якщо ви його не створювали, спершу виконайте `passwd` у Konsole.

**Переходите з 1.19?** Її вбудований механізм оновлення не вміє встановлювати пакети. Оновіться один раз вручну пакетом з [останнього випуску](https://github.com/movacx/bc250-control-center/releases/latest); далі програма оновлюється сама. У Bazzite замініть 1.19 за один крок і перезавантажтеся; якщо встановлювали через install-local.sh, спершу видаліть ту копію:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Перший запуск

1. Відкрийте **BC250 Control Center**.
2. Екран вітання запитає мову, оформлення та вигляд бічної панелі й запропонує встановити інструменти, потрібні платі. Усе це можна змінити пізніше в **Налаштуваннях**.
3. За бажання пройдіть огляд: він проведе кожним модулем і пояснить, що кожен із них змінює на платі.

Перед будь-якою зміною перевірте стан модуля: він повідомляє, що готово, чого бракує і чому.

## Можливості

**Панель і моніторинг**
- Панель із процесором, графікою та охолодженням, ядрами наживо, температурою кожного чипа GDDR6, лініями живлення (з модом I2C) і встановленим BIOS.
- Модуль «Продуктивність» із графіками CPU, GPU, VRAM, RAM, диска й мережі та поданням «Датчики» з мінімумом, середнім і максимумом.

**Обладнання**
- **GPU:** безпечні діапазони governor для Cyan та Oberon, лабораторія напруг і точки понад 2000 МГц.
- **CPU / SMU:** тимчасове й постійне налаштування, тест стабільності та експериментальне розблокування прихованих ядер.
- **Compute Units:** від 24 до 40 CU, поточний стан і стан під час завантаження показано окремо.
- **Вентилятори:** ручне керування PWM, криві за температурою, профілі, що зберігаються після перезавантаження, та експорт у файл або в Decky.
- **Пам'ять:** розмір VRAM, ZRAM, ZSWAP і файл підкачки.
- **Прошивка (BIOS):** готує USB для оновлення з P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 або P2.00, кожен файл перевіряється.

**Система**
- Підготовка залежностей для кожного дистрибутива з вбудованим терміналом, де видно кожну команду.
- Виправлення сумісності: GFX1013 і async compute, FSR4 для окремих ігор, телеметрія та ACPI.
- Драйвери Wi-Fi, Bluetooth і принтерів з офіційних репозиторіїв вашого дистрибутива.
- Діагностика, історія та експорт метрик у CSV.

**Інтерфейс**
- Теми «Світла», «Темна» та «Нічний синій», стилі «Стандартний» і «Строгий», 10 акцентних кольорів і масштаб від 70 % до 150 %.
- 30 мов і керування геймпадом.

## Decky Quick Access (додатково)

Панель для меню швидкого доступу SteamOS та ігрового режиму Steam. Повсякденні налаштування (GPU, CU, CPU, вентилятори та VRAM) доступні просто з гри; розширене налаштування лишається в настільному застосунку.

- **Профілі для ігор:** призначте кожній грі профіль GPU та вентиляторів. Він застосовується під час запуску гри, а після її закриття все повертається як було.
- **Async compute наживо:** показує, чи використовує гра асинхронні обчислення і наскільки.
- **Пресети вентиляторів:** з назвами та швидкостями, експортованими з настільного застосунку.

Щоб установити, відкрийте **Панель**, прокрутіть до розділу **Decky** і виберіть запропоновану дію. Якщо Decky Loader відсутній, застосунок установить його; якщо він уже є — установить або відновить лише BC250 Quick Access. Звичайна підготовка залежностей ніколи не встановлює Decky сама.

Докладніше в [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Безпека

Розгін, зміна Compute Units, керування вентиляторами й оновлення BIOS можуть спричинити зависання чи вимкнення системи, втрату даних або пошкодження обладнання. Застосовуйте зміни по одній, завжди майте шлях назад і не вважайте перевірки застосунку гарантією для обладнання.

## Зовнішні інструменти та подяки

BC250 Control Center спирається на роботу спільноти й не привласнює жодного з цих проєктів. Кожен інструмент використовується лише через явні, перевірені сценарії.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): підтримуваний альтернативний governor.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) і [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): ядро та Mesa/RADV для GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): узгоджені ядро та Mesa/RADV для Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute у Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) і [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 для окремих ігор.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): реконструкція DLSS Model E для ігор з FSR 3.1, для окремих ігор.

**CPU і Compute Units**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): виявлення й налаштування CPU через SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) і [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): розблокування ядер.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) і [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Compute Units.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): стани продуктивності CPU через ACPI.

**Датчики, пам'ять і вентилятори**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): телеметрія регуляторів напруги (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): температура пам'яті GDDR6.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): розмір VRAM через CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): датчики NCT і PWM вентиляторів.

**Прошивка**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): стоковий BIOS P3.00 і Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell і MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): копія набору оновлення ASRock (P2.00 і P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): власний логотип завантаження.

Ліцензії, статус перевірки й точні межі кожної інтеграції описано в [повідомленнях про сторонні компоненти](../THIRD_PARTY_NOTICES.md).

## Структура проєкту

```text
bc250-control-center/
├── src/bc250cc/          Ядро, без графічного інтерфейсу
│   ├── domain/           Правила й обмеження кожного модуля (GPU, CPU, CU, вентилятори, прошивка…)
│   ├── application/      Сценарії, що поєднують ці правила
│   ├── infrastructure/   Доступ до системи: датчики, служби, пакети, GitHub
│   ├── platform/         Відмінності між дистрибутивами та системами ініціалізації
│   └── shared/           Версія, шляхи й контракти, спільні для всіх процесів
├── frontends/
│   ├── desktop/          Настільний застосунок на Qt
│   │   ├── pages/        Один файл на модуль (панель, GPU, CPU, вентилятори, прошивка…)
│   │   ├── components/   Повторно використовувані елементи інтерфейсу
│   │   ├── onboarding/   Екран вітання та огляд
│   │   ├── console/      Вбудований термінал
│   │   ├── theme/        Теми, стилі, кольори та значки
│   │   └── i18n/         Переклади 30 мовами
│   └── cli.py            Режим командного рядка
├── integrations/decky/   Плагін Decky Quick Access для ігрового режиму
├── privileged/           Те, що виконується від root, ізольовано й перевірено
│   ├── helpers/          Один помічник на кожне привілейоване завдання
│   ├── lib/              Код, спільний для цих помічників
│   └── policies/         Дозволи Polkit
├── packaging/            Пакети .pkg.tar.zst, .rpm і .deb та PKGBUILD для AUR
├── scripts/              Лаунчери, локальний інсталятор і системні утиліти
├── assets/               Значки, знімки екрана й вебгалерея
├── docs/                 Документація, повідомлення про сторонні компоненти й переклади цього README
└── tests/                Понад 4000 автоматичних тестів
```

Ліцензія [MIT](../../LICENSE).
