# Эксплуатация и данные для поддержки

[English](OPERATIONS.md) · [Русский](OPERATIONS_RU.md)

Все operational endpoints требуют сессию администратора или явно настроенный
`ADMIN_SHARED_TOKEN`. Публичными остаются только health probes. Не передавайте
administrator token системам Prometheus, backup jobs или support tooling,
которым вы не доверяете.

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
