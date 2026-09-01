# AGENTS.md — CleanArr

Этот файл задаёт общий контракт разработки CleanArr. Читать его до планирования,
делегации, изменения кода, документации или release-артефактов. Наличие команды
или существующего поведения в репозитории не отменяет safety, architecture и
quality-границы ниже.

## Область действия и источники истины

CleanArr — один Git-репозиторий с backend, frontend, deployment, packaging и
публичной документацией. Перед работой:

1. определите абсолютный путь через `pwd -P` и убедитесь, что находитесь в
   репозитории CleanArr;
2. прочитайте этот файл, `README.md`, относящиеся к задаче документы и обе версии
   roadmap;
3. проверьте branch, HEAD, upstream, remote и `git status`;
4. сохраните все несвязанные пользовательские изменения и stage делайте только
   по явным путям.

Источники истины разделены по назначению:

- `docs/ROADMAP.md` и `docs/ROADMAP_RU.md` — синхронизированный продуктовый
  roadmap, release order, acceptance gates и non-goals;
- этот файл — architecture, safety, delegation и final-review contract;
- `CONTRIBUTING.md` и `CONTRIBUTING_RU.md` — Git/PR-механика;
- manifests, lockfiles, CI workflows и scripts — существующие команды и точные
  версии;
- compatibility, safety, operations и release guides — публичные контракты
  эксплуатации.

Roadmap содержит датированные snapshots. Перед использованием counts, versions
или claims перепроверьте живой checkout и воспроизводимые gates. Если документы
расходятся, применяйте более ограничительную safety-границу и остановите
mutation до разрешения противоречия.

Любое продуктовое решение, меняющее scope, acceptance criteria, release order
или non-goals, обновляет обе версии roadmap в одном change. Публичные docs и
release notes также поддерживаются одновременно на английском и русском.

## Продуктовый контракт

CleanArr — safety-first orchestrator для цепочки:

`Jellyfin -> Radarr/Sonarr -> Seerr -> torrent clients`

Стабильный контракт 1.0 охватывает qBittorrent, Transmission, Deluge и rTorrent
через XML-RPC. ruTorrent и Flood являются frontend, а не отдельными download
engines. Post-1.0 UX, batch operations, download monitoring и playback insights
расширяют продукт, но не ослабляют контракт удаления 1.0.

Обязательные инварианты:

1. Неоднозначное ownership или неполные destructive evidence всегда дают
   fail-closed: показать причину и пропустить действие.
2. Новая установка остаётся в dry-run до явного решения администратора.
3. Shared files, packs, cross-seed, hardlinks и multi-client routing нельзя
   удалять без явного доказательства и regression tests.
4. Connection success не является поддержкой интеграции: нужны version matrix,
   protocol/contract tests и failure scenarios.
5. Preflight должен быть точным, mutation-free и привязанным hash к
   подтверждаемой операции. Изменившийся plan требует нового подтверждения.
6. Batch deletion состоит из проверяемых item-level plans и одного hash-bound
   batch confirmation. Partial outcome не маскируется как общий success.
7. Playback/watch data — сигнал для сортировки и рекомендации, но не доказательство
   ownership и не разрешение удалить torrent или media.
8. Missing, stale или conflicting watch/download data считается unknown, а не
   unwatched/eligible.
9. Stop/pause seeding — обратимое действие, отличное от удаления torrent entry и
   данных. Эти команды, permissions, состояния и audit trail не смешиваются.
10. Database/config changes требуют ordered versioned migration, upgrade test с
    последнего stable release, backup path и rollback/restore procedure.
11. Release запрещён при красном обязательном backend, frontend, package,
    container, security или compatibility gate.

Plex, Emby, дополнительные Arr/Usenet applications, PostgreSQL/HA, mobile apps
и новые UI languages не входят в обязательный scope без явного изменения
roadmap.

## Архитектурные границы

Backend использует Python 3.12, FastAPI, Pydantic v2, httpx и SQLite. Направление
зависимостей:

```text
api -> application -> domain
infrastructure -> application/domain ports
```

- `domain/` не импортирует FastAPI, HTTP clients, SQLite или UI schemas;
- `application/` владеет use cases, safety decisions и orchestration;
- `infrastructure/` реализует внешние clients, persistence, config и adapters;
- `api/` отвечает за transport, authentication, schemas и status mapping, но не
  дублирует business rules;
- внешний service response, path, identifier, tracker data и media metadata
  считаются недоверенным вводом;
- любой background state machine имеет явные queued/running/retryable/failed/
  completed/cancelled semantics, bounded retries и recovery after restart.

Frontend использует React 19, TypeScript strict, Vite, Tailwind CSS v4 и
repository-owned component source. Новая работа не должна бесконечно расширять
`frontend/src/cleanarr-app.tsx`: при изменении связного сценария выделяйте
feature components, hooks, API types и presentation helpers с ясным ownership.
Shared `components/ui` содержит primitives, а product flow и data fetching не
переносятся в generic UI wrappers.

