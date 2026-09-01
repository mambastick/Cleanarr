import type { CleanupSort, DownloadActionStatus, DownloadItem, ListingFreshness, SeedReadiness, TorrentOwnership, TorrentState } from "@/lib/downloads"

export type DownloadsLanguage = "en" | "ru"

const en = {
  title: "Downloads", description: "Downloader observations and reversible controls. Unknown evidence is never inferred.", torrents: "Torrents", cleanup: "Cleanup candidates", refresh: "Refresh now", refreshHint: "Refresh evaluates the opt-in stop policy. It never deletes torrents or data.", loading: "Loading downloads…", failed: "Downloads could not be loaded.", retry: "Retry", retryAction: "Retry the same action", unknown: "Unknown", none: "None", partial: "Some sources are partial or unavailable. Unknown values are not inferred.", partialEvidence: "Failure evidence", dryRun: "Dry run — controls are simulations.", loadMore: "Load more", client: "Client", kind: "Kind", state: "State", ownership: "Ownership", progress: "Progress", total: "Total", downloaded: "Downloaded", uploaded: "Uploaded", downloadSpeed: "Download speed", uploadSpeed: "Upload speed", eta: "ETA", added: "Added", completedAt: "Completed", activity: "Last activity", observed: "Observed", metrics: "Metrics", policy: "Policy", policyFacts: "Policy facts", controls: "Controls", pause: "Pause", resume: "Resume", actionUnavailable: "This reversible control is unavailable until CleanArr has fresh, managed ownership evidence and a known torrent state.", pending: "Sending reversible control…", complete: "Control completed.", replay: "The server replayed the same control intent.", simulated: "Control simulated in dry run.", actionFailed: "The control did not complete. No deletion was performed.", reconcile: "The control outcome requires reconciliation. Do not assume it completed.", ambiguous: "The request outcome is uncertain. Retry sends the exact same idempotent intent.", conflict: "That control intent conflicted. Start a new intent after reconciliation.", noTorrents: "No downloads match these filters.", nameUnavailable: "Name unavailable", freshness: "Freshness", category: "Category", tags: "Tags", tracker: "Tracker", candidatesFailed: "Cleanup candidates could not be loaded.", noCandidates: "No cleanup candidates match these filters.", watched: "Watched", neverWatched: "Never watched", cleanupUnknown: "Playback unknown", selection: "selected", preview: "Review selected cleanup", missingLink: "Deletion planning is unavailable because no safe library link was provided.", plan: "Review deletion plan", select: "Select", limit: "A maximum of 50 items can be selected.", overlapping: "This selection overlaps an existing deletion target.", truncated: "The candidate source was truncated; results are incomplete.", fetched: "Fetched", readiness: "Seeding readiness", watchInfo: "Playback is only a sorting signal. It never authorizes deletion.", sort: "Sort", direction: "Order", ascending: "Ascending", descending: "Descending", media: "Media", all: "All", movies: "Movies", series: "Series", watchedUsers: "Watched users", playCount: "Plays", lastPlayed: "Last played", libraryAge: "Library added", size: "Size", seedRatio: "Seed ratio", seedTime: "Seeding time", filterClient: "Client ID", filterCategory: "Category", filterTag: "Tag", clear: "Clear filters", details: "Technical details", sourceStatus: "Source status",
} as const

