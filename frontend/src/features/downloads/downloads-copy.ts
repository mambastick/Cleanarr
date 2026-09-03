import type { CleanupSort, DownloadActionStatus, DownloadItem, ListingFreshness, SeedReadiness, TorrentOwnership, TorrentState } from "@/lib/downloads"

export type DownloadsLanguage = "en" | "ru"

const en = {
  title: "Downloads", description: "Downloader observations and reversible controls. Unknown evidence is never inferred.", torrents: "Torrents", cleanup: "Cleanup candidates", refresh: "Refresh now", refreshHint: "Refresh evaluates the opt-in stop policy. It never deletes torrents or data.", loading: "Loading downloads…", failed: "Downloads could not be loaded.", retry: "Retry", retryAction: "Retry the same action", unknown: "Unknown", none: "None", partial: "Some information is currently unavailable. CleanArr shows the results it has and does not guess missing values.", partialEvidence: "What is unavailable", dryRun: "Dry run — controls are simulations.", loadMore: "Load more", name: "Name", actions: "Actions", client: "Client", kind: "Kind", state: "State", ownership: "Ownership", progress: "Progress", total: "Total", downloaded: "Downloaded", uploaded: "Uploaded", downloadSpeed: "Download speed", uploadSpeed: "Upload speed", eta: "ETA", added: "Added", completedAt: "Completed", activity: "Last activity", observed: "Observed", metrics: "Metrics", policy: "Policy", policyFacts: "Policy facts", controls: "Controls", pause: "Pause", resume: "Resume", actionUnavailable: "This reversible control is unavailable until CleanArr has fresh, managed ownership evidence and a known torrent state.", pending: "Sending reversible control…", complete: "Control completed.", replay: "The server replayed the same control intent.", simulated: "Control simulated in dry run.", actionFailed: "The control did not complete. No deletion was performed.", reconcile: "The control outcome requires reconciliation. Do not assume it completed.", ambiguous: "The request outcome is uncertain. Retry sends the exact same idempotent intent.", conflict: "That control intent conflicted. Start a new intent after reconciliation.", noTorrents: "No downloads match these filters.", nameUnavailable: "Name unavailable", freshness: "Freshness", category: "Category", tags: "Tags", tracker: "Tracker", candidatesFailed: "Cleanup candidates could not be loaded.", noCandidates: "No cleanup candidates match these filters.", watched: "Watched", neverWatched: "Never watched", cleanupUnknown: "Playback unknown", playback: "Watch state", seeding: "Seeding", selection: "selected", preview: "Review selected cleanup", missingLink: "CleanArr could not verify one safe deletion target, so planning is unavailable.", plan: "Review deletion plan", select: "Select", limit: "A maximum of 50 items can be selected.", overlapping: "This selection overlaps an existing deletion target.", truncated: "The catalogue is larger than the current safe read limit, so these results are not the complete library.", fetched: "Fetched", readiness: "Safety state", watchInfo: "Playback is only a sorting signal. It never authorizes deletion.", sort: "Sort", direction: "Order", ascending: "Ascending", descending: "Descending", media: "Media", all: "All", movies: "Movies", series: "Series", watchedUsers: "Watched users", playCount: "Plays", lastPlayed: "Last played", libraryAge: "Library added", size: "Size", seedRatio: "Seed ratio", seedTime: "Seeding time", filterClient: "Client ID", filterCategory: "Category", filterTag: "Tag", clear: "Clear filters", details: "Data details", sourceStatus: "Source status",
} as const

