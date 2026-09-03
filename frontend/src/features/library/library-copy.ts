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
}

export const LIBRARY_COPY: Record<LibraryLanguage, LibraryV2Copy> = {
  en: {
    title: "Library", description: "Browse your media and review what can be safely removed.", movies: "Movies", series: "Series", search: "Search library", sort: "Sort", added: "Recently added", titleSort: "Title", size: "Size", ascending: "Ascending", descending: "Descending", refresh: "Refresh", retry: "Retry", loadMore: "Load more", select: "Select", selectMode: "Select", selectVisible: "Select visible", exitSelectMode: "Done", selected: "selected", selectedHidden: "hidden", clearSelection: "Clear", batchDelete: "Review deletion plan", noItems: "No library items found.", partial: "Some sources returned incomplete data.", unavailable: "The library source is unavailable.", catalogChanged: "The library changed while it was loading. Review the refreshed list.", sourceFailure: "Source details", unknown: "Unknown", noArtwork: "Artwork unavailable", movie: "Movie", seriesType: "Series", year: "Year", sizeLabel: "On disk", playback: "Playback", freshness: "Data freshness", playCount: "Play count", lastPlayed: "Last played", neverPlayed: "Not played", seeding: "Seeding", ratio: "Ratio", seededTime: "Seeded time", readiness: "Readiness", unknownReasons: "Why this is unknown", safety: "Safety", safe: "Safety evidence available", blocked: "Blocked", reviewPlan: "Review deletion plan", selectForGroup: "Select for group", additional: "Additional", technicalDetails: "Technical details", seasons: "Seasons", episodes: "Episodes", close: "Close", loadingDetails: "Loading current safety evidence…", addedLabel: "Added", deleteUnavailable: "Deletion planning is unavailable for this item.", selectionLimit: "A batch can contain at most 50 items.", selectionNeedsReview: "Some selected items belong to an older catalog. Open them again or clear the selection.", itemChanged: "This item changed or is no longer linked to Arr.", selectedItemChanged: "A selected item changed. Refresh the library.", torrentClient: "Torrent client", fresh: "Current", stale: "Stale", ready: "Ready", notReady: "Not ready", signalUnavailable: "The source did not provide enough current evidence.", watched: "Watched",
  },
  ru: {
    title: "Библиотека", description: "Просматривайте медиатеку и проверяйте, что можно безопасно удалить.", movies: "Фильмы", series: "Сериалы", search: "Поиск по библиотеке", sort: "Сортировка", added: "Недавно добавленные", titleSort: "Название", size: "Размер", ascending: "По возрастанию", descending: "По убыванию", refresh: "Обновить", retry: "Повторить", loadMore: "Загрузить ещё", select: "Выбрать", selectMode: "Выбрать", selectVisible: "Выбрать видимые", exitSelectMode: "Готово", selected: "выбрано", selectedHidden: "скрыто", clearSelection: "Очистить", batchDelete: "Проверить план удаления", noItems: "В медиатеке ничего не найдено.", partial: "Некоторые источники вернули неполные данные.", unavailable: "Источник медиатеки недоступен.", catalogChanged: "Медиатека изменилась во время загрузки. Проверьте обновлённый список.", sourceFailure: "Детали источников", unknown: "Неизвестно", noArtwork: "Нет обложки", movie: "Фильм", seriesType: "Сериал", year: "Год", sizeLabel: "На диске", playback: "Просмотр", freshness: "Свежесть данных", playCount: "Количество просмотров", lastPlayed: "Последний просмотр", neverPlayed: "Не просмотрено", seeding: "Раздача", ratio: "Рейтинг", seededTime: "Время раздачи", readiness: "Готовность", unknownReasons: "Почему неизвестно", safety: "Безопасность", safe: "Данные для проверки доступны", blocked: "Заблокировано", reviewPlan: "Проверить план удаления", selectForGroup: "Выбрать для группы", additional: "Дополнительно", technicalDetails: "Технические детали", seasons: "Сезоны", episodes: "Эпизоды", close: "Закрыть", loadingDetails: "Загружаем актуальные данные безопасности…", addedLabel: "Добавлено", deleteUnavailable: "Планирование удаления для этого элемента недоступно.", selectionLimit: "В пакет можно выбрать не более 50 элементов.", selectionNeedsReview: "Часть выбранных элементов относится к старой версии каталога. Откройте их снова или очистите выбор.", itemChanged: "Элемент изменился или больше не связан с Arr.", selectedItemChanged: "Один из выбранных элементов изменился. Обновите библиотеку.", torrentClient: "Torrent-клиент", fresh: "Актуальные", stale: "Устаревшие", ready: "Готово", notReady: "Не готово", signalUnavailable: "Источник не предоставил достаточно актуальных данных.", watched: "Просмотрено",
  },
}
