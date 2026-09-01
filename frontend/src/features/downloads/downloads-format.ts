import type { DownloadsCopy } from "./downloads-copy"

export function knownNumber(value: number | null | undefined, render: (number: number) => string, text: DownloadsCopy) { return typeof value === "number" && Number.isFinite(value) ? render(value) : text.unknown }
export function bytes(value: number | null | undefined, text: DownloadsCopy) { return knownNumber(value, (number) => { const index = number === 0 ? 0 : Math.min(4, Math.floor(Math.log(number) / Math.log(1024))); return `${(number / 1024 ** index).toFixed(index ? 1 : 0)} ${["B", "KB", "MB", "GB", "TB"][index]}` }, text) }
export function rate(value: number | null | undefined, text: DownloadsCopy) { return knownNumber(value, (number) => `${bytes(number, text)}/s`, text) }
export function duration(value: number | null | undefined, text: DownloadsCopy) { return knownNumber(value, (number) => number < 60 ? `${Math.round(number)}s` : number < 3600 ? `${Math.round(number / 60)}m` : `${(number / 3600).toFixed(1)}h`, text) }
export function date(value: string | null | undefined, text: DownloadsCopy, locale: string) { const parsed = value ? new Date(value) : null; return parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString(locale) : text.unknown }
export function reason(value: string | null | undefined, text: DownloadsCopy) { return value ? value.replaceAll("_", " ") : text.unknown }
