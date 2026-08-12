# Диагностика

[English](TROUBLESHOOTING.md) · [Русский](TROUBLESHOOTING_RU.md)

Сначала включите dry-run на аутентифицированной странице Настройки. До рестарта
или rollback сохраните database, logs, failed job и correlation ID: restart
может изменить downstream evidence, хотя персистентное состояние CleanArr
сохранится.

## Процесс не готов

Сначала проверьте `/health/live`, затем `/health/ready`. Для контейнера смотрите
`docker compose ps` и `docker compose logs cleanarr`; для нативного пакета —
`systemctl status cleanarr` и `journalctl -u cleanarr`.

Типичные причины: недоступный для записи или временный `DB_PATH`, неподдерживаемая
будущая версия схемы database/config и повреждённый SQLite. Не удаляйте БД ради
зелёного readiness. Остановите CleanArr, сохраните failed state отдельно,
выполните SQLite `PRAGMA integrity_check` и следуйте документированной процедуре
backup/restore.

## Сервис unhealthy или отклоняет credentials

Выполните Проверить подключение для точного профиля и сравните заявленную версию
с [матрицей совместимости](COMPATIBILITY_RU.md). Публичный ping endpoint не
доказывает работоспособность настроенного credential; health checks CleanArr
используют аутентифицированные контракты.

- qBittorrent требует базовый URL Web UI без добавленного `/api/v2`. Проверьте
  policy host/port Web UI и используйте username/password либо поддерживаемый
  Bearer API key.
- Transmission обычно использует `/transmission/rpc`. Проверьте Basic
  credentials и не фиксируйте поколение протокола: CleanArr согласует его с
  сервером автоматически.
- Deluge Web должен быть подключён к daemon. Настроенный secret является
  паролем Web, а не credential только для daemon.
- rTorrent требует аутентифицированный HTTP XML-RPC endpoint. Для удаления с
  данными дополнительно нужны `execute.throw` и filesystem permissions процесса
  rTorrent.
- URL Radarr и Sonarr должны включать настроенную базу API, обычно `/api/v3`.
  Tokens Jellyfin и Seerr должны приниматься аутентифицированными status
  endpoints.

## Webhook отклонён или проигнорирован

Проверьте Jellyfin destination URL, выбор события `Item Deleted`, заголовок
`X-Webhook-Token` и template из README. Ошибка аутентификации отличается от
safety skip. Для пропуска найдите correlation ID в Activity и изучите причину:
отсутствие точного identifier/path, неоднозначный владелец Arr, отсутствие
history hash, pack/shared data и повтор завершённого event являются намеренными
fail-closed результатами.

Не добавляйте fuzzy matching ради обхода пропуска. Исправьте source metadata,
profile URL, владение instance или download history и создайте новый dry-run
preview.

## Ручное задание partial или ожидает retry

Откройте персистентное задание и сравните завершённые действия с заново
рассчитанным preflight. Ошибка torrent намеренно блокирует зависимые удаления
Arr/Seerr/Jellyfin. Восстановите dependency, оставьте dry-run включённым для
диагностики и повторите задание с новым подтверждённым hash плана. Не изменяйте
строку job напрямую в SQLite.

После рестарта дождитесь readiness и повторно откройте job. Resolved event,
подтверждённый preflight, завершённые actions, attempt count и next retry time
хранятся персистентно.

## Не работает login или SSO

Используйте отдельную [диагностику OIDC и reverse proxy](SSO_RU.md#диагностика).
Особенно проверьте точные HTTPS issuer/redirect URI, proxy scheme/host, allowlist
или required claim, синхронизацию времени и контракт `Secure` cookie. При
введении SSO сохраняйте проверенный локальный путь администратора.

## Не работает upgrade или rollback

Остановите мутации и сохраните обе БД: pre-upgrade и failed-upgrade. Не
запускайте старый релиз на мигрированной БД. Восстановите верифицированный backup,
соответствующий старому image/package, затем запустите именно эту версию. Команды
Docker приведены в README, нативных пакетов — в разделе
[Linux packages](LINUX_PACKAGES_RU.md#обновление-и-откат).

## Сбор доказательств для поддержки

Скачайте аутентифицированный редактированный support bundle и приложите версии
CleanArr/dependencies, health summary, structured error code, correlation ID,
тип deployment и точные шаги воспроизведения. Перед передачей просмотрите bundle
и logs: redaction покрывает известные credential fields, но не может распознать
секрет, вставленный в произвольное имя или external error.

Никогда не прикладывайте к публичному issue рабочую БД, environment file,
tokens, cookies, приватные service URLs или непроверенный debug log.

