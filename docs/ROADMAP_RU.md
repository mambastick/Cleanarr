# Roadmap CleanArr 1.0

[English](ROADMAP.md) · [Русский](ROADMAP_RU.md)

Этот документ — источник истины по границам и критериям выпуска CleanArr 1.0.
Он фиксирует продуктовые решения, но не означает, что перечисленные пункты уже
реализованы.

## Определение продукта

CleanArr 1.0 — стабильный и безопасный оркестратор удаления для цепочки:

`Jellyfin -> Radarr/Sonarr -> Seerr -> основные torrent-клиенты`

Версия 1.0 означает документированный контракт совместимости, безопасные
обновления, устойчивую обработку и обязательные quality gates. Она не означает
поддержку всех медиасерверов, Arr-приложений и протоколов загрузки.

## Зафиксированный baseline

Последняя проверка: **2026-08-11**, тег **v0.2.11**, коммит **ff51e29**.

Уже реализовано:

- сценарии удаления фильма, сериала, сезона и эпизода;
- строгое сопоставление по TMDB/TVDB/IMDB/пути и консервативные проверки
  раздач-паков и общих файлов;
- dry-run по умолчанию, журнал действий, ручные фоновые задания и мониторинг
  сервисов;
- профили сервисов с одной активной целью каждого типа;
- интеграции qBittorrent, Radarr, Sonarr, Jellyfin и Jellyseerr;
- локальная аутентификация, режимы OpenID Connect, интерфейс на русском и
  английском;
- multi-arch контейнеры и пакеты DEB/RPM.

Известные блокеры на момент этой фиксации:

- полный backend suite красный: 39 тестов прошли, 12 упали — главным образом
  из-за изоляции `/config` и одного незавершённого fake Sonarr;
- Ruff показывает 8 ошибок, mypy — 27 ошибок, ESLint — 1 ошибку и 2
  предупреждения; production build frontend проходит;
- tag workflow собирает и публикует артефакты без полного набора quality gates;
- ручные задания хранятся в памяти и не восстанавливаются после рестарта;
- у runtime-конфигурации нет явной версии схемы и последовательности миграций;
- частичное обновление запросов Seerr при удалении эпизодов не завершено;
- OIDC claims декодируются, но не проходят полную проверку JWKS/подписи,
  issuer, audience, expiry и nonce;
- профили можно сохранять, но runtime выбирает только по одному активному
  Radarr, Sonarr, Seerr, Jellyfin и downloader.

Это датированный снимок. Перед использованием этих чисел в новой задаче, PR
или решении о релизе проверки нужно повторить.

## Прогресс по этапам

### v0.2.12 — завершён 2026-08-11

- Восстановлен зелёный baseline: проходят 51 backend-тест, Ruff format/lint,
  strict mypy, ESLint и production build frontend.
- Добавлены обязательные проверки PR и `main`: backend, frontend, startup smoke
  контейнера и smoke-тесты установленных DEB/RPM.
- Tag release workflow теперь ждёт полный quality gate и только после него
  публикует пакеты, checksums и multi-architecture контейнер.
- Проверенный [релиз v0.2.12](https://github.com/mambastick/Cleanarr/releases/tag/v0.2.12)
  опубликован из коммита `9782504`; его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31510458986)
  успешно завершён для `linux/amd64` и `linux/arm64`.

### v0.3.0 — завершён 2026-08-12

- Добавлены адаптеры qBittorrent, Transmission legacy/JSON-RPC 2.0, Deluge Web
  JSON-RPC и rTorrent XML-RPC за единым контрактом удаления.
- Включена одновременная маршрутизация нескольких Radarr, Sonarr и смешанных
  torrent-клиентов с сохранением владельца при совпадающих integer ID Arr.
- Добавлены индивидуальные политики immediate/keep/defer и сопоставление
  qBittorrent v1/v2 hybrid identifiers. Durable automatic retry остаётся частью
  этапа v0.4.0.
- Добавлены полный UI настройки профилей и автоматизированные protocol contract
  tests. Сертификация на реальных версиях сервисов остаётся gate этапа v0.9.
- Коммит `b2b5ae2` проверен 73 backend-тестами, Ruff format/lint, strict mypy,
  ESLint, production build frontend, package/container smoke-тестами и
  browser-проходом настройки смешанного набора downloader-клиентов.
- Проверенный [релиз v0.3.0](https://github.com/mambastick/Cleanarr/releases/tag/v0.3.0)
  опубликован из коммита `894b393`; его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31550224512)
  успешно завершён с DEB/RPM и GHCR-образом для `linux/amd64` и `linux/arm64`.

Следующий активный этап — **v0.4.0**: завершение deletion/Seerr flows,
идемпотентная обработка webhook и durable retry scheduling.

### v0.4.0 — реализация продолжается

