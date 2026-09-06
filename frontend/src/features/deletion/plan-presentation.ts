import type { DashboardAction, DashboardProcessingResult } from "@/lib/dashboard"
import type { RuntimeConfigPayload } from "@/lib/runtime-config"
import { actionGroup, type DeletionLanguage } from "./deletion-copy"

export const planCopy = {
  en: {
    changes: "Planned changes", torrent: "Torrent", request: "Request", issue: "Issue", media: "Media record", file: "Episode file", spaceUnknown: "Freed space: unknown",
    movie: "Entire movie", series: "Entire series · all seasons", season: "Season", episode: "Episode", scopeUnknown: "Deletion scope unavailable",
    dataPath: "Data path", downloadDirectory: "Download directory", mediaPath: "Media path", client: "Client", instance: "Service instance", hash: "Torrent hash", identifier: "Target ID",
    noName: "The client did not provide a torrent name. Use its hash to find it.", noPath: "The plan does not include a data path.", noDetails: "No additional target details were provided.",
    torrentAndData: "Remove the torrent entry and its downloaded files.", torrentOnly: "Remove the torrent entry. This step keeps the downloaded files.", torrentUnknown: "Remove the torrent entry. The plan does not specify whether its files will be removed.",
    movieEffect: "Remove the movie from Radarr and delete its media files.", seriesEffect: "Remove the entire series from Sonarr and delete its media files.", fileEffect: "Delete this episode file from disk through Sonarr.",
    requestEffect: "Delete this request from Seerr. This step does not delete files.", issueEffect: "Delete this issue from Seerr. This step does not delete files.", mediaEffect: "Delete the Seerr availability record. This step does not delete files.",
    updateRequest: "Remove the selected season from this request; keep the other seasons.", unmonitorSeason: "Stop monitoring this season in Sonarr.", unmonitorEpisodes: "Stop monitoring the selected episodes in Sonarr.", jellyfinEffect: "Delete the selected item through Jellyfin, including media files it manages.",
    unknownEffect: "Review the target details. The effect of this step is not described by this version of CleanArr.",
    absent: "Already absent from this service; this step will make no change.", retained: "This step is skipped. Other steps in the plan may still affect the files.", attention: "This step could not be verified. Deletion is blocked until the plan can be checked again.",
    pack_torrent: "This torrent contains content outside the selected scope and will be kept.", shared_file: "This file is shared with other media and will be kept by this step.", seeding_policy: "The seeding policy keeps this torrent in the client for now. Check the other steps for changes to its files.",
    partial_request_retained: "This request also covers episodes outside the selected scope and will be kept.", no_partial_request_cleanup: "Seerr cannot safely remove just this part of the request, so it will be kept.",
    no_match: "No exact target was found. Deletion is blocked.", ambiguous_match: "Several targets could match. Deletion is blocked.", downstream_error: "A service could not verify this step. Check its connection and refresh the plan.",
    openService: "Open service", openItem: "View item", linkHint: "Service links open the configured address in a new tab. Use the name or ID to locate the target; internal addresses may only work on your network.",
    size: "Freed space cannot be calculated reliably from this plan. Shared files and hardlinks can change the actual result.",
    technical: "Target identifiers and paths", operation: "Operation", reason: "Reason code", seasonNumber: "Season", episodeNumbers: "Episodes", episodeIds: "Episode IDs", fileId: "Episode file ID", requestId: "Request ID", issueId: "Issue ID", mediaId: "Media ID", movieId: "Movie ID", seriesId: "Series ID", jellyfinId: "Jellyfin item ID",
  },
  ru: {
    changes: "Запланированные изменения", torrent: "Торрент", request: "Запрос", issue: "Обращение", media: "Запись медиатеки", file: "Файл эпизода", spaceUnknown: "Освобождаемое место: неизвестно",
    movie: "Фильм целиком", series: "Сериал целиком · все сезоны", season: "Сезон", episode: "Эпизод", scopeUnknown: "Область удаления не указана",
    dataPath: "Путь данных", downloadDirectory: "Папка загрузки", mediaPath: "Путь медиаматериала", client: "Клиент", instance: "Экземпляр сервиса", hash: "Хеш торрента", identifier: "ID объекта",
    noName: "Клиент не передал название торрента. Его можно найти по хешу.", noPath: "Путь данных в плане не указан.", noDetails: "Дополнительные сведения об объекте не переданы.",
    torrentAndData: "Удалить торрент из клиента и его скачанные файлы.", torrentOnly: "Удалить торрент из клиента. Этот шаг сохранит скачанные файлы.", torrentUnknown: "Удалить торрент из клиента. В плане не указано, будут ли удалены его файлы.",
    movieEffect: "Удалить фильм из Radarr вместе с его медиафайлами.", seriesEffect: "Удалить сериал целиком из Sonarr вместе с его медиафайлами.", fileEffect: "Удалить этот файл эпизода с диска через Sonarr.",
    requestEffect: "Удалить этот запрос из Seerr. Этот шаг не удаляет файлы.", issueEffect: "Удалить это обращение из Seerr. Этот шаг не удаляет файлы.", mediaEffect: "Удалить запись о доступности из Seerr. Этот шаг не удаляет файлы.",
    updateRequest: "Убрать выбранный сезон из запроса; остальные сезоны сохранить.", unmonitorSeason: "Отключить наблюдение за этим сезоном в Sonarr.", unmonitorEpisodes: "Отключить наблюдение за выбранными эпизодами в Sonarr.", jellyfinEffect: "Удалить выбранный объект через Jellyfin, включая управляемые им медиафайлы.",
    unknownEffect: "Проверьте сведения об объекте. Эта версия CleanArr не описывает последствия данного шага.",
    absent: "Объект уже отсутствует в этом сервисе; этот шаг ничего не изменит.", retained: "Этот шаг пропущен. Другие шаги плана всё ещё могут затронуть файлы.", attention: "Не удалось проверить этот шаг. Удаление заблокировано до повторной проверки плана.",
    pack_torrent: "Торрент содержит материалы за пределами выбранной области и будет сохранён.", shared_file: "Файл используется другими материалами и будет сохранён этим шагом.", seeding_policy: "Политика раздачи пока сохраняет торрент в клиенте. Проверьте, затронут ли его файлы другие шаги.",
    partial_request_retained: "Запрос также охватывает эпизоды за пределами выбранной области и будет сохранён.", no_partial_request_cleanup: "Seerr не может безопасно убрать только эту часть запроса, поэтому запрос будет сохранён.",
    no_match: "Точный объект не найден. Удаление заблокировано.", ambiguous_match: "Подходят несколько объектов. Удаление заблокировано.", downstream_error: "Сервис не смог проверить этот шаг. Проверьте подключение и обновите план.",
    openService: "Открыть сервис", openItem: "Открыть карточку", linkHint: "Ссылки открывают настроенный адрес сервиса в новой вкладке. Найдите объект по названию или ID; внутренние адреса могут работать только в вашей сети.",
    size: "Точно рассчитать освобождаемое место по этому плану нельзя. Общие файлы и жёсткие ссылки могут повлиять на результат.",
    technical: "Идентификаторы и пути объектов", operation: "Операция", reason: "Код причины", seasonNumber: "Сезон", episodeNumbers: "Эпизоды", episodeIds: "ID эпизодов", fileId: "ID файла эпизода", requestId: "ID запроса", issueId: "ID обращения", mediaId: "ID записи медиатеки", movieId: "ID фильма", seriesId: "ID сериала", jellyfinId: "ID объекта Jellyfin",
  },
} as const