const BASE_DOWNLOADS_COPY = {
  en,
  ru: { ...en, title: "Загрузки", description: "Наблюдения клиентов и обратимые команды. Неизвестные данные не предполагаются.", torrents: "Торренты", cleanup: "Кандидаты очистки", refresh: "Обновить сейчас", refreshHint: "Обновление оценивает включённую политику остановки. Торренты и данные не удаляются.", loading: "Загружаем загрузки…", failed: "Не удалось загрузить загрузки.", retry: "Повторить", retryAction: "Повторить ту же команду", unknown: "Неизвестно", none: "Нет", partial: "Часть источников недоступна или вернула неполные данные. Неизвестные значения не предполагаются.", partialEvidence: "Данные об ошибках", dryRun: "Тестовый режим — команды только симулируются.", loadMore: "Загрузить ещё", client: "Клиент", kind: "Тип", state: "Состояние", ownership: "Владение", progress: "Прогресс", total: "Всего", downloaded: "Скачано", uploaded: "Отдано", downloadSpeed: "Скорость скачивания", uploadSpeed: "Скорость отдачи", eta: "Осталось", added: "Добавлено", completedAt: "Завершено", activity: "Последняя активность", observed: "Наблюдалось", metrics: "Метрики", policy: "Политика", policyFacts: "Факты политики", controls: "Команды", pause: "Приостановить", resume: "Возобновить", actionUnavailable: "Эта обратимая команда недоступна, пока нет свежего доказательства управляемого владения и известного состояния торрента.", pending: "Отправляем обратимую команду…", complete: "Команда выполнена.", replay: "Сервер повторил то же намерение команды.", simulated: "Команда смоделирована в тестовом режиме.", actionFailed: "Команда не завершилась. Удаление не выполнялось.", reconcile: "Результат команды требует сверки. Не считайте её выполненной.", ambiguous: "Результат запроса неизвестен. Повтор отправит ровно то же идемпотентное намерение.", conflict: "Конфликт намерения команды. После сверки создайте новое намерение.", noTorrents: "Нет загрузок по этим фильтрам.", nameUnavailable: "Имя недоступно", freshness: "Свежесть", category: "Категория", tags: "Теги", tracker: "Трекер", candidatesFailed: "Не удалось загрузить кандидатов очистки.", noCandidates: "Нет кандидатов очистки по этим фильтрам.", watched: "Просмотрено", neverWatched: "Не просмотрено", cleanupUnknown: "Просмотр неизвестен", selection: "выбрано", preview: "Проверить выбранную очистку", missingLink: "Планирование удаления недоступно: безопасная ссылка на медиатеку не предоставлена.", plan: "Проверить план удаления", select: "Выбрать", limit: "Можно выбрать не более 50 элементов.", overlapping: "Выбор пересекается с существующей целью удаления.", truncated: "Источник кандидатов усечён; результаты неполные.", fetched: "Получено", readiness: "Готовность раздачи", watchInfo: "Данные о просмотре — только сигнал для сортировки. Они никогда не разрешают удаление.", sort: "Сортировка", direction: "Порядок", ascending: "По возрастанию", descending: "По убыванию", media: "Медиа", all: "Все", movies: "Фильмы", series: "Сериалы", watchedUsers: "Пользователей", playCount: "Просмотры", lastPlayed: "Последний просмотр", libraryAge: "Добавлено", size: "Размер", seedRatio: "Рейтинг раздачи", seedTime: "Время раздачи", filterClient: "ID клиента", filterCategory: "Категория", filterTag: "Тег", clear: "Сбросить фильтры", details: "Технические сведения", sourceStatus: "Статус источника" },
} as const

const EXTRA_COPY = {
  en: {
    inProgress: "The server still reports this control in progress. Refresh or retry the same intent; do not assume success.",
    readinessReason: "Readiness reason",
    torrentState: "Torrent state",
    torrentCount: "Matched torrents",
    source: "Data source",
    sourceJellyfin: "Standard Jellyfin API",
    unavailableReason: "Unavailable reason",
    latestAction: "Latest reversible control",
    actionSource: "Source",
    actionAttempts: "Attempts",
    actionUpdated: "Updated",
  },
  ru: {
    inProgress: "Сервер всё ещё считает команду выполняющейся. Обновите данные или повторите то же намерение; не считайте это успехом.",
    readinessReason: "Причина готовности",
    torrentState: "Состояние торрента",
    torrentCount: "Найдено торрентов",
    source: "Источник данных",
    sourceJellyfin: "Стандартный API Jellyfin",
    unavailableReason: "Причина недоступности",
    latestAction: "Последняя обратимая команда",
    actionSource: "Источник",
    actionAttempts: "Попытки",
    actionUpdated: "Обновлено",
  },
} as const

export const DOWNLOADS_COPY = {
  en: { ...BASE_DOWNLOADS_COPY.en, ...EXTRA_COPY.en },
  ru: { ...BASE_DOWNLOADS_COPY.ru, ...EXTRA_COPY.ru },
} as const

export type DownloadsCopy = (typeof DOWNLOADS_COPY)[DownloadsLanguage]

const baseLabels = {
  state: {
    downloading: ["Downloading", "Скачивается"], seeding: ["Seeding", "Раздаётся"], stopped: ["Stopped", "Остановлен"], queued: ["Queued", "В очереди"], checking: ["Checking", "Проверяется"], error: ["Error", "Ошибка"], unknown: ["Unknown", "Неизвестно"], mixed: ["Mixed", "Смешанное"],
  }, ownership: { managed: ["Managed", "Управляемый"], unmanaged: ["Unmanaged", "Неуправляемый"], conflict: ["Conflict", "Конфликт"], unknown: ["Unknown", "Неизвестно"] }, freshness: { fresh: ["Fresh", "Свежие"], stale: ["Stale", "Устаревшие"], unknown: ["Unknown", "Неизвестно"] }, readiness: { eligible: ["Eligible", "Готов"], blocked: ["Blocked", "Заблокирован"], excluded: ["Excluded", "Исключён"], disabled: ["Disabled", "Выключен"], unknown: ["Unknown", "Неизвестно"] }, sort: { play_count: ["Play count", "Просмотры"], last_played: ["Last played", "Последний просмотр"], library_added: ["Library added", "Добавлено"], size: ["Size", "Размер"], seed_ratio: ["Seed ratio", "Рейтинг раздачи"], seed_time: ["Seeding time", "Время раздачи"], seed_readiness: ["Seeding readiness", "Готовность раздачи"] }, action: { queued: ["Queued", "В очереди"], running: ["Running", "Выполняется"], already_in_state: ["Already in requested state", "Уже в запрошенном состоянии"], succeeded: ["Succeeded", "Выполнено"], failed: ["Failed", "Ошибка"], uncertain: ["Uncertain", "Неизвестный результат"], reconcile_required: ["Reconciliation required", "Требуется сверка"], simulated: ["Simulated", "Смоделировано"] },
} as const

