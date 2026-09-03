const AVATAR_TONE_COUNT = 5

export function userInitials(name: string | null | undefined): string {
  const parts = (name ?? "")
    .trim()
    .split(/[\s._-]+/u)
    .filter(Boolean)

  if (!parts.length) return "?"
  const first = parts[0]?.charAt(0) ?? ""
  const last = parts.length > 1 ? parts.at(-1)?.charAt(0) ?? "" : ""
  return `${first}${last}`.toLocaleUpperCase()
}

export function userAvatarTone(name: string | null | undefined): number {
  let hash = 0
  for (const character of (name ?? "").trim().toLocaleLowerCase()) {
    hash = (hash * 31 + (character.codePointAt(0) ?? 0)) >>> 0
  }
  return hash % AVATAR_TONE_COUNT
}