// Only explicitly known display fields are rendered; never dump backend messages,
// arbitrary details, credentials, tracker URLs, or confirmation material.
export function displayText(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim() || value.length > 4096) return null
  return value.replace(/[\p{Cc}\p{Cf}]/gu, "").trim() || null
}

export function identifier(value: unknown): string | null {
  if (typeof value === "number") return Number.isSafeInteger(value) && value >= 0 ? String(value) : null
  return typeof value === "string" && /^[\w.-]{1,256}$/.test(value) ? value : null
}

export function planScope(plan: DashboardProcessingResult, language: DeletionLanguage): string {
  const c = planCopy[language]
  if (plan.item_type === "Movie") return c.movie
  if (plan.item_type === "Series") return c.series
  if (plan.item_type === "Season" && plan.season_number != null) return `${c.season} ${plan.season_number}`
  if (plan.item_type === "Episode" && plan.episode_number != null) return `${c.season} ${plan.season_number ?? "?"} · ${c.episode} ${plan.episode_number}${plan.episode_end_number != null && plan.episode_end_number !== plan.episode_number ? `–${plan.episode_end_number}` : ""}`
  return c.scopeUnknown
}

export function actionTarget(action: DashboardAction, plan: DashboardProcessingResult, language: DeletionLanguage): string {
  const c = planCopy[language]
  const d = action.details
  const target = displayText(d.torrent_name) ?? displayText(d.title)
  if (target) return target
  if (action.action === "delete_hash") return `${c.torrent}${identifier(d.hash) ? ` · ${identifier(d.hash)}` : ""}`
  for (const [key, label] of [["request_id", c.request], ["issue_id", c.issue], ["media_id", c.media], ["episode_file_id", c.file]] as const) {
    if (identifier(d[key])) return `${label} #${identifier(d[key])} · ${displayText(plan.display_name) ?? displayText(plan.name) ?? planScope(plan, language)}`
  }
  return displayText(plan.display_name) ?? displayText(plan.name) ?? planScope(plan, language)
}

