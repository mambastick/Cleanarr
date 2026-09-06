export type LibraryLanguage = "en" | "ru"

export interface LibraryV2Copy {
  title: string
  description: string
  movies: string
  series: string
  search: string
  sort: string
  added: string
  titleSort: string
  size: string
  ascending: string
  descending: string
  refresh: string
  retry: string
  loadMore: string
  previousPage: string
  nextPage: string
  page: string
  itemsPerPage: string
  cardSize: string
  cardSmall: string
  cardMedium: string
  cardLarge: string
  select: string
  selectMode: string
  selectVisible: string
  exitSelectMode: string
  selected: string
  selectedHidden: string
  clearSelection: string
  batchDelete: string
  noItems: string
  partial: string
  unavailable: string
  catalogChanged: string
  sourceFailure: string
  unknown: string
  noArtwork: string
  movie: string
  seriesType: string
  year: string
  sizeLabel: string
  playback: string
  freshness: string
  playCount: string
  lastPlayed: string
  neverPlayed: string
  seeding: string
  ratio: string
  seededTime: string
  readiness: string
  unknownReasons: string
  safety: string
  safe: string
  blocked: string
  reviewPlan: string
  selectForGroup: string
  additional: string
  technicalDetails: string
  seasons: string
  episodes: string
  close: string
  loadingDetails: string
  addedLabel: string
  deleteUnavailable: string
  selectionLimit: string
  selectionUnavailable: string
  selectionNeedsReview: string
  itemChanged: string
  selectedItemChanged: string
  torrentClient: string
  fresh: string
  stale: string
  ready: string
  notReady: string
  signalUnavailable: string
  watched: string
  season: string
  files: string
  seasonDelete: string
  seasonDeleteHint: string
  seasonJellyfinRetained: string
  seasonBreakdown: string
  evidenceSummary: string
  evidenceComplete: string
  checkedAt: string
}

