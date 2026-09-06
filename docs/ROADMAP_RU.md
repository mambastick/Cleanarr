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

### v0.4.0 — завершён 2026-08-12

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
- Финальный implementation-коммит `76e5b71` проверен 96 backend-тестами, Ruff
  format/lint, strict mypy, ESLint, production build frontend, а также
  smoke-тестами контейнера и установленных пакетов. Его
  [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31559810076)
  успешно завершил все обязательные jobs.
- Проверенный [релиз v0.4.0](https://github.com/mambastick/Cleanarr/releases/tag/v0.4.0)
  опубликован из коммита `8f032f4`; его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31560298020)
  успешно завершён с checksums, DEB/RPM для amd64 и arm64 и публичным GHCR-
  манифестом для `linux/amd64` и `linux/arm64`.

### v0.5.0 — завершён 2026-08-12

- Persisted runtime config получил упорядоченную цепочку схем от
  неверсионированного формата v0.4 через версии 1 и 2. Upgrade-тесты сохраняют
  локального администратора и настройки OIDC client, подтверждают fail-closed
  policy defaults, проверяют backup/restore SQLite до обновления и отклоняют
  будущую версию config без перезаписи.
- OIDC authorization-code login теперь проверяет точный discovery issuer и
  HTTPS endpoints, ограниченный размер metadata/JWKS, асимметричную подпись и
  алгоритм ID token, issuer, audience, срок действия, issued-at, nonce и `azp`
  при нескольких audience. PKCE S256 и одноразовый state с привязкой к browser
  обязательны; access token никогда не принимается как ID token.
- Для администрирования через OIDC обязательна явная policy по пользователю,
  группе или required claim. Локальный вход ограничивает попытки по source и
  account. Browser sessions используют семидневную `HttpOnly`,
  `SameSite=Strict` cookie, отдельный CSRF token, same-origin проверки мутаций и
  документированный `Secure` за reverse proxy; dashboard больше не публичен,
  включены базовые security headers.
- Коммит реализации `e493502` проверен 109 backend-тестами, Ruff format/lint,
  strict mypy, ESLint, production build frontend, browser-проходом регистрации,
  настроек и logout, container smoke и установочными smoke-тестами DEB/RPM. Его
  [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31563074725)
  успешно завершил все обязательные jobs.
- Добавлены версионированный export конфигурации без credentials и fail-safe
  merge import. Import сохраняет локальную аутентификацию и существующие
  credentials, отключает каждый импортированный профиль, не удаляет
  отсутствующие в документе профили, вырезает credentials из URL и принудительно
  включает глобальный dry-run.
- Добавлены аутентифицированные Prometheus-метрики с ограниченными
  неидентифицирующими labels, редактированный support bundle с проверенными
  версиями dependencies и correlation ID для результатов обработки и
  структурированных логов. Общий redaction теперь покрывает логи,
  сериализованные activity actions, вложенные diagnostic details и сохранённые
  ошибки ручных заданий.
- Обязательный CI теперь проверяет resolved Python runtime dependencies,
  исходники, lockfiles, deployment configuration, committed secrets и
  установленный контейнер и блокирует исправимые high/critical findings.
  Release workflow создаёт SPDX JSON SBOM и подписанные GitHub build, SBOM и
  artifact attestations, привязанные к digest образа и файлов.
- Коммит реализации `1db8a46` проверен 117 backend-тестами, Ruff format/lint,
  strict mypy, frontend lint/build и dependency audit, Trivy-сканами исходников
  и контейнера, actionlint, container smoke и установочными smoke-тестами
  DEB/RPM. Его [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31565040954)
  успешно завершил все обязательные jobs.
- Проверенный [релиз v0.5.0](https://github.com/mambastick/Cleanarr/releases/tag/v0.5.0)
  опубликован из коммита `04d4db8`; его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31565556759)
  успешно завершил все обязательные quality, native-package,
  multi-architecture image, SBOM, provenance и publication jobs.
