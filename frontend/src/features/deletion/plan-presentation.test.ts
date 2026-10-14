import { describe, expect, it } from "vitest"
import type { DashboardAction, DashboardProcessingResult } from "@/lib/dashboard"
import type { RuntimeConfigPayload } from "@/lib/runtime-config"
import { actionEffect, actionFacts, actionLink, actionTarget, blockingTorrents, inspectionServices, planScope, providerLinks } from "./plan-presentation"
import { actionGroup, localizedJobError } from "./deletion-copy"

const plan: DashboardProcessingResult = { item_type: "Series", item_id: "fixture-series", name: "Example Series", display_name: "Пример сериала", status: "success", fingerprint: { tmdb_id: 42, tvdb_id: null, imdb_id: "tt12345", path: "/media/example" }, season_number: null, episode_number: null, episode_end_number: null, actions: [] }
const action: DashboardAction = { system: "qbittorrent", action: "delete_hash", status: "dry_run", message: "DO NOT DISPLAY", reason: null, details: { hash: "A".repeat(40), torrent_name: "Example.Series.S01", content_path: "/downloads/Example.Series.S01", downloader_id: "client-2", downloader_name: "Second client", delete_files: true } }

describe("deletion target presentation", () => {
  it("uses concrete targets and distinguishes file deletion from entry-only and unknown modes", () => {
    expect(actionTarget(action, plan, "ru")).toBe("Example.Series.S01")
    expect(actionEffect(action, "ru")).toContain("скачанные файлы")
    expect(actionEffect({ ...action, details: { delete_files: false } }, "en")).toContain("keeps the downloaded files")
    expect(actionEffect({ ...action, details: {} }, "ru")).toContain("не указано")
    expect(actionTarget({ ...action, details: { hash: "B".repeat(40) } }, plan, "en")).toContain("B".repeat(40))
    expect(actionTarget({ ...action, system: "seerr", action: "delete_request", details: { request_id: 29 } }, plan, "ru")).toBe("Запрос #29 · Пример сериала")
  })
  it("explains retained and blocked outcomes before the planned mutation", () => {
    expect(actionEffect({ ...action, status: "skipped", reason: "seeding_policy" }, "en")).toContain("keeps this torrent")
    expect(actionEffect({ ...action, status: "skipped", reason: "shared_file" }, "ru")).toContain("используется другими")
    expect(actionEffect({ ...action, status: "skipped", reason: "no_match" }, "ru")).toContain("заблокировано")
    expect(actionEffect({ ...action, status: "failed", reason: "new_reason" }, "en")).toContain("blocked")
    expect(actionEffect({ ...action, status: "already_absent" }, "en")).toContain("Already absent")
    expect(actionEffect({ ...action, action: "future_action" }, "ru")).toContain("не описывает")
  })
  it("distinguishes incomplete sibling evidence and closed torrents from known shared data", () => {
    const sibling = { ...action, status: "skipped" as const, reason: "sibling_scope_unknown" }
    expect(actionGroup(sibling)).toBe("attention")
    expect(actionEffect(sibling, "en")).toContain("incomplete file metadata")
    expect(actionEffect(sibling, "ru")).toContain("неполные сведения")
    const closed = { ...sibling, reason: "torrent_closed" }
    expect(actionGroup(closed)).toBe("attention")
    expect(actionEffect(closed, "en")).toContain("Open or resume it in rTorrent")
    expect(actionEffect(closed, "ru")).toContain("Откройте или возобновите")
    expect(localizedJobError("unsafe_plan", "en")).toContain("Automatic retry is disabled")
    expect(localizedJobError("unsafe_plan", "ru")).toContain("Автоматический повтор отключён")
  })
  it("projects only validated blocker identities and useful names", () => {
    const sibling = { ...action, status: "skipped" as const, reason: "sibling_scope_unknown", details: { blocking_torrents: [
      { downloader_id: "client-2", hash: "B".repeat(40), torrent_name: "Unknown release", url: "SECRET", error: "SECRET" },
      { downloader_id: "client-3", hash: "C".repeat(64) },
      { downloader_id: "client-4", hash: "bad" },
      { downloader_id: "https://private.example", hash: "A".repeat(40) },
      null,
    ] } }
    expect(blockingTorrents(sibling)).toEqual([
      { clientId: "client-2", hash: "B".repeat(40), name: "Unknown release" },
      { clientId: "client-3", hash: "C".repeat(64), name: null },
    ])
    expect(JSON.stringify(actionFacts(sibling, "ru"))).toContain("Unknown release")
    expect(JSON.stringify(actionFacts(sibling, "en"))).not.toMatch(/SECRET|private/)
    expect(blockingTorrents({ ...sibling, reason: "shared_path" })).toEqual([])
  })
  it("shows scope including specials and episode ranges, and labels non-deletion changes accurately", () => {
    expect(planScope(plan, "ru")).toContain("все сезоны")
    expect(planScope({ ...plan, item_type: "Season", season_number: 0 }, "ru")).toBe("Сезон 0")
    expect(planScope({ ...plan, item_type: "Episode", season_number: 2, episode_number: 3, episode_end_number: 5 }, "en")).toBe("Season 2 · Episode 3–5")
    expect(actionEffect({ ...action, system: "seerr", action: "update_request" }, "en")).toContain("keep the other seasons")
    expect(actionEffect({ ...action, system: "sonarr", action: "unmonitor_season" }, "ru")).toContain("Отключить наблюдение")
  })
  it("allowlists useful technical fields and renders no raw messages, credentials or URLs", () => {
    const facts = actionFacts({ ...action, details: { ...action.details, episode_ids: [2, 3], api_key: "SECRET", url: "https://private.example/?token=SECRET", tracker: "PRIVATE", error: "PRIVATE" } }, "ru")
    expect(facts).toContainEqual({ label: "Путь данных", value: "/downloads/Example.Series.S01" })
    expect(facts).toContainEqual({ label: "Хеш торрента", value: "A".repeat(40) })
    expect(facts).toContainEqual({ label: "ID эпизодов", value: "2, 3" })
    expect(JSON.stringify(facts)).not.toMatch(/SECRET|PRIVATE|DO NOT DISPLAY/)
  })
})

