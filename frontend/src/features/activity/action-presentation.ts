import type { DashboardAction } from "@/lib/dashboard"

export type ActivityLanguage = "en" | "ru"

const SYSTEM_LABELS: Record<string, readonly [string, string]> = {
  radarr: ["Radarr", "Radarr"],
  sonarr: ["Sonarr", "Sonarr"],
  seerr: ["Seerr", "Seerr"],
  jellyfin: ["Jellyfin", "Jellyfin"],
  downloader: ["Downloader", "Загрузчик"],
  qbittorrent: ["qBittorrent", "qBittorrent"],
  transmission: ["Transmission", "Transmission"],
  deluge: ["Deluge", "Deluge"],
  rtorrent: ["rTorrent", "rTorrent"],
}

const ACTION_LABELS: Record<string, readonly [string, string]> = {
  resolve_movie: ["Find movie", "Поиск фильма"],
  resolve_series: ["Find series", "Поиск сериала"],
  resolve_media: ["Find request record", "Поиск записи запроса"],
  delete_hashes: ["Find related torrents", "Поиск связанных торрентов"],
  delete_hash: ["Remove torrent", "Удаление торрента"],
  delete_movie: ["Remove movie", "Удаление фильма"],
  delete_series: ["Remove series", "Удаление сериала"],
  delete_season_scope: ["Check season files", "Проверка файлов сезона"],
  delete_episode_scope: ["Check episode files", "Проверка файлов эпизода"],
  delete_episode_file: ["Remove episode file", "Удаление файла эпизода"],
  unmonitor_episodes: ["Stop episode monitoring", "Отключение наблюдения за эпизодами"],
  unmonitor_season: ["Stop season monitoring", "Отключение наблюдения за сезоном"],
  cleanup_movie: ["Clean up movie requests", "Очистка запросов фильма"],
  cleanup_series: ["Clean up series requests", "Очистка запросов сериала"],
  cleanup_season: ["Clean up season requests", "Очистка запросов сезона"],
  cleanup_episode: ["Clean up episode requests", "Очистка запросов эпизода"],
  delete_request: ["Remove request", "Удаление запроса"],
  update_request: ["Update request", "Обновление запроса"],
  delete_issue: ["Remove issue", "Удаление обращения"],
  delete_media: ["Remove media record", "Удаление записи медиатеки"],
  delete_item: ["Remove library item", "Удаление из медиатеки"],
}

const REASON_COPY: Record<string, readonly [string, string]> = {
  no_match: [
    "No single exact match was found in this service, so CleanArr safely skipped it.",
    "В этом сервисе не нашлось одного точного совпадения, поэтому CleanArr безопасно пропустил шаг.",
  ],
  ambiguous_match: [
    "Several records could match. CleanArr did not choose one automatically.",
    "Подходят несколько записей. CleanArr не стал выбирать одну автоматически.",
  ],
  pack_torrent: [
    "The torrent contains more content than this item and was kept.",
    "Торрент содержит не только этот материал, поэтому он сохранён.",
  ],
  shared_file: [
    "The file is shared with other media and was kept.",
    "Файл используется другими материалами, поэтому он сохранён.",
  ],
  seeding_policy: [
    "The configured seeding policy requires keeping this torrent for now.",
    "Настроенная политика раздачи пока требует сохранить этот торрент.",
  ],
  partial_request_retained: [
    "The request covers more episodes than this cleanup and was kept.",
    "Запрос охватывает больше эпизодов, чем текущая очистка, поэтому он сохранён.",
  ],
  no_partial_request_cleanup: [
    "This service cannot safely remove only the requested part, so the request was kept.",
    "Сервис не умеет безопасно удалить только выбранную часть, поэтому запрос сохранён.",
  ],
  authentication_failed: [
    "The service rejected CleanArr credentials. Check the connection settings and retry.",
    "Сервис отклонил учётные данные CleanArr. Проверьте подключение и повторите попытку.",
  ],
  downstream_error: [
    "The service did not finish the action. Check its availability before retrying.",
    "Сервис не завершил действие. Проверьте его доступность перед повтором.",
  ],
  source_still_present: [
    "The source item is still present, so dependent cleanup was not started.",
    "Исходный объект всё ещё существует, поэтому зависимая очистка не запускалась.",
  ],
  unsupported_event: [
    "This event type is not supported and no changes were made.",
    "Этот тип события не поддерживается, изменения не выполнялись.",
  ],
}

const STATUS_COPY = {
  en: {
    deleted: "The action completed successfully.",
    already_absent: "The record was already absent; no further change was needed.",
    dry_run: "The action was verified but only simulated in dry-run mode.",
    skipped: "The step was intentionally skipped without making a change.",
    ignored: "The event did not require this action.",
    failed: "The action failed and needs attention.",
  },
  ru: {
    deleted: "Действие успешно выполнено.",
    already_absent: "Запись уже отсутствовала, дополнительных изменений не потребовалось.",
    dry_run: "Действие проверено, но только смоделировано в тестовом режиме.",
    skipped: "Шаг намеренно пропущен без изменений.",
    ignored: "Для этого события действие не требовалось.",
    failed: "Действие завершилось ошибкой и требует внимания.",
  },
} as const

function localizedPair(language: ActivityLanguage, value: readonly [string, string] | undefined) {
  return value?.[language === "ru" ? 1 : 0]
}

export function actionTitle(action: DashboardAction, language: ActivityLanguage) {
  const system = localizedPair(language, SYSTEM_LABELS[action.system.toLowerCase()])
    ?? (language === "ru" ? "Сервис" : "Service")
  const actionName = localizedPair(language, ACTION_LABELS[action.action])
    ?? (language === "ru" ? "Безопасная обработка" : "Safe processing")
  return `${system} · ${actionName}`
}

export function actionDescription(action: DashboardAction, language: ActivityLanguage) {
  const reason = action.reason ? localizedPair(language, REASON_COPY[action.reason]) : undefined
  if (reason) return reason
  return STATUS_COPY[language][action.status]
}

export function actionSummaryLabel(status: string, count: number, language: ActivityLanguage) {
  const labels = language === "ru"
    ? { deleted: "выполнено", skipped: "безопасно пропущено", ignored: "не потребовалось", failed: "с ошибкой", already_absent: "уже отсутствовало", dry_run: "проверено в тестовом режиме" }
    : { deleted: "completed", skipped: "safely skipped", ignored: "not required", failed: "failed", already_absent: "already absent", dry_run: "checked in dry run" }
  const label = labels[status as keyof typeof labels] ?? (language === "ru" ? "других шагов" : "other steps")
  return `${count} ${label}`
}