API и TypeScript types меняются согласованно. Строковые backend messages не
должны быть единственным машинно-читаемым контрактом: для новых состояний
используйте structured codes и локализуйте user-facing copy во frontend.

## UI system и interaction contract

Для всего CleanArr действует один UI stack:

- **shadcn/ui** — базовые accessible primitives, layout и form controls;
- **Animate UI** на совместимом Base UI primitive — tabs, purposeful motion и
  animated Lucide icons;
- **React Bits** — только выбранные декоративные или presentation-level effects,
  не замена Dialog, Alert Dialog, Select, Checkbox, Tabs, form semantics или
  destructive confirmation;
- **Motion** — общий animation runtime, уже присутствующий в проекте.

Не добавляйте четвёртую параллельную component system. Registry/code-copy
компоненты становятся локальным исходным кодом, проходят review, приводятся к
CleanArr tokens и сопровождаются license/attribution, если это требуется.
React Bits Pro или другой закрытый registry нельзя копировать в публичный
репозиторий без подтверждённой лицензии.

UI rules:

1. Цвет, surface, border, status, focus, radius, spacing, shadow и scrollbar
   задаются semantic tokens. Не размножайте raw light/dark color pairs в feature
   markup.
2. Dark, light и system themes проверяются для каждого изменённого flow. Нативные
   `<select>` и checkbox не используются там, где design-system primitive
   обеспечивает единый themed вариант.
3. Tabs используют один Animate UI wrapper и сохраняют keyboard navigation,
   focus, ARIA relationships, controlled state и `prefers-reduced-motion`.
4. Animated icons сообщают feedback на hover/tap/state change, но не запускают
   бесконечное движение и не являются единственным носителем смысла.
5. Destructive CTA имеет однозначные idle, preparing, ready, submitting,
   success и failure states. Disabled control всегда сопровождается видимой
   причиной; repeated clicking не является способом продолжить flow.
6. Dialog/Alert Dialog обеспечивает focus trap, initial focus, Escape, backdrop,
   labelled title/description и возврат focus к trigger.
7. Technical details доступны по progressive disclosure. Обычный пользователь
   сначала видит понятный outcome: что удалится, что сохранится, где действие
   заблокировано и почему.
8. ScrollArea и scrollbar соответствуют теме, доступны с клавиатуры и не
   создают nested-scroll trap. Fixed panels не перекрывают primary content.
9. Все interactive targets, focus states, contrast и responsive reflow
   проверяются минимум на desktop и mobile. Цель — WCAG 2.2 AA; screenshot не
   доказывает compliance.
10. Новые пользовательские строки добавляются минимум в English/Russian maps;
    fallback не должен показывать mixed-language technical copy.

## Модель работы с архитектором и кодерами

Для сложных implementation-задач действует иерархическая модель: один корневой
агент является архитектором, интегратором и окончательным ревьювером; все
делегированные агенты являются кодерами или advisory reviewers с ограниченным
brief. Делегация ускоряет работу, но не передаёт ответственность за результат.

### Архитектор и окончательный ревьювер

- Роль выполняет корневой `gpt-5.6-sol`, обычно с reasoning `xhigh`; `ultra`
  уместен для destructive safety, migrations, authentication, compatibility,
  cross-cutting architecture и release decisions.
- Корневой чат сохраняет роль архитектора до конца задачи. Не запускайте второй
  `gpt-5.6-sol` без явного запроса пользователя; делегированный agent не
  становится вторым архитектором независимо от model ID.
- Архитектор лично проверяет live Git state, выбирает architecture, делит scope,
  задаёт contracts, разрешает конфликты, читает полный diff и повторяет
  достаточные проверки.
- Coder report — предложение, а не доказательство. Только архитектор принимает
  итоговые trade-offs, scope changes, safety decisions и completion decision.
- Архитектор может оставить у себя critical path, интеграцию и исправление
  неудачного coder pass.
- Только архитектор передаёт результат пользователю, объявляет задачу
  завершённой и выполняет разрешённые commit/push/PR/merge действия после всех
  применимых gates. Release, tag, publication, destructive operation и live
  changes требуют отдельной явной власти пользователя.

### Выбор кодера

Используйте точные model IDs, доступные текущему runtime:

| Модель | Назначение | Ограничение |
| --- | --- | --- |
| `gpt-5.3-codex-spark` | default: exploration, bounded implementation, tests, fixtures, docs, mechanical refactor и первый code pass | Не принимает architecture/safety/release решения; результат проходит полный review архитектора |
| `gpt-5.6-terra` | сложный связный multi-file vertical slice или debugging, который нельзя безопасно декомпозировать для Spark | Не меняет public API, migration history или product scope без решения архитектора |
| `gpt-5.6-luna` | резерв для узкой задачи, когда Spark недоступен/неподходящ, а Terra не оправдан | Не владеет critical path и труднообратимыми решениями |

Spark-first routing применяется, пока runtime подтверждает доступность модели и
отдельный pool. Terra выбирается с записанной причиной: неделимый связный scope,
проверенный blocker/неудовлетворительный Spark pass или недоступность Spark.
Fallback нельзя молча называть исходной моделью.

