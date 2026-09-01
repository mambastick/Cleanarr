import type { UiTextMap } from "@/lib/i18n"
import { DEFAULT_UI_LANG, getUiText } from "@/lib/i18n"

export function formatMediaTitle(itemType: string, name: string): string {
  return `${itemType}: ${name}`
}

export function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Unexpected request error"
}

export function getWebhookStatusTone(outcome: string): "blue" | "green" | "red" {
  if (outcome === "processed") return "green"
  if (outcome === "rejected_auth" || outcome === "invalid_payload") return "red"
  return "blue"
}

export function getWebhookStatusLabel(outcome: string, text: UiTextMap = getUiText(DEFAULT_UI_LANG)): string {
  switch (outcome) {
    case "processed": return text.webhookReceived
    case "rejected_auth": return text.tokenMismatch
    case "invalid_payload": return text.payloadRejected
    default: return text.noDeliveryYet
  }
}
