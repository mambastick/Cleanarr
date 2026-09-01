import { connectionFingerprint, hasCurrentConnectionEvidence } from "@/lib/downloader-profile"
import { isSetupStepReady } from "@/lib/service-config"
import type { RuntimeConfigPayload } from "@/lib/runtime-config"

const draft = { downloader_kind: "qbittorrent" as const, url: " https://qbit.example ", username: "admin", password: "secret", api_key: "" }

describe("downloader connection evidence", () => {
  it("is deterministic and ignores display/runtime fields by construction", () => {
    expect(connectionFingerprint(draft)).toBe(connectionFingerprint({ ...draft }))
    expect(connectionFingerprint(draft)).toBe(connectionFingerprint({ ...draft, url: "https://qbit.example" }))
  })

  it.each([
    ["url", "https://other.example"], ["username", "another"], ["password", "changed"], ["api_key", "token"], ["downloader_kind", "transmission"],
  ] as const)("invalidates qBittorrent evidence when %s changes", (field, value) => {
    const evidence = new Set([connectionFingerprint(draft)])
    expect(hasCurrentConnectionEvidence({ ...draft, [field]: value } as typeof draft, evidence)).toBe(false)
  })

  it("keeps all Tier 1 profile kinds independently testable, including disabled drafts", () => {
    const profiles = ["qbittorrent", "transmission", "deluge", "rtorrent"] as const
    const fingerprints = profiles.map((downloader_kind) => connectionFingerprint({ ...draft, downloader_kind }))
    expect(new Set(fingerprints)).toHaveLength(4)
    expect(hasCurrentConnectionEvidence({ ...draft, downloader_kind: "deluge" }, new Set([fingerprints[2] ?? ""]))).toBe(true)
  })

  it.each([
    [{ ...draft, downloader_kind: "transmission" as const, api_key: "ignored" }, { api_key: "changed" }],
    [{ ...draft, downloader_kind: "rtorrent" as const, api_key: "ignored" }, { api_key: "changed" }],
    [{ ...draft, downloader_kind: "deluge" as const, username: "ignored", api_key: "ignored" }, { username: "changed", api_key: "changed" }],
  ])("ignores hidden irrelevant fields", (profile, hiddenChanges) => {
    const evidence = new Set([connectionFingerprint(profile)])
    expect(hasCurrentConnectionEvidence({ ...profile, ...hiddenChanges }, evidence)).toBe(true)
  })

  it("requires current evidence for every enabled profile but not disabled profiles", () => {
    const first = {
      id: "qbit",
      name: "qBittorrent",
      kind: "qbittorrent" as const,
      url: "https://qbit.example",
      enabled: true,
      is_default: true,
      username: "admin",
      password: "secret",
      api_key: null,
      seeding_policy: "immediate" as const,
      min_seed_ratio: null,
      min_seed_time_minutes: null,
    }
    const second = {
      id: "deluge",
      name: "Deluge",
      kind: "deluge" as const,
      url: "https://deluge.example",
      enabled: true,
      is_default: false,
      password: "secret",
      seeding_policy: "keep" as const,
      min_seed_ratio: null,
      min_seed_time_minutes: null,
    }
    const config = { downloaders: [first, second] } as RuntimeConfigPayload
    const firstEvidence = connectionFingerprint({ ...draft, api_key: "", url: first.url })
    const secondEvidence = connectionFingerprint({ ...draft, downloader_kind: "deluge", url: second.url, username: "", api_key: "" })

    expect(isSetupStepReady("downloaders", config, new Set())).toBe(false)
    expect(isSetupStepReady("downloaders", config, new Set([firstEvidence]))).toBe(false)
    expect(isSetupStepReady("downloaders", config, new Set([firstEvidence, secondEvidence]))).toBe(true)
    expect(isSetupStepReady("downloaders", { ...config, downloaders: [first, { ...second, enabled: false }] }, new Set([firstEvidence]))).toBe(true)
  })
})
