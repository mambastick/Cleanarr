# Эксплуатация и данные для поддержки

[English](OPERATIONS.md) · [Русский](OPERATIONS_RU.md)

Все operational endpoints требуют сессию администратора или явно настроенный
`ADMIN_SHARED_TOKEN`. Публичными остаются только health probes. Не передавайте
administrator token системам Prometheus, backup jobs или support tooling,
которым вы не доверяете.

## Операции Library и storage в UI-v2

Authenticated Library workspace использует следующие read-only endpoints:

- `GET /api/library/items?media_type=movie|series&q=&sort=added|title|size&direction=asc|desc&limit=1..50&cursor=` возвращает ограниченную страницу, привязанную к revision. `refresh=true` обходит in-process cache, но не меняет Arr или Jellyfin.
- `GET /api/library/items/{resource_id}` возвращает detail выбранного opaque resource. Детали эпизодов и файлов сериала ограничены, raw paths исключены.
- `GET /api/library/artwork/{resource_id}` сначала разрешает объект и проксирует проверенный artwork из Jellyfin. Endpoint требует admin session, является private и разрешает клиентский cache не более часа.
- `GET /api/storage/volumes` возвращает observations томов Radarr/Sonarr без raw paths. `POST /api/storage/refresh` просит одно объединённое обновление и возвращает `429` с code `refresh_throttled` при повторе в течение 10 секунд.

Library collection results кэшируются 30 секунд на сочетание runtime
configuration, языка Jellyfin и media type; search и sorting используют
закэшированный каталог. Storage collection results кэшируются 60 секунд и считаются fresh 120 секунд.
Параллельные чтения объединяются. Missing, invalid, partial, stale или
conflicting observation получает `unknown`: он не превращается в healthy storage
или в разрешение на удаление. Storage status имеет приоритет critical,
unknown/partial, warning, healthy. Storage status является сигналом и не доказывает
ownership torrent.

Shell адаптивен (sidebar 240px на desktop, rail 80px на tablet, top bar и bottom
navigation на mobile) и резервирует safe-area для контента. Это presentation
layer не меняет authentication, preflight или fail-closed правила удаления.

## Обновление и rollback

Runtime configuration schema 4 добавляет thresholds свободного места storage:
warning 15% и critical 5% по умолчанию. Значения должны быть конечными
неотрицательными процентами, а warning — строго выше critical. Неверная
конфигурация даёт fail-closed. Не удаляйте автоматически созданный
совместимый с v3 pre-upgrade backup, пока новая binary и конфигурация не
проверены.

В стандартном SQLite deployment sidecar называется
`cleanarr.config-v3.backup.db` и лежит рядом с `cleanarr.db`. Legacy file-backed
configuration создаёт `runtime-config.config-v3.backup.json` рядом с
`runtime-config.json`. Существующие sidecars никогда не перезаписываются. Перед
rollback остановите CleanArr, отдельно сохраните неудачное состояние v4,
скопируйте соответствующий sidecar обратно под исходным именем, для SQLite
проверьте `PRAGMA integrity_check`, затем запустите старую binary.

Старая binary CleanArr должна отклонить конфигурацию с более новой schema и не
перезаписать её. Для rollback остановите новую binary, восстановите подходящий
automatic v3 backup (и соответствующий SQLite backup, если применялись
миграции БД), установите или закрепите старую binary и запустите её с
восстановленными файлами. Не запускайте старую binary на мигрированной БД или
конфигурации v4. Неудачное состояние храните отдельно для диагностики и перед
запуском проверьте БД через `PRAGMA integrity_check`.

## Метрики Prometheus

`GET /metrics` возвращает Prometheus text format. Labels намеренно ограничены
типом интеграции, health state, item type, статусом операции, результатом webhook,
статусом задания, ограниченным статусом download action и ограниченным policy
decision. Media names и IDs, пути, имена профилей, URL, hashes и credentials в
labels не попадают.

Значения операций являются gauges по сохраняемой истории, а не lifetime
counters: они могут уменьшаться после очистки activity retention или истории
ручных заданий.

Пример scrape configuration с optional static administrator token:

```yaml
scrape_configs:
  - job_name: cleanarr
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/cleanarr-admin-token
    static_configs:
      - targets: [cleanarr:8089]
```

## Support bundle

`GET /api/support/bundle` возвращает JSON с версиями CleanArr, config schema и
database schema; количеством настроенных и включённых профилей, health и
downstream versions для типов интеграций; последними структурированными кодами
ошибок/actions и correlation IDs; агрегатами webhook/manual jobs, download actions
и policy decisions.

Ответ исключает media names и IDs, пути, имена профилей, URL, credentials,
free-form messages и action details. Перед отправкой всё равно проверьте файл:
версии, агрегированные количества и время могут описывать часть установки.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  http://127.0.0.1:8089/api/support/bundle \
  --output cleanarr-support.json
```

Каждый новый deletion cascade получает `correlation_id`. По нему можно связать
API result или activity record с редактированной записью ошибки в support bundle.

## Operational evidence для Downloads

Агрегаты download actions и policy являются gauges по сохраняемой истории, а не
доказательством завершения отдельного pause/resume. Action projection намеренно
не включает idempotency keys и canonical request bodies. При расследовании
сохраните action ID, ограниченные status/code, source status и freshness
observation; не считайте один HTTP response доказательством успеха.

## Редактированный перенос конфигурации

`GET /api/config/export` возвращает версионированный transfer document. В нём
остаются profile IDs, names, очищенные URL, integration kinds и несекретные
policy settings. Локальный администратор, webhook token, OIDC authentication
settings, API keys, usernames и passwords исключаются. Credentials в документе
нет, но topology и profile names могут оставаться приватными.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  http://127.0.0.1:8089/api/config/export \
  --output cleanarr-config-redacted.json
```

`POST /api/config/import` работает только как merge и fail-safe:

- существующие профили, которых нет в документе, не удаляются;
- credentials совпавшего profile ID и kind сохраняются локально;
- новые профили получают пустые credentials;
- каждый импортированный или обновлённый профиль отключается;
- глобально принудительно включается dry-run;
- administrator, webhook token и OIDC boundary сохраняются.

Неизвестная будущая версия export schema отклоняется. После импорта внесите
недостающие credentials, проверьте каждый профиль, изучите dry-run plan и
включайте профили по одному.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-binary @cleanarr-config-redacted.json \
  http://127.0.0.1:8089/api/config/import
```

## Граница редактирования логов

Structured logs редактируют распространённые формы authorization, token,
API key, password, URL userinfo и чувствительных query parameters. Downstream
error response bodies не копируются в action messages. Это defense in depth, а
не разрешение намеренно писать credentials в логи; защищайте log storage и
проверяйте логи перед отправкой.