- Удаление эпизода теперь очищает только связанные проблемы Seerr. Поскольку
  запросы Seerr относятся ко всему сезону, CleanArr сохраняет запрос с
  машинно-читаемой причиной `partial_request_retained`, пока event и inventory
  Sonarr не докажут охват всего сезона; только после этого сезон удаляется из
  запроса либо удаляется ставший пустым запрос.
- Seerr теперь используется как каноническое имя в domain, API, UI, логах и
  сохранённой конфигурации. Существующие SQLite/JSON-профили `jellyseerr`
  переписываются без потери данных; старые переменные окружения и скрытые
  маршруты configuration API остаются совместимыми псевдонимами.
- Коммит `ff1bb1a` проверен 78 backend-тестами, Ruff format/lint, strict mypy,
  ESLint, production build frontend, container/package smoke-тестами и
  browser-проходом создания канонического профиля Seerr. Его
  [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31556760557)
  успешно завершил все обязательные jobs.
- Ручное удаление теперь требует точного dry-run preflight с устойчивыми media
  identifiers/path, Arr instance, download client/hash, изменениями
  Seerr/Jellyfin и всеми структурированными safety-пропусками. Сервер связывает
  подтверждение с SHA-256 канонического плана, отклоняет ошибочный или
  изменившийся план и повторно проверяет его перед первой мутацией.
- Ручные задания, resolved event, подтверждённый preflight, частичный результат,
  номер попытки и время retry сохраняются в SQLite. После частичной ошибки план
  пересчитывается и повторяется; после рестарта процесс продолжает работу из
  сохранённого event и не зависит от уже удалённой записи Arr. Ошибка удаления
  torrent блокирует зависимые удаления Arr, Seerr и Jellyfin, чтобы ownership
  evidence сохранился для следующей безопасной попытки.
- Версия 1 схемы SQLite — последовательная аддитивная миграция с неверсионированной
  БД v0.3. Автотесты проверяют обновление, повторный запуск, отклонение более
  новой схемы, проверенный backup и restore без потери config/activity; команды
  rollback для контейнера и нативных пакетов документированы на двух языках.
- Коммит `c1ed854` проверен 87 backend-тестами, Ruff format/lint, strict mypy,
  ESLint, production build frontend, container и установленными DEB/RPM
  smoke-тестами, а также browser-проходом просмотра плана и отправки с его
  hash. Его [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31559076267)
  успешно завершил все обязательные jobs.
- Версия 2 схемы SQLite добавляет персистентный ledger webhook events. Успешное
  событие подавляется семь дней в памяти и после рестарта; partial failure и
  ignored намеренно не завершаются, потому что состояние source/downstream
  может измениться. Новый source timestamp создаёт новый event key.
- Единый process-wide safety lock сериализует webhook, фоновые ручные задания и
  старый синхронный endpoint. Консервативный single-instance дизайн исключает
  пересечение работы с одним media entity, torrent hash или path;
  PostgreSQL/HA не входит в границы продукта 1.0.
- Срез duplicate/serialization локально проверен 96 backend-тестами, Ruff
  format/lint, strict mypy, ESLint и production build frontend. После этого
  implementation scope v0.4 завершён; остаётся выпустить проверенный v0.4.0.

## Обязательный scope 1.0

### 1. Torrent-клиенты и маршрутизация

Tier 1:

| Клиент | Требование 1.0 |
| --- | --- |
| qBittorrent | Сохранить текущую поддержку, добавить явную матрицу API/версий и современную аутентификацию там, где она доступна |
| Transmission | Поддержать проверенное старое поколение RPC и новое поколение JSON-RPC 2.0 |
| Deluge | Поддержать аутентифицированный remote API и оба режима удаления |
| rTorrent | Поддержать XML-RPC; ruTorrent считается интерфейсом, а не отдельным движком |

Каждый Tier 1 adapter обязан покрывать:

- health/authentication и определение версии;
- поиск и удаление по BitTorrent v1, v2 и hybrid identifiers, когда их отдают
  Arr и клиент;
- удаление только раздачи либо раздачи вместе с локальными данными;
- идемпотентную обработку уже отсутствующей раздачи;
- таймауты, ошибки аутентификации, partial failure и retry;
- общие пути, паки, cross-seed данные и несколько клиентов;
- необязательную политику сидирования: удалить сразу, оставить раздачу или
  отложить удаление до заданного ratio/time.

Несколько Radarr/Sonarr/download-client должны работать одновременно. CleanArr
должен направлять удаление в экземпляр и клиент, которым принадлежит объект, а
не полагаться на одну default-конфигурацию.

### 2. Полные сценарии удаления и Seerr

- Завершить movie, series, season и episode flows. Для диапазона эпизодов
  удалять связанные проблемы Seerr и обновлять сезонный запрос только тогда,
  когда событие доказанно охватывает весь сезон; иначе сохранять запрос с явной
  причиной безопасности, потому что у Seerr нет модели запроса отдельных
  эпизодов.
- Использовать актуальное имя **Seerr**, сохранив чтение и миграцию старой
  Jellyseerr-конфигурации.
