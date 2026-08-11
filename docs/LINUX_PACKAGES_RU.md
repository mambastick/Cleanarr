# Нативные пакеты Linux

[English](LINUX_PACKAGES.md) · [Русский](LINUX_PACKAGES_RU.md)

В релизах CleanArr публикуются нативные DEB- и RPM-пакеты для `amd64` и `arm64`. Пакет устанавливает приложение в `/opt/cleanarr`, создаёт отдельного непривилегированного пользователя и регистрирует защищённый systemd-сервис.

## Поддерживаемые системы

- Linux с systemd;
- Python 3.12 по пути `/usr/bin/python3.12`;
- DEB: Ubuntu 24.04 или совместимая система с пакетом `python3.12`;
- RPM: Fedora или RHEL-совместимая система с пакетом `python3.12`.

Пакеты пока не подписываются. Загружайте их только из официального GitHub Release и перед установкой проверяйте `SHA256SUMS`.

## Загрузка и проверка

Скачайте пакет нужной архитектуры и `SHA256SUMS` из соответствующего [GitHub Release](https://github.com/mambastick/Cleanarr/releases).

```bash
sha256sum --check SHA256SUMS --ignore-missing
```

Имена файлов:

- `cleanarr_<версия>_amd64.deb`
- `cleanarr_<версия>_arm64.deb`
- `cleanarr_<версия>_amd64.rpm`
- `cleanarr_<версия>_arm64.rpm`

## Установка

### Debian и Ubuntu

```bash
sudo apt install ./cleanarr_<версия>_amd64.deb
```

### Fedora и RHEL-совместимые системы

```bash
sudo dnf install ./cleanarr_<версия>_amd64.rpm
```

Проверьте `/etc/cleanarr/cleanarr.env`, затем запустите сервис:

```bash
sudo systemctl enable --now cleanarr
systemctl status cleanarr --no-pager
curl --fail http://127.0.0.1:8089/health/ready
```

Откройте `http://адрес-сервера:8089` и завершите мастер настройки. Пакет устанавливает безопасное значение `DRY_RUN=true`.

## Пути

| Путь | Назначение |
|---|---|
| `/opt/cleanarr` | Приложение и Python-зависимости |
| `/etc/cleanarr/cleanarr.env` | Переменные окружения; сохраняются при обновлении |
| `/var/lib/cleanarr` | SQLite и runtime-состояние |
| `/usr/lib/systemd/system/cleanarr.service` | systemd-сервис |
| `/usr/bin/cleanarr` | Команда запуска |

Сервис слушает `0.0.0.0:8089`. Перед публикацией за пределами приватной сети используйте доверенный reverse proxy с TLS.

## Логи и проверки

```bash
journalctl -u cleanarr -f
curl --fail http://127.0.0.1:8089/health/live
curl --fail http://127.0.0.1:8089/health/ready
```

## Резервное копирование

Перед прямым копированием SQLite ненадолго остановите сервис либо используйте SQLite backup API.

```bash
sudo systemctl stop cleanarr
sudo cp -a /var/lib/cleanarr /var/lib/cleanarr.backup
sudo systemctl start cleanarr
```

Перед миграцией операционной системы сохраните копию вне сервера.

## Обновление и откат

Установите новый пакет поверх старого. Конфигурация и данные сохранятся.

```bash
sudo apt install ./cleanarr_<новая-версия>_amd64.deb
# или
sudo dnf install ./cleanarr_<новая-версия>_amd64.rpm

sudo systemctl restart cleanarr
```

Для отката при необходимости восстановите совместимую резервную копию БД, установите предыдущий пакет и перезапустите сервис.

## Удаление

```bash
sudo apt remove cleanarr
# или
sudo dnf remove cleanarr
```

При удалении намеренно сохраняются `/var/lib/cleanarr` и системный пользователь `cleanarr`. Удаляйте оставшиеся данные только после создания и проверки резервной копии.

## Локальная сборка

Нужны Node.js 24, pnpm 10, Python 3.12, Go 1.26 и nFPM 2.47.

```bash
go install github.com/goreleaser/nfpm/v2/cmd/nfpm@v2.47.0
bash packaging/build-linux-packages.sh 0.2.10 amd64
```

По умолчанию пакеты создаются в `dist/`.
