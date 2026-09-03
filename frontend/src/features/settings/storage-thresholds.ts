export interface StorageThresholdCopy { warning: string; critical: string; hint: string; invalid: string; }
export const STORAGE_THRESHOLD_COPY = {
  en: { warning: "Warning free-space threshold (%)", critical: "Critical free-space threshold (%)", hint: "Use percentages from 0 to 100. Critical must stay below warning.", invalid: "Enter values where 0 ≤ critical < warning ≤ 100." },
  ru: { warning: "Порог предупреждения свободного места (%)", critical: "Критический порог свободного места (%)", hint: "Укажите проценты от 0 до 100. Критический порог должен быть ниже предупреждения.", invalid: "Введите значения: 0 ≤ критический < предупреждение ≤ 100." },
} satisfies Record<"en" | "ru", StorageThresholdCopy>
export function validateStorageThresholds(warning: number, critical: number): boolean { return Number.isFinite(warning) && Number.isFinite(critical) && warning >= 0 && warning <= 100 && critical >= 0 && critical < warning }