export const LIBRARY_COPY: Record<LibraryLanguage, LibraryV2Copy> = {
  en: {
    title: "Library", description: "Browse your media and review what can be safely removed.", movies: "Movies", series: "Series", search: "Search library", sort: "Sort", added: "Recently added", titleSort: "Title", size: "Size", ascending: "Ascending", descending: "Descending", refresh: "Refresh", retry: "Retry", loadMore: "Load more", previousPage: "Previous", nextPage: "Next", page: "Page", itemsPerPage: "Items per page", cardSize: "Card size", cardSmall: "Small", cardMedium: "Medium", cardLarge: "Large", select: "Select", selectMode: "Select", selectVisible: "Select visible", exitSelectMode: "Done", selected: "selected", selectedHidden: "hidden", clearSelection: "Clear", batchDelete: "Review deletion plan", noItems: "No library items found.", partial: "Some sources returned incomplete data.", unavailable: "The library source is unavailable.", catalogChanged: "The library changed while it was loading. Review the refreshed list.", sourceFailure: "What is unavailable", unknown: "Unknown", noArtwork: "Artwork unavailable", movie: "Movie", seriesType: "Series", year: "Year", sizeLabel: "On disk", playback: "Playback", freshness: "Data freshness", playCount: "Play count", lastPlayed: "Last played", neverPlayed: "Not played", seeding: "Seeding", ratio: "Seed ratio", seededTime: "Seeded time", readiness: "Readiness", unknownReasons: "Why some values are unknown", safety: "Safety", safe: "Safety evidence available", blocked: "Blocked", reviewPlan: "Review deletion plan", selectForGroup: "Select for group", additional: "Data details", technicalDetails: "Item details", seasons: "Seasons", episodes: "Episodes", close: "Close", loadingDetails: "Loading current safety evidence…", addedLabel: "Added", deleteUnavailable: "Deletion planning is unavailable for this item.", selectionLimit: "A batch can contain at most 50 items.", selectionUnavailable: "This item is not linked to a safe deletion target.", selectionNeedsReview: "Some selected items belong to an older catalog. Open them again or clear the selection.", itemChanged: "This item changed or is no longer linked to Arr.", selectedItemChanged: "A selected item changed. Refresh the library.", torrentClient: "Torrent client", fresh: "Current", stale: "Stale", ready: "Ready", notReady: "Not ready", signalUnavailable: "The source did not provide enough current evidence.", watched: "Watched", season: "Season", files: "files", seasonDelete: "Delete season", seasonJellyfinRetained: "No unique Jellyfin season match. Direct Jellyfin cleanup will be omitted from the plan.", seasonDeleteHint: "Review a plan for this season before confirming deletion. Other seasons are retained.", seasonBreakdown: "Season breakdown", evidenceSummary: "CleanArr keeps these values unknown instead of guessing.", evidenceComplete: "All available detail sources responded.", checkedAt: "Checked",
  },
  ru: {
    title: "Библиотека", description: "Просматривайте медиатеку и проверяйте, что можно безопасно удалить.", movies: "Фильмы", series: "Сериалы", search: "Поиск по библиотеке", sort: "Сортировка", added: "Недавно добавленные", titleSort: "Название", size: "Размер", ascending: "По возрастанию", descending: "По убыванию", refresh: "Обновить", retry: "Повторить", loadMore: "Загрузить ещё", previousPage: "Назад", nextPage: "Далее", page: "Страница", itemsPerPage: "Элементов на странице", cardSize: "Размер карточек", cardSmall: "Маленькие", cardMedium: "Средние", cardLarge: "Большие", select: "Выбрать", selectMode: "Выбрать", selectVisible: "Выбрать видимые", exitSelectMode: "Готово", selected: "выбрано", selectedHidden: "скрыто", clearSelection: "Очистить", batchDelete: "Проверить план удаления", noItems: "В медиатеке ничего не найдено.", partial: "Часть данных сейчас недоступна. CleanArr показывает полученные результаты и ничего не додумывает.", unavailable: "Источник медиатеки недоступен.", catalogChanged: "Медиатека изменилась во время загрузки. Проверьте обновлённый список.", sourceFailure: "Что недоступно", unknown: "Неизвестно", noArtwork: "Нет обложки", movie: "Фильм", seriesType: "Сериал", year: "Год", sizeLabel: "На диске", playback: "Просмотр", freshness: "Свежесть данных", playCount: "Количество просмотров", lastPlayed: "Последний просмотр", neverPlayed: "Не просмотрено", seeding: "Раздача", ratio: "Коэффициент раздачи", seededTime: "Время раздачи", readiness: "Готовность", unknownReasons: "Почему часть значений неизвестна", safety: "Безопасность", safe: "Данные для проверки доступны", blocked: "Заблокировано", reviewPlan: "Проверить план удаления", selectForGroup: "Выбрать для группы", additional: "Сведения о данных", technicalDetails: "Сведения об элементе", seasons: "Сезоны", episodes: "Эпизоды", close: "Закрыть", loadingDetails: "Загружаем актуальные данные безопасности…", addedLabel: "Добавлено", deleteUnavailable: "Планирование удаления для этого элемента недоступно.", selectionLimit: "В пакет можно выбрать не более 50 элементов.", selectionUnavailable: "Этот элемент не связан с безопасной целью удаления.", selectionNeedsReview: "Часть выбранных элементов относится к старой версии каталога. Откройте их снова или очистите выбор.", itemChanged: "Элемент изменился или больше не связан с Arr.", selectedItemChanged: "Один из выбранных элементов изменился. Обновите библиотеку.", torrentClient: "Torrent-клиент", fresh: "Актуальные", stale: "Устаревшие", ready: "Готово", notReady: "Не готово", signalUnavailable: "Источник не предоставил достаточно актуальных данных.", watched: "Просмотрено", season: "Сезон", files: "файлов", seasonDelete: "Удалить сезон", seasonJellyfinRetained: "Нет однозначной связи с сезоном Jellyfin. Прямое удаление из Jellyfin не войдёт в план.", seasonDeleteHint: "Перед подтверждением проверьте план удаления этого сезона. Остальные сезоны сохранятся.", seasonBreakdown: "По сезонам", evidenceSummary: "CleanArr оставляет эти значения неизвестными, а не подставляет догадки.", evidenceComplete: "Все доступные источники подробностей ответили.", checkedAt: "Проверено",
  },
}