- Сохранять строгое сопоставление и показывать причину каждого пропуска.
- Показывать точный preflight/preview: media entity, Arr instance, download
  client, hash/path, downstream mutations и safety decision.
- Сделать webhook и ручное удаление идемпотентными.
- Сохранять частичный прогресс и безопасно продолжать/retry после ошибки
  downstream-сервиса или рестарта процесса.
- Сериализовать параллельную работу с одним media entity, torrent или path.

### 3. Жизненный цикл данных и обновления

- Ввести явные версии схемы БД и runtime-конфигурации.
- Поддерживать последовательные протестированные forward migrations.
- Проверять обновление с последнего стабильного 0.x на каждый release candidate
  1.0.
- Создавать или требовать проверенный backup перед разрушительной миграцией.
- Документировать и тестировать rollback/restore для контейнеров и нативных
  пакетов.
- Добавить безопасный экспорт/импорт конфигурации с удалением секретов.
- Персистентно хранить ручные задания и данные для их безопасного продолжения
  или сверки после рестарта.

### 4. Security baseline

- Проверять OIDC ID token через metadata и JWKS: signature, algorithm, issuer,
  audience, expiry, state и nonce; использовать PKCE, если его поддерживает
  провайдер.
- Разрешать доступ только явно настроенным users/groups/claims, а не каждому
  пользователю, принятому IdP.
- Добавить throttling входа и CSRF/Origin-защиту cookie-auth mutations.
- Сохранять безопасные cookie при документированных reverse-proxy схемах.
- Удалять credentials и tokens из логов, activity data, export и support bundle.
- Добавить dependency/container scanning, SBOM и подписанные/provenanced
  release artifacts.

### 5. Quality gates и совместимость

Обязательные проверки pull request:

- полный backend pytest suite;
- Ruff format/lint и strict mypy;
- frontend type-check, ESLint и production build;
- сборка Docker image и startup smoke test;
- сборка DEB/RPM и installation smoke tests;
- contract tests каждого Tier 1 download client;
- сценарии всех item types, pack/shared/cross-seed safety, duplicate events,
  partial failures, restart recovery и multi-instance routing.

Перед 1.0 release candidate должен пройти end-to-end проверки на реальных
поддерживаемых версиях Jellyfin, Radarr, Sonarr, Seerr и каждого Tier 1 клиента.
Результат публикуется в compatibility matrix.

### 6. Эксплуатация и поддержка

- Структурированные error/action codes и correlation IDs всей цепочки удаления.
- Prometheus-compatible метрики без media names и credentials в labels.
- Безопасный support bundle: версия CleanArr, версии downstream-сервисов,
  health summary, форма конфигурации и последние error codes.
- Полная русская и английская документация: установка, обновление,
  backup/restore, reverse proxy и SSO, каждый download client, safety model,
  troubleshooting и release rollback.
- Опубликованная политика совместимости и deprecation для серии 1.x.

## Явные non-goals для 1.0

Эти возможности могут появиться позже, но не блокируют 1.0:

- Plex и Emby как источники событий удаления;
- Lidarr, Readarr, Whisparr и другие Arr-приложения;
- SABnzbd, NZBGet и другие Usenet-клиенты;
- PostgreSQL, горизонтальное масштабирование и HA;
- мобильные приложения, plugin marketplace и дополнительные языки UI.

Перенос non-goal в обязательный scope 1.0 является отдельным продуктовым
решением и должен явно менять этот roadmap.

## Последовательность релизов

| Версия | Результат этапа |
| --- | --- |
| 0.2.12 | Зелёные backend/frontend проверки и CI, блокирующий некорректный релиз |
| 0.3.0 | Tier 1 torrent adapters и одновременная multi-instance маршрутизация |
| 0.4.0 | Полные deletion/Seerr сценарии, idempotency, durable retry и safety tests |
| 0.5.0 | Версионированные миграции, backup/restore, security baseline, метрики и support tooling |
| 0.9.0 | Feature freeze, compatibility matrix, репетиция миграции и публичные release candidates |
| 1.0.0 | Стабильный контракт после выполнения всех критериев ниже |

Границы промежуточных версий могут меняться, но критерии 1.0 нельзя молча
ослаблять.

## Критерии выпуска 1.0

- Все обязательные CI checks проходят из чистого checkout.
- Каждый Tier 1 клиент и каждая заявленная версия dependency проходят contract
  и end-to-end сценарии.
- Обновление с v0.2.11/latest 0.x и rollback с release candidate 1.0 доказаны на
  реальном backup с восстановлением данных.
- Нет незакрытых data-loss defects, security-critical defects и P0/P1 blockers.
- Хотя бы один release candidate проверен независимыми установками, вместе
  покрывающими все Tier 1 клиенты и распространённые multi-instance схемы.
- Документация, compatibility matrix, checksums, SBOM и подписанные release
  artifacts опубликованы одновременно.