export function actionEffect(action: DashboardAction, language: DeletionLanguage): string {
  const c = planCopy[language]
  if (action.status === "already_absent") return c.absent
  if (actionGroup(action) !== "remove") {
    const reason = action.reason
    const reasons = { pack_torrent: c.pack_torrent, shared_file: c.shared_file, seeding_policy: c.seeding_policy, partial_request_retained: c.partial_request_retained, no_partial_request_cleanup: c.no_partial_request_cleanup, no_match: c.no_match, ambiguous_match: c.ambiguous_match, downstream_error: c.downstream_error }
    return reason && Object.hasOwn(reasons, reason) ? reasons[reason as keyof typeof reasons] : actionGroup(action) === "retain" ? c.retained : c.attention
  }
  if (action.action === "delete_hash") return action.details.delete_files === true ? c.torrentAndData : action.details.delete_files === false ? c.torrentOnly : c.torrentUnknown
  const effects: Record<string, string> = {
    "radarr:delete_movie": c.movieEffect, "sonarr:delete_series": c.seriesEffect, "sonarr:delete_episode_file": c.fileEffect,
    "seerr:delete_request": c.requestEffect, "seerr:delete_issue": c.issueEffect, "seerr:delete_media": c.mediaEffect, "seerr:update_request": c.updateRequest,
    "sonarr:unmonitor_season": c.unmonitorSeason, "sonarr:unmonitor_episodes": c.unmonitorEpisodes, "jellyfin:delete_item": c.jellyfinEffect,
  }
  return effects[`${action.system}:${action.action}`] ?? c.unknownEffect
}

