export type StorageLanguage = "en" | "ru"
export interface StorageCopy {
  title: string
  refresh: string
  loading: string
  unavailable: string
  retry: string
  healthy: string
  warning: string
  critical: string
  unknown: string
  partial: string
  free: string
  total: string
  observed: string
  stale: string
  possibleDuplicate: string
  provenance: string
}
export const STORAGE_COPY: Record<StorageLanguage, StorageCopy> = {
  en: { title: "Storage", refresh: "Refresh storage", loading: "Loading storage…", unavailable: "Storage data is unavailable.", retry: "Retry", healthy: "Healthy", warning: "Low space", critical: "Critical", unknown: "Unknown", partial: "Some storage sources returned incomplete data.", free: "Free", total: "Total", observed: "Observed", stale: "Data may be stale", possibleDuplicate: "Possible duplicate volume", provenance: "Storage is read from each configured Radarr and Sonarr root folder and disk-space endpoint. Paths and credentials stay hidden; preview data is never used here." },
  ru: { title: "Хранилище", refresh: "Обновить хранилище", loading: "Загрузка хранилища…", unavailable: "Данные о хранилище недоступны.", retry: "Повторить", healthy: "В норме", warning: "Мало места", critical: "Критично", unknown: "Неизвестно", partial: "Некоторые источники хранилища вернули неполные данные.", free: "Свободно", total: "Всего", observed: "Наблюдение", stale: "Данные могут быть устаревшими", possibleDuplicate: "Возможный дубликат тома", provenance: "Данные о хранилище поступают из root-папок и endpoint’ов свободного места каждого настроенного Radarr и Sonarr. Пути и учётные данные скрыты; тестовые данные здесь не используются." },
}