const BASE_DOWNLOADS_COPY = {
  en,
  ru: { ...en, title: "Загрузки", description: "Наблюдения клиентов и обратимые команды. Неизвестные данные не предполагаются.", torrents: "Торренты", cleanup: "Кандидаты очистки", refresh: "Обновить сейчас", refreshHint: "Обновление оценивает включённую политику остановки. Торренты и данные не удаляются.", loading: "Загружаем загрузки…", failed: "Не удалось загрузить загрузки.", retry: "Повторить", retryAction: "Повторить ту же команду", unknown: "Неизвестно", none: "Нет", partial: "Часть данных сейчас недоступна. CleanArr показывает полученные результаты и ничего не додумывает.", partialEvidence: "Что недоступно", dryRun: "Тестовый режим — команды только симулируются.", loadMore: "Загрузить ещё", name: "Название", actions: "Действия", client: "Клиент", kind: "Тип", state: "Состояние", ownership: "Владение", progress: "Прогресс", total: "Всего", downloaded: "Скачано", uploaded: "Отдано", downloadSpeed: "Скорость скачивания", uploadSpeed: "Скорость отдачи", eta: "Осталось", added: "Добавлено", completedAt: "Завершено", activity: "Последняя активность", observed: "Наблюдалось", metrics: "Метрики", policy: "Политика", policyFacts: "Факты политики", controls: "Команды", pause: "Приостановить", resume: "Возобновить", actionUnavailable: "Эта обратимая команда недоступна, пока нет свежего доказательства управляемого владения и известного состояния торрента.", pending: "Отправляем обратимую команду…", complete: "Команда выполнена.", replay: "Сервер повторил то же намерение команды.", simulated: "Команда смоделирована в тестовом режиме.", actionFailed: "Команда не завершилась. Удаление не выполнялось.", reconcile: "Результат команды требует сверки. Не считайте её выполненной.", ambiguous: "Результат запроса неизвестен. Повтор отправит ровно то же идемпотентное намерение.", conflict: "Конфликт намерения команды. После сверки создайте новое намерение.", noTorrents: "Нет загрузок по этим фильтрам.", nameUnavailable: "Имя недоступно", freshness: "Свежесть", category: "Категория", tags: "Теги", tracker: "Трекер", candidatesFailed: "Не удалось загрузить кандидатов очистки.", noCandidates: "Нет кандидатов очистки по этим фильтрам.", watched: "Просмотрено", neverWatched: "Не просмотрено", cleanupUnknown: "Просмотр неизвестен", playback: "Состояние просмотра", seeding: "Раздача", selection: "выбрано", preview: "Проверить выбранную очистку", missingLink: "CleanArr не смог подтвердить одну безопасную цель удаления, поэтому план пока недоступен.", plan: "Проверить план удаления", select: "Выбрать", limit: "Можно выбрать не более 50 элементов.", overlapping: "Выбор пересекается с существующей целью удаления.", truncated: "Медиатека больше безопасного лимита чтения, поэтому показаны не все элементы.", fetched: "Получено", readiness: "Состояние безопасности", watchInfo: "Данные о просмотре — только сигнал для сортировки. Они никогда не разрешают удаление.", sort: "Сортировка", direction: "Порядок", ascending: "По возрастанию", descending: "По убыванию", media: "Медиа", all: "Все", movies: "Фильмы", series: "Сериалы", watchedUsers: "Пользователей", playCount: "Просмотры", lastPlayed: "Последний просмотр", libraryAge: "Добавлено", size: "Размер", seedRatio: "Коэффициент раздачи", seedTime: "Время раздачи", filterClient: "ID клиента", filterCategory: "Категория", filterTag: "Тег", clear: "Сбросить фильтры", details: "Сведения о данных", sourceStatus: "Статус источника" },
} as const