- После публикации скачаны все четыре DEB/RPM и три SPDX 2.3 SBOM, проверены все
  checksums и каждая GitHub artifact attestation относительно тега, исходного
  коммита, signer workflow и hosted-runner policy. Build и SBOM attestations
  GHCR-образа также проверены; digest его `linux/amd64` и `linux/arm64`
  манифеста —
  `sha256:5425c1f73ecc4abd6434e9db750a6cc5ddc8f4426d1df028118e97a8fa9e13ca`.

### v0.9.0 — завершён 2026-08-12

- Опубликованы двуязычная compatibility matrix и policy
  compatibility/deprecation 1.x с точными digest-pinned версиями qBittorrent
  5.2.3, Transmission 4.0.6 и 4.1.3, Deluge 2.2.0, rTorrent 0.16.17, Radarr
  6.3.0.10514, Sonarr 4.0.19.2979, Seerr 3.4.1 и Jellyfin 10.11.11. ruTorrent и
  Flood корректно остаются frontend.
- Real-service suite создаёт детерминированную раздачу через каждый Tier 1
  native API и доказывает version/authentication, отказ неверных credentials,
  dry-run, удаление только записи, удаление вместе с данными и идемпотентное
  отсутствие. Стенд обнаружил и позволил исправить сохранение регистра hash в
  Deluge, target argument `execute.throw` rTorrent и прежний health probe
  Jellyfin, проверявший только публичный endpoint.