Кодеру без отдельного разрешения запрещено:

- расширять scope или менять product/architecture baseline;
- ослаблять fail-closed behavior, tests, assertions или quality gates;
- менять public API, migration chain, auth/security boundary, compatibility
  claims или release contract;
- выполнять commit, push, merge, tag, release, destructive operation или live
  mutation;
- продолжать при неизвестных пользовательских изменениях, конфликте инструкций
  или отсутствующем обязательном решении.

### Делегация и изоляция

1. Делегируйте только самостоятельную bounded-задачу с полезным артефактом.
2. Read-only exploration и review можно выполнять параллельно.
3. Два write-enabled агента не изменяют один checkout одновременно. Для
   параллельной записи используйте отдельные worktree/branches с фиксированным
   base и непересекающимся ownership файлов; пересекающийся scope выполняется
   последовательно.
4. Перед делегацией архитектор фиксирует absolute path, branch, base SHA,
   upstream divergence, `git status` и существующие изменения. Dirty checkout
   передаётся только с явной границей ownership.
5. Brief кодера обязан включать task ID, role/model, одну цель, in/out of scope,
   file ownership, принятые решения, forbidden actions, acceptance criteria,
   test commands, expected report и stop conditions.
6. Кодер сначала читает этот файл и связанные docs, повторно сверяет Git state и
   сообщает о расхождении с brief до mutation.

### Интеграция и final gate

Архитектор принимает coder output только после того, как:

1. проверил provenance: model, reasoning, checkout, branch и base;
2. прочитал полный diff относительно правильного base;
3. сопоставил change с product flow, security, failure modes, concurrency,
   retry, migration и rollback requirements;
4. проверил содержательность tests, а не только их наличие;
5. повторил релевантные проверки в интегрируемом состоянии;
6. выполнил browser walkthrough изменённых flows и сохранил visual evidence для
   light/dark и responsive states, когда менялся UI.

Не снижайте acceptance criteria, чтобы принять уже написанный код. Возвращайте
конкретные findings кодеру либо исправляйте critical integration самостоятельно.

### Долгая цель и восстановление

Для goal-задачи создайте один устойчивый objective с scope, authority,
acceptance criteria, phases и recovery procedure. Динамический progress храните
в кратком checkpoint вне versioned source либо в явно предназначенном ignored
файле. После каждого крупного этапа фиксируйте Git state, completed/remaining
scope, changed files/commits, decisions, test outcomes, active coder tasks,
blockers и одно следующее действие.

После compaction/resume сначала перечитайте objective, этот файл, roadmap и
checkpoint, затем заново проверьте Git. При расхождении source of truth — Git,
живые файлы и повторяемые проверки; checkpoint исправляется до новых mutation.

## Development и обязательные проверки

Текущие обязательные local gates:

```bash
cd backend
ruff format --check src tests
ruff check src tests
mypy src
pytest -q

cd ../frontend
pnpm lint
pnpm build
```

Для UI interactions, destructive confirmation, selection, async states и theme
regressions одних lint/build недостаточно. Затрагивающая их задача должна
создать или расширить automated frontend test harness (Vitest + Testing Library
и browser-level Playwright либо принятый эквивалент) и включить его в required
CI. Тестируйте single-click submit, duplicate prevention, keyboard/focus,
loading/error/retry, reduced motion, light/dark, responsive overflow и EN/RU.

Backend changes дополнительно покрывают unit/integration/scenario tests. Для
download-client contract changes обязательны fake/protocol tests всех четырёх
Tier 1 adapters и real-service compatibility profile перед compatibility claim.
Database/config changes покрывают forward migration, idempotent rerun,
future-version rejection, upgrade with seeded data, backup и restore/rollback.

Перед completion выполняйте все затронутые CI-equivalent checks. Перед release
также обязательны container/package smoke, dependency/source/container scans,
real-service compatibility и upgrade rehearsal из release guides. Незапущенный
gate указывается как точный blocker; его нельзя описывать как passed.

## Git, документация и release authority

- Обычная задача начинается с tracked Issue и отдельной branch от свежего
  `origin/main`, если пользователь не ограничил работу local-only/read-only.
- Не работайте напрямую в `main`, не делайте force push и не переписывайте
  shared history после начала review.
- Commits имеют focused Conventional Commit subject; stage — по явным путям.
- PR направляется в `main`, связан с Issue и содержит фактические checks, risks,
  migration/rollback notes и visual evidence для UI changes.
- Implementation, API/types, migrations, tests, compatibility docs, operations
  docs и bilingual public copy меняются согласованно.
- Не публикуйте claim о поддержке, доступности или соответствии без
  воспроизводимых evidence.
- Никогда не помещайте credentials, tokens, реальные service URLs, частные
  paths, user identities или media history в committed files, screenshots,
  prompts, logs и reports.
- Merge, tags, releases, artifact/image publication, repository settings,
  destructive actions и production changes требуют явного разрешения
  пользователя и точного target/verification/rollback plan.