const EXTRA_COPY = {
  en: {
    close: "Close",
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
    adminOnly: "Viewer access is read-only. An administrator can run controls and deletion plans.",
    jellyfinOnly: "Only in Jellyfin",
    jellyfinOnlyHint: "This movie has no exact Radarr match. The plan will remove only the selected Jellyfin item and will not change Arr or torrent records.",
  },
  ru: {
    close: "Закрыть",
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
    adminOnly: "Для роли «Зритель» доступен только просмотр. Команды и планы удаления запускает администратор.",
    jellyfinOnly: "Только в Jellyfin",
    jellyfinOnlyHint: "У фильма нет точного совпадения в Radarr. План удалит только выбранный элемент Jellyfin и не изменит записи Arr или торрентов.",
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
  }, ownership: { managed: ["Managed", "Управляемый"], unmanaged: ["Unmanaged", "Неуправляемый"], conflict: ["Conflict", "Конфликт"], unknown: ["Unknown", "Неизвестно"] }, freshness: { fresh: ["Fresh", "Свежие"], stale: ["Stale", "Устаревшие"], unknown: ["Unknown", "Неизвестно"] }, readiness: { eligible: ["Eligible", "Готов"], blocked: ["Blocked", "Заблокирован"], excluded: ["Excluded", "Исключён"], disabled: ["Disabled", "Выключен"], unknown: ["Unknown", "Неизвестно"] }, sort: { play_count: ["Play count", "Просмотры"], last_played: ["Last played", "Последний просмотр"], library_added: ["Recently added", "Недавно добавленные"], size: ["Size", "Размер"], seed_ratio: ["Seed ratio", "Рейтинг раздачи"], seed_time: ["Seeding time", "Время раздачи"], seed_readiness: ["Seeding readiness", "Готовность раздачи"] }, action: { queued: ["Queued", "В очереди"], running: ["Running", "Выполняется"], already_in_state: ["Already in requested state", "Уже в запрошенном состоянии"], succeeded: ["Succeeded", "Выполнено"], failed: ["Failed", "Ошибка"], uncertain: ["Uncertain", "Неизвестный результат"], reconcile_required: ["Reconciliation required", "Требуется сверка"], simulated: ["Simulated", "Смоделировано"] },
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
  arr_history_unavailable: ["Arr history could not be read, so torrent details remain unknown.", "Историю Arr не удалось получить, поэтому данные торрента остаются неизвестными."],
  arr_history_incomplete: ["Arr history reached the safe read limit, so torrent details remain unknown.", "История Arr достигла безопасного лимита чтения, поэтому данные торрента остаются неизвестными."],
  no_arr_hashes: ["Arr has no exact torrent identifier for this item; no torrent action will be planned.", "В Arr нет точного идентификатора торрента; действие с торрентом не планируется."],
  downloader_mapping_ambiguous: ["More than one downloader record matches; CleanArr did not choose automatically.", "Найдено несколько записей загрузчика; CleanArr не стал выбирать автоматически."],
  downloader_snapshot_stale: ["Downloader data is too old for a safety decision.", "Данные загрузчика устарели и не подходят для решения о безопасности."],
  downloader_ownership_unknown: ["CleanArr could not prove that it manages the matched torrent.", "CleanArr не смог доказать, что управляет найденным торрентом."],
  torrent_state_unknown: ["Torrent state is unknown", "Состояние торрента неизвестно"],
  arr_mapping_unknown: ["No single exact Arr match was found. Arr and torrent records will be left unchanged.", "Одного точного совпадения в Arr не найдено. Записи Arr и торрентов останутся без изменений."],
  jellyfin_catalog_unavailable: ["Jellyfin did not return its media catalogue.", "Jellyfin не вернул каталог медиатеки."],
  jellyfin_catalog_truncated: ["The Jellyfin catalogue exceeded the safe read limit; this is not the complete library.", "Каталог Jellyfin превысил безопасный лимит чтения; показана не вся медиатека."],
  jellyfin_users_unavailable: ["Jellyfin users could not be read, so watch status remains unknown.", "Пользователей Jellyfin не удалось получить, поэтому статус просмотра неизвестен."],
  jellyfin_users_truncated: ["Not every Jellyfin user fit within the safe read limit, so watch status remains unknown.", "Не все пользователи Jellyfin вошли в безопасный лимит чтения, поэтому статус просмотра неизвестен."],
  jellyfin_playback_unavailable: ["Jellyfin did not return playback data.", "Jellyfin не вернул данные о просмотрах."],
  jellyfin_playback_partial: ["Playback data is incomplete for one or more Jellyfin users.", "Данные о просмотрах неполны хотя бы для одного пользователя Jellyfin."],
  radarr_catalog_unavailable: ["Radarr did not return its movie catalogue.", "Radarr не вернул каталог фильмов."],
  sonarr_catalog_unavailable: ["Sonarr did not return its series catalogue.", "Sonarr не вернул каталог сериалов."],
  arr_history_truncated: ["Some Arr history was not loaded because the bounded read limit was reached.", "Часть истории Arr не загружена: достигнут ограниченный лимит чтения."],
  refresh_failed: ["Downloader data could not be refreshed.", "Не удалось обновить данные загрузчика."],
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