- Release candidate обновлён из реальных опубликованных контейнеров v0.2.11 и
  v0.5.0 с подготовленными config/activity, после чего выполнен rollback через
  byte-verified backup и успешный запуск каждой исходной версии. Чистый hosted
  [compatibility run](https://github.com/mambastick/Cleanarr/actions/runs/31588845484)
  независимо повторил полный pinned stack и обе репетиции.
- Коммит реализации `1c5547d` и portability fix hosted runner `d215261`
  проверены 118 backend-тестами, Ruff format/lint, strict mypy, frontend
  lint/build, dependency и source/container scans, actionlint, container smoke,
  установочными smoke-тестами DEB/RPM и семью real-service contracts.
- Проверенный [релиз v0.9.0](https://github.com/mambastick/Cleanarr/releases/tag/v0.9.0)
  опубликован из коммита `d215261`; его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31589090793)
  повторил все обязательные quality и compatibility gates до публикации native
  packages, multi-architecture image, SPDX SBOM, provenance и подписанных
  artifact attestations.
- После публикации скачаны все release files, проверены каждый checksum и file
  attestation, а также GHCR attestation. Digest image manifest для
  `linux/amd64` и `linux/arm64` —
  `sha256:c77bffd72ca49279b95a5c1b82e3b20938d702d7016ab759ce11fc39be29de67`.

### v1.0.0 — завершён 2026-08-12

- Версии package и API зафиксированы как 1.0.0 в release-коммите `d8a63c2`.
  Этим установлен документированный safety-first контракт для Jellyfin, Seerr,
  одновременно работающих экземпляров Radarr/Sonarr и всех четырёх Tier 1
  torrent-движков. Неоднозначное владение и неполные доказательства для
  destructive action по-прежнему дают fail-closed, а новая установка по
  умолчанию остаётся в dry-run.
- [Quality run](https://github.com/mambastick/Cleanarr/actions/runs/31590801294)
  финального коммита успешно завершил backend suite (118 passed, 7 live-service
  тестов пропущены в обычном suite), Ruff format/lint, strict mypy, frontend
  lint/build, audit runtime dependencies, scans исходников, secrets,
  конфигурации и установленного image, container smoke и установочные
  smoke-тесты DEB/RPM. Соответствующие локальные Trivy-сканы не обнаружили
  исправимых high/critical findings.
- Три изолированные установки candidate — локальный временный stack, чистый
  hosted [release-candidate run](https://github.com/mambastick/Cleanarr/actions/runs/31591012707)
  и чистый hosted stack tag release — независимо создали полную pinned-матрицу.
  Во всех прошли семь real-service contracts для qBittorrent, обоих поколений
  Transmission, Deluge, rTorrent, Radarr, Sonarr, Seerr и Jellyfin; обычный
  scenario suite дополнительно покрывает одновременную multi-Arr и multi-client
  маршрутизацию.
- Те же локальные и hosted gates обновили заполненные установки из
  опубликованных image v0.2.11 и v0.9.0 до финального candidate, сохранили
  config, schema и activity data, восстановили byte-identical проверенный
  backup и успешно запустили каждую исходную версию после rollback.
- Финальный blocker audit не обнаружил открытых GitHub issues, красных
  обязательных checks или findings на release-пороге security scans. На момент
  публикации нет известных незакрытых data-loss, security-critical или P0/P1
  дефектов.
- Проверенный стабильный [релиз v1.0.0](https://github.com/mambastick/Cleanarr/releases/tag/v1.0.0)
  опубликован из `d8a63c2`. Его [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31591298566)
  повторил все обязательные quality и compatibility gates до публикации
  DEB/RPM для amd64/arm64, трёх SPDX SBOM, checksums, подписанных file
  attestations и multi-architecture GHCR image.
- Независимая проверка после публикации скачала все восемь release assets,
  подтвердила каждый записанный checksum и GitHub file attestation, а также OCI
  provenance. Digest image index для `linux/amd64` и `linux/arm64` —
  `sha256:fd039528eed3326ad0c16d8f36630a4dc5b67962e3c93d3687a768e206979dc5`.

## Принятый post-1.0 workstream

Принято **2026-09-01**. Этот раздел фиксирует следующее продуктовое направление,
но не утверждает, что работа реализована или выпущена. Контракты 1.0 по
fail-closed, dry-run, совместимости, миграциям и quality gates остаются
обязательными.

### 1. Надёжное взаимодействие удаления и первоначальная настройка

- Одно подтверждённое нажатие должно создавать ровно одну задачу удаления.
  Интерфейс явно показывает состояния загрузки плана, готовности, отправки,
  успеха, ошибки и повтора; duplicate submit блокируется, повторные нажатия не
  являются способом продолжить сценарий.
- Пользовательское имя из медиатеки остаётся одинаковым в preview, фоновой
  задаче, activity, retry и batch results. Локализованное display name является
  presentation data и не заменяет стабильные media identifiers или ownership
  evidence.
- Шаг torrent-клиентов в мастере первого запуска учитывает отдельные URL,
  authentication fields, validation, help и connection evidence для
  qBittorrent, Transmission, Deluge и rTorrent. Он позволяет настроить несколько
  клиентов и не выдаёт первый клиент за полную runtime topology.

### 2. Единая design system и доступный destructive UX

- Провести аудит всех frontend surfaces и свести color, status, surface, focus,
  radius, spacing, motion и scrollbar behavior к semantic tokens с проверенной
  согласованностью light, dark и system themes.
- Использовать shadcn/ui как основу accessible components, Animate UI для
  совместимых animated tabs и взаимодействий с Lucide icons, а ограниченный
  набор React Bits — только для presentation polish. Не добавлять независимую
  четвёртую component system и не заменять декоративными компонентами критичные
  form semantics.
- Заменить несогласованные native selects, checkboxes, ad-hoc dialogs, buttons и
  scroll containers проверенными локальными primitives. Соблюдать keyboard
  access, focus restoration, reduced motion, responsive reflow и WCAG 2.2 AA
  contrast/semantics.
- Вместо технического dump показывать progressive deletion plan: понятное
  резюме того, что будет удалено, сохранено, пропущено или заблокировано, а
  technical identifiers и diagnostics раскрывать отдельно.

### 3. Ограниченное массовое удаление

- Добавить явный выбор карточек, видимое количество выбранных элементов,
  действия select-visible/clear и постоянную batch action bar, не превращая всю
  карточку в неоднозначный destructive control.
- Для каждого выбранного элемента строить mutation-free plan, затем привязывать
  точный упорядоченный batch к одному confirmation hash. Изменившийся, failed,
  ambiguous или stale дочерний plan блокирует этот элемент и требует нового
  подтверждения.
- Использовать отдельный accessible confirmation dialog с item types, count,
  estimated size, affected systems, retained torrents и safety blocks. Batch
  submission ограничен на backend, идемпотентен и показывает per-item progress
  и partial outcomes, а не притворяется атомарным между внешними сервисами.

### 4. Загрузки и сигналы для очистки

- Добавить верхнеуровневый раздел **«Загрузки»** с двумя разными представлениями:
  текущее состояние скачивания/раздачи и кандидаты на очистку медиатеки. Не
  смешивать torrent state и watch-derived eligibility в один непрозрачный score.
- Нормализовать read-only state всех четырёх Tier 1 клиентов: client, state,
  progress, size, ratio, seeding time, activity, category/tags при наличии и
  freshness данных. Идемпотентные pause/stop и resume добавляются только после
  документированных semantics и contract tests каждого adapter.
- Добавить явную policy остановки раздачи по заданным ratio/time conditions.
  Evaluation, изменения состояния, failures и retries персистентны и доступны
  для аудита; остановка не является удалением torrent entry или данных.
- Сформировать объяснимые Jellyfin cleanup signals: watched/never-watched/
  unknown, aggregate play count, last played time, library age, size и seeding
  readiness. Missing/stale history остаётся unknown. Первый этап использует эти
  данные только для filters, sorting, recommendations и manual/batch deletion.
- Automatic media deletion, «Скоро удалим», дополнительные historical providers
  и scheduled rules являются последующим opt-in этапом с отдельными preview,
  exclusions, cooling period, migration, recovery и end-to-end safety gate.

### Acceptance gates post-1.0

- Ввести обязательные frontend interaction tests (component и browser level)
  для single-click submit, duplicate prevention, batch confirmation, keyboard/
  focus, loading/error/retry, themes, reduced motion, responsive overflow и
  English/Russian copy.
- Сохранять зелёными полный backend, frontend, package, container, supply-chain,
  upgrade и Tier 1 compatibility gates. Новая adapter command требует fake,
  protocol и pinned real-service evidence до заявления совместимости.
- Версионировать и тестировать каждую новую persisted job, policy, playback или
  batch schema; документировать backup и rollback/restore.
- Не отмечать пункт выполненным только по screenshot или успешному build.
  Требуются воспроизводимые tests и browser walkthrough точных destructive и
  recovery flows.

## Итоговый snapshot v1.1.0 — 2026-09-01

- [Issue #4](https://github.com/mambastick/Cleanarr/issues/4) и
  [PR #5](https://github.com/mambastick/Cleanarr/pull/5) реализовали ограниченный
  post-1.0 scope в release-коммите `ac66ae0`: идемпотентное ручное удаление по
  одному подтверждению, hash-bound batch plans, обратимые pause/resume для
  загрузок, ограниченные playback insights, первоначальную настройку нескольких
  downloader и доступную component system на semantic tokens. Automatic
  deletion и остальные последующие opt-in пункты не входят в этот релиз.
- SQLite schema v5 и прежняя конфигурация v1.1 проверены через последовательное
  обновление, идемпотентность, отказ для будущей версии, проверенный backup и
  rollback. Workstream UI-v2 переводит runtime configuration на schema v4 со
  storage thresholds; этот snapshot не утверждает, что работа выпущена.
  Финальный локальный candidate прошёл 214 backend-тестов с 7
  пропущенными в обычном suite pinned live-service тестами, Ruff format/lint,
  strict mypy, 66 тестов Vitest/Testing Library, 12 browser-тестов
  Playwright/Axe, frontend lint и production build, dependency/source/container
  scans, container smoke и установочные smoke-тесты DEB/RPM.
- Обязательный
  [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/33552452113)
  тега повторил backend, frontend, supply-chain, container и package gates. Его
  чистый compatibility stack прошёл все семь pinned real-service contracts и
  обновил заполненные установки v0.2.11, v0.9.0 и v1.0.0, после чего восстановил
  проверенные backups и успешно запустил каждый исходный релиз.
- Проверенный [релиз v1.1.0](https://github.com/mambastick/Cleanarr/releases/tag/v1.1.0)
  опубликовал четыре пакета DEB/RPM для amd64/arm64, три SPDX SBOM,
  `SHA256SUMS` и публичный multi-architecture GHCR image. Независимая проверка
  после публикации скачала все восемь файлов, подтвердила каждый checksum и
  file provenance attestation, а также OCI provenance. Digest image index для
  `linux/amd64` и `linux/arm64` —
  `sha256:67cadfe8caa795ec5c6a5d9daaf61df25260ffce1f54bf72199aec47f5e37336`.

## Tracked Epic #8 — рабочее пространство Library UI-v2

Epic отслеживается в [GitHub Issue #8](https://github.com/mambastick/Cleanarr/issues/8)
и принят как post-1.1 work. Это план доставки, а не заявление о выпуске. Он
сохраняет fail-closed, dry-run, ownership, freshness, authentication,
migration и quality contracts версии 1.0.

Порядок доставки:

1. **Frontend harness и извлечение логики** — расширить существующее покрытие
   Vitest/Testing Library и Playwright, затем выделить controllers и feature-границы текущего
   интерфейса без изменения production-вида и поведения.
2. **Backend-контракты** — реализовать configuration schema v4, ordered
   migration, storage monitoring, resource-based Library/detail/artwork APIs,
   compatibility, автоматический backup v3, rollback/restore и backend-тесты.
3. **Основа shell** — добавить semantic light/dark tokens, адаптивные
   sidebar/rail/mobile navigation и блоки account/storage, пока не переключая
   production entry point.
4. **Dashboard и Library** — реализовать storage dashboard, poster grid,
   inspector выбранного объекта, устойчивый ограниченный выбор и интеграцию
   single/batch preflight.
5. **Production cutover** — перенести Downloads, Cleanup Candidates, Activity,
   Settings, Setup/Auth/Jobs, удалить устаревший UI, синхронизировать EN/RU docs
   и зафиксировать browser/accessibility/visual evidence и все обязательные gates.

Пять изменений остаются stacked, связаны с Epic #8 и откатываются независимо.
Backend и foundational work могут быть объединены отдельно, но новый shell
становится production default только в финальном cutover; merge, release и
publication требуют отдельного разрешения.

Пока все пять шагов и их gates не завершены, UI-v2 нельзя описывать как
выпущенный или ослабляющий безопасность удаления. Missing, stale, partial и
conflicting watch/download/storage data остаётся `unknown` и не разрешает
destructive action.

### Принятое административное дополнение UI-v2 — 2026-09-03

Результаты аннотированного UI-review расширяют Epic #8 административным
каталогом пользователей и сохраняемыми ролями `admin`/`viewer`. Первая
допущенная identity может создать административную границу; новые SSO identity
после неё по умолчанию получают роль viewer, изменение ролей сохраняет минимум
одного администратора, а viewer session открывает только ограниченные read
projections — без конфигурации, credentials, списка пользователей и mutation.
Database schema 6 добавляет проекцию учётных записей и проходит обычные gates
backup, upgrade, future-version rejection и restore.

В том же дополнении приняты collapsible shell с анимированным active marker,
расширенная информационная архитектура Settings, плотный поток Activity,
плоский список сервисов, ограниченные по высоте прокручиваемые dialogs, cursor
pagination и выбор размера карточек Library, явный сброс selection, мобильная
навигация с safe-area и tooltips у действий без подписи. Это цели реализации,
а не заявление о релизе; они не ослабляют preflight, ownership, freshness или
dry-run contracts.

## Подготовка release candidate v2.0.0 — 2026-09-03

- Пять изменений UI-v2 последовательно влиты через PR
  [#9](https://github.com/mambastick/Cleanarr/pull/9),
  [#10](https://github.com/mambastick/Cleanarr/pull/10),
  [#11](https://github.com/mambastick/Cleanarr/pull/11),
  [#12](https://github.com/mambastick/Cleanarr/pull/12) и
  [#13](https://github.com/mambastick/Cleanarr/pull/13), завершая production
  cutover из
  [Epic #8](https://github.com/mambastick/Cleanarr/issues/8).
- Версия 2.0.0 выбрана потому, что поставка заменяет production UI и вводит
  сохраняемую authorization-границу administrator/viewer. Она не удаляет Tier
  1 adapter, не ослабляет fail-closed deletion behavior и не использует major
  boundary для обхода опубликованной deprecation policy.
- Release candidate переводит SQLite со schema v5 на v6, а runtime
  configuration — со schema v3 на v4. Публикация остаётся заблокированной до
  полного прохождения quality, package, container, security, pinned real-service
  compatibility и latest-stable v1.1.0 upgrade/automatic-backup/rollback gates
  из release commit. Пока эти проверки не пройдут и release tag не будет явно
  разрешён, v2.0.0 остаётся неопубликованным candidate.

### Принятое дополнение по результатам production-feedback v2 — 2026-09-04

- Исправить production-регрессии интерфейса из
  [Issue #16](https://github.com/mambastick/Cleanarr/issues/16): загрузку
  artwork, отступы inspector, детализацию по сезонам, локализованные объяснения
  evidence/activity, сохраняемый прогресс настройки, плоское представление
  семейств сервисов и расположение кнопки фоновых задач.
- Добавить узкий сценарий прямого удаления из Jellyfin для одного фильма,
  когда включённого Radarr нет либо полный актуальный каталог Radarr не содержит
  точного совпадения. План удаляет только точный объект Jellyfin, остаётся
  hash-bound и идемпотентным и непосредственно перед выполнением повторно
  проверяет identity Jellyfin и отсутствие связи с Radarr. Недоступный или
  неоднозначный каталог даёт fail-closed.
- Прямое удаление сериалов Jellyfin и массовый выбор остаются вне scope, пока
  для них не определены столь же явные контракты physical scope и ownership.

### Принятое уточнение предпросмотра удаления — 2026-09-07

- [Issue #39](https://github.com/mambastick/Cleanarr/issues/39) делает конкретные
  торренты и downstream-записи различимыми в предпросмотре одиночного удаления,
  объясняет последствия для файлов и записей и добавляет ограниченные ссылки
  для проверки. Отсутствующие данные явно неизвестны; подтверждение остаётся
  привязанным к просмотренному плану.
- Убрать из shell вход в историю недавних задач; история доступна в «Активности».
  Сохранить доступ к активным фоновым задачам и результату уже отслеживаемой
  работы, возвращая keyboard focus при закрытии панели.
- Сохранить порядок релизов, ownership rules, dry-run по умолчанию и обязательные
  backend/frontend interaction gates. Это не заявление о выпуске.

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
| 1.0.0 | Опубликованный стабильный контракт со всеми выполненными критериями ниже |

Границы промежуточных версий могут меняться, но критерии 1.0 нельзя молча
ослаблять.

## Критерии выпуска 1.0

- [x] Все обязательные CI checks проходят из чистого checkout.
- [x] Каждый Tier 1 клиент и каждая заявленная версия dependency проходят contract
  и end-to-end сценарии.
- [x] Обновление с v0.2.11/latest 0.x и rollback с release candidate 1.0 доказаны на
  реальном backup с восстановлением данных.
- [x] Нет незакрытых data-loss defects, security-critical defects и P0/P1 blockers.
- [x] Хотя бы один release candidate проверен независимыми установками, вместе
  покрывающими все Tier 1 клиенты и распространённые multi-instance схемы.
- [x] Документация, compatibility matrix, checksums, SBOM и подписанные release
  artifacts опубликованы одновременно.