describe("inspection links", () => {
  const service = { id: "client-2", name: "Second client", kind: "qbittorrent", url: "https://client.example/base/", active: false }
  it("links to the exact client profile, preserves base paths, and never guesses ambiguous owners", () => {
    expect(actionLink(action, plan, [{ ...service, id: "client-1" }, service])?.href).toBe(service.url)
    expect(actionLink({ ...action, details: {} }, plan, [{ ...service, id: "client-1" }, service])).toBeNull()
    expect(actionLink(action, plan, [{ ...service, id: "client-1" }])).toBeNull()
    expect(actionLink({ ...action, details: {} }, plan, [service])?.item).toBe(false)
  })
  it.each(["javascript:alert(1)", "data:text/html,example", "file:///media/example", "//other.example", "https://user:password@example.com", "https://example.com/?token=secret", "https://example.com/#secret", "https://example.com/transmission/rpc", "https://example.com/RPC2", "https://example.com/api/v2"]) ("rejects unsafe or API-only configured address %s", (url) => {
    expect(actionLink(action, plan, [{ ...service, url }])).toBeNull()
  })
  it("uses TMDB IDs rather than internal Seerr media IDs for a media page", () => {
    const seerr = { ...service, kind: "seerr", active: true, url: "https://seerr.example/base/" }
    expect(actionLink({ ...action, system: "seerr", details: { media_id: 987 } }, plan, [seerr])?.href).toBe("https://seerr.example/base/tv/42")
    expect(actionLink({ ...action, system: "seerr", details: {} }, { ...plan, item_type: "Movie" }, [seerr])?.href).toBe("https://seerr.example/base/movie/42")
  })
  it("only generates public provider links from valid exact IDs", () => {
    expect(providerLinks(plan).map((link) => link.href)).toEqual(["https://www.themoviedb.org/tv/42", "https://www.imdb.com/title/tt12345/"])
    expect(providerLinks({ ...plan, fingerprint: { ...plan.fingerprint, tmdb_id: -1, imdb_id: "tt123/../secret" } })).toEqual([])
  })
  it("projects only enabled connection identities and safe URLs, without credentials or RPC links", () => {
    const config = { radarr: [], sonarr: [], seerr: [], jellyfin: [], downloaders: [{ ...service, enabled: true, is_default: true, password: "SECRET", api_key: "SECRET" }, { ...service, id: "disabled", enabled: false }, { ...service, id: "rpc", kind: "rtorrent", enabled: true }] } as unknown as RuntimeConfigPayload
    expect(inspectionServices(config)).toEqual([{ ...service, active: true }])
    expect(JSON.stringify(inspectionServices(config))).not.toContain("SECRET")
  })
})