export function actionFacts(action: DashboardAction, language: DeletionLanguage): Array<{ label: string; value: string }> {
  const c = planCopy[language]
  const labels: Record<string, string> = {
    hash: c.hash, downloader_name: c.client, downloader_id: `${c.client} ID`, client_name: c.client,
    radarr_instance_name: c.instance, sonarr_instance_name: c.instance, radarr_instance_id: `${c.instance} ID`, sonarr_instance_id: `${c.instance} ID`,
    path: c.mediaPath, content_path: c.dataPath, download_directory: c.downloadDirectory, request_id: c.requestId, issue_id: c.issueId, media_id: c.mediaId, movie_id: c.movieId, series_id: c.seriesId, jellyfin_item_id: c.jellyfinId,
    season_number: c.seasonNumber, episode_numbers: c.episodeNumbers, episode_ids: c.episodeIds, episode_file_id: c.fileId,
  }
  return Object.entries(labels).flatMap(([key, label]) => {
    const value = action.details[key]
    const rendered = Array.isArray(value) ? value.map(identifier).filter((item) => item != null).join(", ") : displayText(value) ?? identifier(value)
    return rendered ? [{ label, value: rendered }] : []
  })
}

export interface InspectionService { id: string; name: string; kind: string; url: string; active: boolean }
export interface InspectionLink { label: string; href: string; item: boolean }

function safeServiceUrl(value: string): string | null {
  try {
    const url = new URL(value)
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null
    // RPC endpoints are not browser interfaces. Do not guess a separate Web UI.
    if (/\/(?:api|rpc|rpc2|jsonrpc)(?:\/|$)/i.test(url.pathname)) return null
    return `${url.href.replace(/\/+$/, "")}/`
  } catch { return null }
}

export function inspectionServices(config: RuntimeConfigPayload | null): InspectionService[] {
  if (!config) return []
  return [config.radarr, config.sonarr, config.seerr, config.downloaders, config.jellyfin].flatMap((profiles) => {
    const enabled = profiles.filter((profile) => profile.enabled)
    const active = enabled.find((profile) => profile.is_default) ?? enabled[0]
    return enabled.flatMap((profile) => {
      const url = safeServiceUrl(profile.url)
      return url && profile.kind !== "rtorrent" ? [{ id: profile.id, name: profile.name, kind: profile.kind, url, active: active?.id === profile.id }] : []
    })
  })
}

export function actionLink(action: DashboardAction, plan: DashboardProcessingResult, services: InspectionService[]): InspectionLink | null {
  const rawInstanceId = action.details.downloader_id ?? action.details.radarr_instance_id ?? action.details.sonarr_instance_id
  const instanceId = identifier(rawInstanceId)
  if (rawInstanceId != null && instanceId == null) return null
  const candidates = services.filter((service) => service.kind === action.system)
  const service = instanceId ? candidates.find((candidate) => candidate.id === instanceId)
    : ["seerr", "jellyfin"].includes(action.system) ? candidates.find((candidate) => candidate.active) : candidates.length === 1 ? candidates[0] : undefined
  if (!service) return null
  const base = safeServiceUrl(service.url)
  if (!base || service.kind === "rtorrent") return null
  const tmdb = plan.fingerprint?.tmdb_id
  if (action.system === "seerr" && Number.isSafeInteger(tmdb) && tmdb! > 0 && ["Movie", "Series", "Season", "Episode"].includes(plan.item_type)) {
    return { label: service.name, href: `${base}${plan.item_type === "Movie" ? "movie" : "tv"}/${tmdb}`, item: true }
  }
  return { label: service.name, href: base, item: false }
}

export function providerLinks(plan: DashboardProcessingResult): InspectionLink[] {
  const links: InspectionLink[] = []
  const tmdb = plan.fingerprint?.tmdb_id
  if (Number.isSafeInteger(tmdb) && tmdb! > 0 && ["Movie", "Series", "Season", "Episode"].includes(plan.item_type)) links.push({ label: "TMDB", href: `https://www.themoviedb.org/${plan.item_type === "Movie" ? "movie" : "tv"}/${tmdb}`, item: true })
  const imdb = plan.fingerprint?.imdb_id
  if (imdb && /^tt\d{1,12}$/.test(imdb)) links.push({ label: "IMDb", href: `https://www.imdb.com/title/${imdb}/`, item: true })
  return links
}
