export type ConnectionFields = {
  downloader_kind: "qbittorrent" | "transmission" | "deluge" | "rtorrent" | null
  url: string
  username: string
  password: string
  api_key: string
}

/** Ephemeral only: this value is never persisted or logged. */
export function connectionFingerprint(draft: ConnectionFields): string {
  const url = draft.url.trim()
  switch (draft.downloader_kind) {
    case "qbittorrent": return JSON.stringify(["qbittorrent", url, draft.username, draft.password, draft.api_key])
    case "transmission": return JSON.stringify(["transmission", url, draft.username, draft.password])
    case "rtorrent": return JSON.stringify(["rtorrent", url, draft.username, draft.password])
    case "deluge": return JSON.stringify(["deluge", url, draft.password])
    default: return JSON.stringify(["unknown", url])
  }
}

export function hasCurrentConnectionEvidence(draft: ConnectionFields, testedFingerprints: ReadonlySet<string>): boolean {
  return testedFingerprints.has(connectionFingerprint(draft))
}
