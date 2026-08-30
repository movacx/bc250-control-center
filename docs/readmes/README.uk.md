# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Центр керування Linux для AMD BC-250: моніторинг, керування GPU, налаштування CPU, Compute Units і вентиляторів в одній настільній програмі.

## Знімки екрана

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Панель BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Встановлення

```bash
# Із вихідного коду
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS і Manjaro
yay -S bc250-control-center-git
```

Щоб видалити локальну інсталяцію, виконайте `./uninstall-local.sh` з тієї самої папки.

Пакети доступні в [останньому випуску](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara та Bazzite використовують один RPM `noarch`:

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # після rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Перший запуск

1. Відкрийте `bc250-control-center`.
2. На Dashboard виберіть **Prepare dependencies**.
3. Перевірте стан модуля перед застосуванням зміни.

## Можливості

- Живі показники CPU, GPU, пам’яті, сховища, мережі, температур і вентиляторів.
- GPU governor, налаштування CPU та експериментальне розблокування ядер.
- Керування 24–40 Compute Units, PWM і кривими вентиляторів.
- Діагностика, історія, експорт CSV, масштабування інтерфейсу й навігація контролером.

## Додатковий Decky Quick Access

У SteamOS/Game Mode панель встановлюється з розділу **Decky** внизу Dashboard. Програма встановлює Decky Loader за потреби або встановлює/відновлює лише BC250 Quick Access. Див. [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Безпека

Розгін, зміни Compute Units і керування вентиляторами можуть спричинити зависання, вимкнення, втрату даних або пошкодження обладнання. Застосовуйте одну зміну за раз, зберігайте шлях відновлення та не вважайте програмні перевірки апаратною валідацією.

## Подяки

Проєкт використовує роботу спільноти через явні перевірені процеси. [Повідомлення про сторонні компоненти](../THIRD_PARTY_NOTICES.md) містять ліцензії, стан перевірки та межі інтеграції.

## Мови

Настільний інтерфейс підтримує 30 мов, може використовувати мову системи або змінюватися в Settings: англійська, іспанська, португальська, російська, українська, німецька, французька, польська, китайська, японська, корейська та інші.

## Структура проєкту

```text
src/bc250cc/   логіка програми й системи
frontends/     адаптери Desktop Qt, CLI та Quick Access
privileged/    захищені helpers і політика Polkit
packaging/     метадані пакетів і налаштування дистрибутивів
scripts/       засоби запуску та локальний інсталятор
```

Ліцензія [MIT](../../LICENSE).
