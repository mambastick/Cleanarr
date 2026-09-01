export const SETUP_CONNECTION_COPY = {
  en: {
    connectionVerified: "Tested with current connection settings",
    connectionIncomplete: "Not ready — test this exact connection before calling it configured.",
    testCurrentProfile: "Test current profile",
    addAnotherProfile: "Add another client",
    enabledTopology: "Every enabled owning client participates in routing. Default is only a routing fallback preference.",
  },
  ru: {
    connectionVerified: "Проверено с текущими параметрами подключения",
    connectionIncomplete: "Не готово — проверьте именно это подключение, прежде чем считать его настроенным.",
    testCurrentProfile: "Проверить текущий профиль",
    addAnotherProfile: "Добавить ещё клиент",
    enabledTopology: "Все включённые клиент-владельцы участвуют в маршрутизации. Default — только предпочтение для fallback-маршрута.",
  },
} as const