const labels = {
  ...baseLabels,
  state: { ...baseLabels.state, not_present: ["Not present", "Нет в клиенте"] },
} as const

export function enumLabel(language: DownloadsLanguage, group: "state", value: TorrentState | "mixed" | "not_present"): string
export function enumLabel(language: DownloadsLanguage, group: "ownership", value: TorrentOwnership): string
export function enumLabel(language: DownloadsLanguage, group: "freshness", value: ListingFreshness): string
export function enumLabel(language: DownloadsLanguage, group: "readiness", value: SeedReadiness): string
export function enumLabel(language: DownloadsLanguage, group: "sort", value: CleanupSort): string
export function enumLabel(language: DownloadsLanguage, group: "action", value: DownloadActionStatus): string
export function enumLabel(language: DownloadsLanguage, group: keyof typeof labels, value: string) { return labels[group][value as never]?.[language === "en" ? 0 : 1] ?? DOWNLOADS_COPY[language].unknown }

const reasonLabels: Record<string, readonly [string, string]> = {
  policy_disabled: ["Policy disabled", "Политика выключена"],
  stale_or_unknown_observation: ["Observation is stale or unknown", "Наблюдение устарело или неизвестно"],
  ownership_not_managed: ["Ownership is not managed", "Владение не подтверждено как управляемое"],
  not_seeding: ["Torrent is not seeding", "Торрент не раздаётся"],
  no_configured_threshold: ["No threshold configured", "Порог не настроен"],
  required_metric_unknown: ["A required metric is unknown", "Обязательная метрика неизвестна"],
  thresholds_met: ["Configured thresholds met", "Настроенные пороги достигнуты"],
  thresholds_not_met: ["Configured thresholds not met", "Настроенные пороги не достигнуты"],
  scope_metadata_unknown: ["Scope metadata is unknown", "Метаданные области неизвестны"],
  excluded_category: ["Excluded category", "Категория исключена"],
  excluded_tag: ["Excluded tag", "Тег исключён"],
  outside_include_scope: ["Outside included scope", "Вне разрешённой области"],
  excluded_scope: ["Excluded by policy scope", "Исключено областью политики"],
  target_not_fresh: ["Target is not fresh", "Данные цели несвежие"],
  arr_history_unavailable: ["Arr history unavailable", "История Arr недоступна"],
  arr_history_incomplete: ["Arr history incomplete", "История Arr неполна"],
  no_arr_hashes: ["No exact Arr torrent identifiers", "Нет точных torrent ID из Arr"],
  downloader_mapping_ambiguous: ["Downloader mapping is ambiguous", "Связь с download-клиентом неоднозначна"],
  downloader_snapshot_stale: ["Downloader observation is stale", "Наблюдение download-клиента устарело"],
  downloader_ownership_unknown: ["Downloader ownership is unknown", "Владение в download-клиенте неизвестно"],
  torrent_state_unknown: ["Torrent state is unknown", "Состояние торрента неизвестно"],
  arr_mapping_unknown: ["Exact Arr mapping unavailable", "Точная связь с Arr недоступна"],
  jellyfin_catalog_unavailable: ["Jellyfin catalogue unavailable", "Каталог Jellyfin недоступен"],
  jellyfin_catalog_truncated: ["Jellyfin catalogue truncated", "Каталог Jellyfin усечён"],
  jellyfin_users_unavailable: ["Jellyfin user coverage unavailable", "Охват пользователей Jellyfin недоступен"],
  jellyfin_users_truncated: ["Jellyfin user coverage truncated", "Охват пользователей Jellyfin усечён"],
  jellyfin_playback_unavailable: ["Jellyfin playback unavailable", "Данные просмотра Jellyfin недоступны"],
  jellyfin_playback_partial: ["Jellyfin playback incomplete", "Данные просмотра Jellyfin неполны"],
  radarr_catalog_unavailable: ["Radarr catalogue unavailable", "Каталог Radarr недоступен"],
  sonarr_catalog_unavailable: ["Sonarr catalogue unavailable", "Каталог Sonarr недоступен"],
  arr_history_truncated: ["Arr history truncated", "История Arr усечена"],
  refresh_failed: ["Downloader refresh failed", "Обновление download-клиентов не выполнено"],
}

export function reasonLabel(language: DownloadsLanguage, value: string | null | undefined) {
  if (!value) return DOWNLOADS_COPY[language].unknown
  return reasonLabels[value]?.[language === "en" ? 0 : 1] ?? DOWNLOADS_COPY[language].unknown
}

export function actionResultCopy(text: DownloadsCopy, status: DownloadActionStatus | null) {
  if (status === "succeeded" || status === "already_in_state") return text.complete
  if (status === "simulated") return text.simulated
  if (status === "uncertain") return text.ambiguous
  if (status === "reconcile_required") return text.reconcile
  return text.actionFailed
}

export function actionForItem(item: DownloadItem) { return item.state === "stopped" ? "resume" : ["downloading", "seeding", "queued", "checking"].includes(item.state) ? "pause" : null }
