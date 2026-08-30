# BC250 Control Center

[English](../../README.md) · [Español](README.es.md) · [Português](README.pt-BR.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Центр управления Linux для AMD BC-250: мониторинг, управление GPU, настройка CPU, Compute Units и вентиляторов в одном настольном приложении.

## Снимки экрана

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Панель BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Установка

```bash
# Из исходного кода
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh

# Arch, CachyOS и Manjaro
yay -S bc250-control-center-git
```

Чтобы удалить локальную установку, выполните `./uninstall-local.sh` из той же папки.

Пакеты доступны в [последнем выпуске](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara и Bazzite используют один RPM `noarch`:

```bash
sudo dnf install ./bc250-control-center-*.rpm        # Fedora / Nobara
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot                                      # после rpm-ostree
sudo apt install ./bc250-control-center_*.deb         # Ubuntu / Debian
```

## Первый запуск

1. Откройте `bc250-control-center`.
2. В Dashboard выберите **Prepare dependencies**.
3. Проверьте статус модуля перед применением изменения.

## Возможности

- Показатели CPU, GPU, памяти, хранилища, сети, температур и вентиляторов в реальном времени.
- GPU governor, настройка CPU и экспериментальная разблокировка ядер.
- Управление 24–40 Compute Units, PWM и кривыми вентиляторов.
- Диагностика, история, экспорт CSV, масштаб интерфейса и навигация контроллером.

## Дополнительный Decky Quick Access

В SteamOS/Game Mode панель устанавливается из раздела **Decky** внизу Dashboard. Приложение устанавливает Decky Loader при необходимости либо устанавливает/восстанавливает только BC250 Quick Access. См. [README Decky](../../integrations/decky/bc250-quick-access/README.md).

## Безопасность

Разгон, изменения Compute Units и управление вентиляторами могут вызвать зависания, выключения, потерю данных или повреждение оборудования. Применяйте по одному изменению, сохраняйте путь восстановления и не считайте программные проверки аппаратной валидацией.

## Благодарности

Проект использует работу сообщества через явные проверенные процессы. [Уведомления о сторонних компонентах](../THIRD_PARTY_NOTICES.md) содержат лицензии, статус проверки и границы интеграции.

## Языки

Настольный интерфейс поддерживает 30 языков, может следовать языку системы или изменяться в Settings; среди них английский, испанский, португальский, русский, украинский, немецкий, французский, польский, китайский, японский, корейский и другие.

## Структура проекта

```text
src/bc250cc/   логика приложения и системы
frontends/     адаптеры Desktop Qt, CLI и Quick Access
privileged/    защищённые helpers и политика Polkit
packaging/     метаданные пакетов и настройка дистрибутивов
scripts/       средства запуска и локальный установщик
```

Лицензия [MIT](../../LICENSE).