const EVIDENCE_REASONS: Record<string, readonly [string, string]> = {
  jellyfin_not_configured: ["Jellyfin is not configured, so library and playback data cannot be loaded.", "Jellyfin не настроен, поэтому медиатека и данные о просмотрах недоступны."],
  jellyfin_catalog_truncated: ["Only part of the Jellyfin catalogue was loaded because the safe read limit was reached.", "Загружена только часть каталога Jellyfin: достигнут безопасный лимит чтения."],
  jellyfin_users_unavailable: ["The Jellyfin user list could not be read, so playback cannot be verified for everyone.", "Не удалось получить список пользователей Jellyfin, поэтому просмотры нельзя проверить для всех."],
  jellyfin_users_truncated: ["Only part of the Jellyfin user list was loaded, so playback coverage is incomplete.", "Загружена только часть пользователей Jellyfin, поэтому данные о просмотрах неполны."],
  jellyfin_item_unavailable: ["This Arr item is not linked to one exact Jellyfin record, so playback and artwork are unavailable.", "Элемент Arr не связан с одной точной записью Jellyfin, поэтому обложка и просмотры недоступны."],
  jellyfin_playback_unavailable: ["Jellyfin did not return playback data. Check the Jellyfin connection and retry.", "Jellyfin не вернул данные о просмотрах. Проверьте подключение и повторите попытку."],
  jellyfin_playback_partial: ["Playback data is incomplete for one or more Jellyfin users.", "Данные о просмотрах неполны хотя бы для одного пользователя Jellyfin."],
  playback_users_unavailable: ["The Jellyfin user list is unavailable, so playback remains unknown.", "Список пользователей Jellyfin недоступен, поэтому данные о просмотрах остаются неизвестными."],
  playback_read_failed: ["Jellyfin did not return a valid playback response.", "Jellyfin не вернул корректный ответ с данными о просмотрах."],
  playback_scope_incomplete: ["CleanArr could not verify playback for every Jellyfin user.", "CleanArr не смог проверить просмотры для всех пользователей Jellyfin."],
  playback_observation_incomplete: ["Jellyfin did not return a playback record for every expected user.", "Jellyfin не вернул запись просмотра для каждого ожидаемого пользователя."],
  playback_observation_conflict: ["Jellyfin returned conflicting playback records, so CleanArr did not guess.", "Jellyfin вернул противоречивые записи просмотров, поэтому CleanArr не стал угадывать."],
  playback_observation_malformed: ["Jellyfin returned an invalid playback value.", "Jellyfin вернул некорректное значение просмотра."],
  arr_history_unavailable: ["Arr history could not be read, so torrent and seeding data cannot be linked safely.", "Историю Arr не удалось получить, поэтому нельзя безопасно связать торрент и данные раздачи."],
  arr_history_incomplete: ["Arr history reached the safe read limit. Torrent data remains unknown.", "История Arr достигла безопасного лимита чтения. Данные торрента остаются неизвестными."],
  arr_history_truncated: ["Some Arr history was not loaded because the bounded read limit was reached.", "Часть истории Arr не загружена: достигнут ограниченный лимит чтения."],
  arr_mapping_unknown: ["This item is not linked to one exact Arr record, so its torrent and seeding data remain unknown.", "Элемент не связан с одной точной записью Arr, поэтому данные о торренте и раздаче остаются неизвестными."],
  no_arr_hashes: ["Arr has no exact torrent identifier for this item. No torrent action will be planned.", "В Arr нет точного идентификатора торрента для этого элемента. Действие с торрентом не планируется."],
  downloader_mapping_ambiguous: ["More than one downloader record matches the Arr identifier.", "Идентификатору Arr соответствует больше одной записи загрузчика."],
  downloader_snapshot_stale: ["The downloader data is too old to use for a safety decision.", "Данные загрузчика устарели и не подходят для решения о безопасности."],
  downloader_ownership_unknown: ["CleanArr could not prove that it manages the matched torrent.", "CleanArr не смог доказать, что управляет найденным торрентом."],
  torrent_state_unknown: ["The downloader did not provide a known torrent state.", "Загрузчик не сообщил известное состояние торрента."],
  required_metric_unknown: ["The seeding policy needs a ratio or duration that the downloader did not provide.", "Политике раздачи нужен коэффициент или время, которого загрузчик не предоставил."],
  seeding_evidence_invalid: ["The torrent evidence was inconsistent and was rejected.", "Данные о торренте оказались противоречивыми и были отклонены."],
  safety_preflight_required: ["Safety is decided only after you open and review the current deletion plan.", "Безопасность определяется только после открытия и проверки актуального плана удаления."],
  radarr_catalog_unavailable: ["Radarr did not return its movie catalogue.", "Radarr не вернул каталог фильмов."],
  sonarr_catalog_unavailable: ["Sonarr did not return its series catalogue.", "Sonarr не вернул каталог сериалов."],
  jellyfin_catalog_unavailable: ["Jellyfin did not return its media catalogue.", "Jellyfin не вернул каталог медиатеки."],
  jellyfin_unavailable: ["Jellyfin could not be reached while loading current item details.", "Не удалось связаться с Jellyfin при загрузке актуальных сведений об элементе."],
  ambiguous_jellyfin_match: ["Several Jellyfin items could match this Arr record, so CleanArr did not choose one.", "Записи Arr соответствует несколько элементов Jellyfin, поэтому CleanArr не стал выбирать один из них."],
  season_jellyfin_unavailable: ["Jellyfin season details are unavailable; direct Jellyfin cleanup is omitted from the plan.", "Сведения о сезонах Jellyfin недоступны; прямое удаление из Jellyfin не включается в план."],
  series_detail_unavailable: ["Sonarr did not return complete season and episode details.", "Sonarr не вернул полные сведения о сезонах и эпизодах."],
  detail_enrichment_unavailable: ["One of the detail sources did not respond, so some values remain unknown.", "Один из источников подробностей не ответил, поэтому часть значений остаётся неизвестной."],
  safety_evidence_unavailable: ["Current safety evidence is incomplete. Open a fresh deletion plan before making changes.", "Актуальные данные безопасности неполны. Перед изменениями откройте новый план удаления."],
}

export function libraryEvidenceReason(language: LibraryLanguage, code: string | null | undefined) {
  if (!code) return LIBRARY_COPY[language].signalUnavailable
  return EVIDENCE_REASONS[code]?.[language === "ru" ? 1 : 0] ?? LIBRARY_COPY[language].signalUnavailable
}

export function librarySourceLabel(language: LibraryLanguage, source: string) {
  const key = source.toLowerCase()
  if (key.includes("jellyfin")) return "Jellyfin"
  if (key.includes("radarr")) return "Radarr"
  if (key.includes("sonarr")) return "Sonarr"
  if (key.includes("download")) return language === "ru" ? "Загрузчик" : "Downloader"
  return language === "ru" ? "Медиатека" : "Library"
}
