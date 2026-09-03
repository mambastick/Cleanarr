import { SETUP_CONNECTION_COPY } from "@/lib/setup-copy"

export type UiLanguage = string

export type UiTextKey =
  | "dashboard"
  | "settings"
  | "activity"
  | "library"
  | "downloads"
  | "live"
  | "dryRun"
  | "liveMode"
  | "liveModeDescription"
  | "dryRunDescription"
  | "logOut"
  | "navigation"
  | "status"
  | "setup"
  | "setupWizard"
  | "connectedServices"
  | "webhookStatus"
  | "latestEvent"
  | "webhookStatusDescription"
  | "latestEventDescription"
  | "noWebhookReceived"
  | "runtimeSettingsSaved"
  | "save"
  | "saveChanges"
  | "saveSettings"
  | "cancel"
  | "delete"
  | "deleteSeries"
  | "deleteItem"
  | "refresh"
  | "filter"
  | "clear"
  | "activityTimeline"
  | "activityTimelineDescription"
  | "eventCount"
  | "noActivityFiltered"
  | "noActivity"
  | "noActivityDescription"
  | "noActivityWebhook"
  | "sendWebhookToSeeActivity"
  | "sendWebhookForStatus"
  | "noWebhookAttempts"
  | "webhookAttempts"
  | "setupCount"
  | "deletionsLogged"
  | "noWebhookActivity"
  | "library"
  | "backgroundTasks"
  | "preflightPlan"
  | "preflightPlanHint"
  | "preflightLoading"
  | "preflightUnavailable"
  | "noPlannedActions"
  | "attempt"
  | "planning"
  | "retrying"
  | "searchMovies"
  | "noMoviesFound"
  | "noMoviesMatch"
  | "searchSeries"
  | "noSeriesFound"
  | "noSeriesMatch"
  | "noSeasonsFound"
  | "season"
  | "libraryDescription"
  | "dryRunModeInfo"
  | "noLiveChanges"
  | "series"
  | "movies"
  | "searchPlaceholderSeries"
  | "searchPlaceholderMovies"
  | "confirmDelete"
  | "simulate"
  | "deleteButton"
  | "confirmDeleteDescription"
  | "titleDeleteConfirmation"
  | "dryRunModeNotice"
  | "titleNotConfigured"
  | "general"
  | "settingsUnavailable"
  | "tryAgain"
  | "runtimeSettings"
  | "noItemsYet"
  | "appBehaviour"
  | "logLevel"
  | "httpTimeoutSeconds"
  | "activityRetention"
  | "jellyfinMetadataLanguage"
  | "uiLanguage"
  | "webhookToken"
  | "hideToken"
  | "showToken"
  | "regenerateToken"
  | "copyToken"
  | "tokenHint"
  | "allSettingsSaved"
  | "unsavedChanges"
  | "firstLaunchCreateAdmin"
  | "signInWithLocalOrSso"
  | "signInWithLocalOnly"
  | "signInWithSso"
  | "authTitleSignIn"
  | "authTitleCreateAdmin"
  | "username"
  | "password"
  | "confirmPassword"
  | "signInWithCredentials"
  | "orDivider"
  | "ssoSignInError"
  | "continueWithSso"
  | "ssoNotConfigured"
  | "connecting"
  | "configureSsoBefore"
  | "noAuthConfigured"
  | "requestFailed"
  | "ssoAuthMode"
  | "ssoIssuer"
  | "ssoClientId"
  | "ssoClientSecret"
  | "ssoRedirectUri"
  | "ssoScopes"
  | "ssoAllowedUsers"
  | "ssoAllowedGroups"
  | "ssoGroupClaim"
  | "ssoRequiredClaim"
  | "ssoRequiredValue"
  | "ssoAccessPolicyHint"
  | "ssoModePasswordOnly"
  | "ssoModeSsoOnly"
  | "ssoModeBoth"
  | "ssoModePasswordOnlyHint"
  | "ssoModeSsoOnlyHint"
  | "ssoModeBothHint"
  | "ssoIssuerHint"
  | "ssoClientIdHint"
  | "ssoClientSecretHint"
  | "ssoRedirectHint"
  | "ssoScopesHint"
  | "ssoFieldDisabledHint"
  | "webhookMessageLabel"
  | "webhookPayloadEventsLabel"
  | "webhookNotificationLabel"
  | "webhookResultStatusLabel"
  | "reasonLabel"
  | "add"
  | "edit"
  | "test"
  | "next"
  | "back"
  | "skipForNow"
  | "done"
  | "enabled"
  | "runtimeTarget"
  | "displayName"
  | "baseUrl"
  | "alreadyConfigured"
  | "connectionVerified"
  | "connectionIncomplete"
  | "testCurrentProfile"
  | "addAnotherProfile"
  | "enabledTopology"
  | "beforeYouSave"
  | "beforeSaveDescription"
  | "webhook"
  | "notConfigured"
  | "healthy"
  | "unreachable"
  | "noStatus"
  | "none"
  | "active"
  | "recent"
  | "dismiss"
  | "progress"
  | "actions"
  | "deletion"
  | "unexpectedRequestError"
  | "unknownError"
  | "passwordsDoNotMatch"
  | "adminCreated"
  | "signedIn"
  | "deletionStarted"
  | "backgroundRefreshFailed"
  | "serviceUpdated"
  | "serviceAdded"
  | "serviceRemoved"
  | "runtimeSettingsSummary"
  | "jellyfinLanguageHint"
  | "uiLanguageHint"
  | "runtimeSettingsDescription"
  | "recommendedFirstRun"
  | "recommendedDryRun"
  | "httpTimeoutHint"
  | "retentionHint"
  | "closeAndRefresh"
  | "keepDryRun"
  | "oneDay"
  | "sevenDays"
  | "thirtyDays"
  | "ninetyDays"
  | "oneYear"
  | "serviceRadarrDescription"
  | "serviceSonarrDescription"
  | "serviceSeerrDescription"
  | "serviceDownloaderDescription"
  | "serviceJellyfinDescription"
  | "apiKey"
  | "exampleUrl"
  | "reverseProxyHint"
  | "serviceUrlHint"
  | "downloaderUrlHint"
  | "radarrApiHint"
  | "sonarrApiHint"
  | "seerrApiHint"
  | "downloaderUsernameHint"
  | "downloaderPasswordHint"
  | "qbittorrentApiHint"
  | "delugePasswordHint"
  | "torrentClient"
  | "allEnabledRouting"
  | "disabled"
  | "defaultLabel"
  | "seedingPolicy"
  | "seedingImmediate"
  | "seedingKeep"
  | "seedingDefer"
  | "minSeedRatio"
  | "minSeedTime"
  | "seedingPolicyHint"
  | "seedingThresholdHint"
  | "jellyfinApiHint"
  | "firstTimeSetup"
  | "autoConfigureWebhook"
  | "autoConfigureWebhookDescription"
  | "connectJellyfinFirst"
  | "setWebhookTokenFirst"
  | "configuring"
  | "configured"
  | "installJellyfinWebhook"
  | "installJellyfinWebhookDescription"
  | "jellyfinInstallStep1"
  | "jellyfinInstallStep2"
  | "jellyfinInstallStep3"
  | "jellyfinInstallStep4"
  | "verifyDelivery"
  | "verifyDeliveryDescription"
  | "deliveryStatus"
  | "lastAttempt"
  | "httpStatus"
  | "lastItem"
  | "notReceivedYet"
  | "noItemReceived"
  | "processing"
  | "latestWebhookAttempt"
  | "noJellyfinWebhook"
  | "smokeTestCurl"
  | "tokenPrefilled"
  | "configureTokenFirst"
  | "smokeTestDescription"
  | "copyCurl"
  | "generalSetupStep1"
  | "generalSetupStep2"
  | "generalSetupStep3"
  | "tryDifferentSearch"
  | "noSeriesSetup"
  | "noMoviesSetup"
  | "onDisk"
  | "noFile"
  | "episodes"
  | "seasons"
  | "dryRunNoChanges"
  | "seasonOfSeries"
  | "movie"
  | "item"
  | "webhookReceived"
  | "tokenMismatch"
  | "payloadRejected"
  | "noDeliveryYet"
  | "partialFailure"
  | "success"
  | "failed"
  | "deleted"
  | "queued"
  | "running"
  | "completed"
  | "skipped"
  | "unknown"
  | "downloadsActive"
  | "storageProvenance"
  | "serviceDetails"
  | "recentActivitySummary"
  | "recentActivitySummaryDescription"
  | "recentActivityProcessed"
  | "recentActivityWebhook"
  | "eventDetails"
  | "technicalDetails"
  | "viewDetails"
  | "activityPageDescription"

export type UiTextMap = Record<UiTextKey, string>

export const UI_TEXTS: Record<UiLanguage, Partial<UiTextMap>> = {
  en: {
    dashboard: "Dashboard",
    settings: "Settings",
    activity: "Activity",
    library: "Library",
    downloads: "Downloads",
    downloadsActive: "active",
    storageProvenance: "CleanArr reads free space for each media folder from its configured Radarr or Sonarr. Paths and credentials stay hidden.",
    serviceDetails: "Technical details",
    recentActivitySummary: "Recent activity",
    recentActivitySummaryDescription: "The latest delivery or cleanup outcome, with technical details available when needed.",
    recentActivityProcessed: "Cleanup checked: {{item}}",
    recentActivityWebhook: "Media server event: {{item}}",
    eventDetails: "Event details",
    technicalDetails: "Technical details",
    viewDetails: "View details",
    activityPageDescription: "Review recent cleanup checks and media-server events. Open an item only when you need more detail.",
    live: "Live",
    dryRun: "Dry run",
    liveMode: "Live mode",
    liveModeDescription: "Real deletions are active",
    dryRunDescription: "No deletions will be made",
    status: "Status",
    setup: "Setup",
    setupWizard: "Setup wizard",
    connectedServices: "Connected services",
    webhookStatus: "Webhook status",
    latestEvent: "Latest event",
    webhookStatusDescription: "Last Jellyfin delivery attempt.",
    latestEventDescription: "Most recent processed item.",
    noWebhookReceived: "No webhook received",
    logOut: "Log out",
    navigation: "Main navigation",
    runtimeSettingsSaved: "Runtime settings saved.",
    save: "Save",
    saveChanges: "Save changes",
    saveSettings: "Save settings",
    cancel: "Cancel",
    delete: "Delete",
    deleteSeries: "Delete series",
    deleteItem: "Delete movie",
    series: "Series",
    movies: "Movies",
    refresh: "Refresh",
    filter: "Filter",
    clear: "Clear",
    activityTimeline: "Runtime activity timeline",
    activityTimelineDescription: "Incoming Jellyfin webhooks and processed deletion events in one stream.",
    eventCount: "event",
    noActivityFiltered: "No items match the current filter.",
    noActivity: "No activity yet",
    noActivityDescription: "No items found.",
    noActivityWebhook: "No activity yet",
    sendWebhookToSeeActivity: "Send a Jellyfin webhook or process a cleanup event to populate the timeline.",
    sendWebhookForStatus: "Send a Jellyfin webhook to see current status.",
    noWebhookAttempts: "No webhook attempts yet.",
    webhookAttempts: "No webhook attempts yet.",
    setupCount: "Setup progress",
    deletionsLogged: "deletions logged",
    noWebhookActivity: "No webhook activity yet.",
    noItemsYet: "No items found.",
    noSeriesFound: "No series found",
    noSeriesMatch: "No series match your search",
    noSeasonsFound: "No seasons with episodes found.",
    season: "Season",
    searchPlaceholderSeries: "Search series…",
    searchPlaceholderMovies: "Search movies…",
    libraryDescription:
      "Browse your media library and review a safety-bound cleanup plan across configured services before confirming it.",
    dryRunModeInfo: "Dry run mode",
    noLiveChanges: "No actual changes will be made. Enable Live mode in Runtime settings to execute real deletions.",
    deleteButton: "Delete",
    confirmDelete: "Delete",
    simulate: "Simulate (dry run)",
    confirmDeleteDescription:
      "Review the exact plan before confirming. Actions without complete ownership evidence are retained or blocked.",
    titleDeleteConfirmation: "Delete \"{{title}}\"?",
    dryRunModeNotice: "Dry run mode",
    titleNotConfigured: "No authentication method is currently configured.",
    backgroundTasks: "Background tasks",
    preflightPlan: "Exact preflight plan",
    preflightPlanHint: "Confirm only after reviewing the resolved targets and safety skips below.",
    preflightLoading: "Resolving targets and safety checks…",
    preflightUnavailable: "The plan must load successfully before deletion can be confirmed.",
    noPlannedActions: "No downstream actions were resolved.",
    attempt: "attempt",
    planning: "Checking plan",
    retrying: "Waiting to retry",
    searchMovies: "Search movies…",
    noMoviesFound: "No movies found",
    noMoviesMatch: "No movies match your search",
    general: "General",
    settingsUnavailable: "Settings unavailable",
    tryAgain: "Refresh the configuration and try again.",
    runtimeSettings: "Runtime settings",
    appBehaviour: "Application behaviour and operational parameters.",
    logLevel: "Log level",
    httpTimeoutSeconds: "HTTP timeout (s)",
    activityRetention: "Activity retention",
    jellyfinMetadataLanguage: "Jellyfin metadata language",
    uiLanguage: "UI language",
    webhookToken: "Webhook token",
    hideToken: "Hide token",
    showToken: "Show token",
    regenerateToken: "Regenerate token",
    copyToken: "Copy token",
    tokenHint:
      "Auto-generated. Regenerate only if you need to rotate it — then re-run auto-configure in the Jellyfin step.",
    allSettingsSaved: "All settings saved.",
    unsavedChanges: "You have unsaved changes.",
    firstLaunchCreateAdmin: "First launch — create the admin account.",
    signInWithLocalOrSso: "Sign in with local credentials or SSO.",
    signInWithLocalOnly: "Sign in with local credentials.",
    signInWithSso: "Sign in with SSO",
    authTitleSignIn: "Sign in",
    authTitleCreateAdmin: "Create administrator",
    username: "Username",
    password: "Password",
    confirmPassword: "Confirm password",
    signInWithCredentials: "Sign in with credentials",
    orDivider: "or",
    ssoSignInError: "SSO sign-in error",
    continueWithSso: "Continue with SSO",
    ssoNotConfigured: "SSO is not configured yet",
    connecting: "Connecting...",
    configureSsoBefore: "Enable and configure SSO in Runtime settings, then reload this screen.",
    noAuthConfigured: "No authentication method is currently configured.",
    requestFailed: "Request failed",
    ssoAuthMode: "SSO auth mode",
    ssoIssuer: "Issuer URL",
    ssoClientId: "Client ID",
    ssoClientSecret: "Client Secret",
    ssoRedirectUri: "Redirect URI",
    ssoScopes: "Scopes",
    ssoAllowedUsers: "Allowed users",
    ssoAllowedGroups: "Allowed groups",
    ssoGroupClaim: "Group claim",
    ssoRequiredClaim: "Required claim",
    ssoRequiredValue: "Required claim value",
    ssoAccessPolicyHint:
      "Access fails closed. A user must match an allowed user or group; the required claim is an additional condition. A required claim alone is also a valid policy.",
    ssoModePasswordOnly: "Local credentials only",
    ssoModeSsoOnly: "SSO only",
    ssoModeBoth: "Local + SSO",
    ssoIssuerHint: "Full OIDC issuer URL from your provider.",
    ssoClientIdHint: "Public client ID for your OIDC application.",
    ssoClientSecretHint: "Secret sent to your provider's token endpoint.",
    ssoRedirectHint: "Usually your CleanArr public URL + /api/auth/sso/callback.",
    ssoScopesHint: "Optional override for OIDC scope list.",
    ssoFieldDisabledHint: "SSO fields are disabled while auth mode is Password-only.",
    webhookMessageLabel: "Message:",
    webhookPayloadEventsLabel: "Payload events:",
    webhookNotificationLabel: "Notification:",
    webhookResultStatusLabel: "Processing result:",
    reasonLabel: "reason:",
    ssoModePasswordOnlyHint: "Use only local credentials. SSO fields are disabled.",
    ssoModeSsoOnlyHint: "Use only external identity provider authentication.",
    ssoModeBothHint: "Allow both local credentials and external identity provider authentication.",
    add: "Add",
    edit: "Edit",
    test: "Test",
    next: "Next",
    back: "Back",
    skipForNow: "Skip for now",
    done: "Done",
    enabled: "Enabled",
    runtimeTarget: "Mark as preferred/default",
    displayName: "Display name",
    baseUrl: "Base URL",
    alreadyConfigured: "Already configured",
    ...SETUP_CONNECTION_COPY.en,
    beforeYouSave: "Before you save",
    beforeSaveDescription: "Paste the service URL and credentials, then run Test. The result must turn green before switching live.",
    webhook: "Webhook",
    notConfigured: "Not configured",
    healthy: "Healthy",
    unreachable: "Unreachable",
    noStatus: "No status",
    none: "None",
    active: "active",
    recent: "recent",
    dismiss: "Dismiss",
    progress: "progress",
    actions: "actions",
    deletion: "deletion",
    unexpectedRequestError: "Unexpected request error",
    unknownError: "Unknown error",
    passwordsDoNotMatch: "Passwords do not match.",
    adminCreated: "Administrator created. Use the setup wizard to configure your services.",
    signedIn: "Signed in successfully.",
    deletionStarted: "Deletion started in the background.",
    backgroundRefreshFailed: "Could not refresh background tasks",
    serviceUpdated: "updated",
    serviceAdded: "added",
    serviceRemoved: "removed",
    runtimeSettingsSummary: "Runtime settings: log level, HTTP timeout, activity retention, metadata language, SSO, and webhook token.",
    jellyfinLanguageHint: "Used when requesting series and movie titles from Jellyfin metadata.",
    uiLanguageHint: "Changes the language of the CleanArr interface.",
    runtimeSettingsDescription: "Changes are persisted and immediately rebuild the live runtime.",
    recommendedFirstRun: "Recommended first-run settings",
    recommendedDryRun: "Leave Dry Run enabled while you validate every downstream integration.",
    httpTimeoutHint: "Increase only if your Arr services are slow to respond.",
    retentionHint: "Events older than this are deleted from the SQLite database.",
    closeAndRefresh: "Close this window and refresh the configuration.",
    keepDryRun: "Keep CleanArr in Dry Run",
    oneDay: "1 day",
    sevenDays: "7 days",
    thirtyDays: "30 days",
    ninetyDays: "90 days",
    oneYear: "1 year",
    serviceRadarrDescription: "Movie cleanup target used to resolve and delete movies.",
    serviceSonarrDescription: "Series, season, and episode cleanup target.",
    serviceSeerrDescription: "Request and issue cleanup target.",
    serviceDownloaderDescription: "One or more torrent clients used for ownership lookup and safe hash deletion.",
    serviceJellyfinDescription: "Jellyfin media server used for library browsing and immediate item removal.",
    apiKey: "API key",
    exampleUrl: "Example URL",
    reverseProxyHint: "Reverse-proxy paths are supported.",
    serviceUrlHint: "Paste the service URL only. CleanArr appends the correct API path automatically.",
    downloaderUrlHint: "Paste the client base URL. CleanArr adds the default RPC path when it is omitted.",
    radarrApiHint: "Radarr → Settings → General → Security → API Key.",
    sonarrApiHint: "Sonarr → Settings → General → Security → API Key.",
    seerrApiHint: "Seerr → Settings → General → API Key.",
    downloaderUsernameHint: "Username for the selected client's Web or RPC interface, when authentication is enabled.",
    downloaderPasswordHint: "Password for the selected client's Web or RPC interface, when authentication is enabled.",
    qbittorrentApiHint: "qBittorrent 5.2+ API key; leave empty to use username and password.",
    delugePasswordHint: "Password for the Deluge Web JSON-RPC interface.",
    torrentClient: "Torrent client",
    allEnabledRouting: "All enabled Radarr, Sonarr, and torrent-client instances participate in routing.",
    disabled: "Disabled",
    defaultLabel: "Default",
    seedingPolicy: "Torrent removal policy",
    seedingImmediate: "Remove immediately",
    seedingKeep: "Keep torrent",
    seedingDefer: "Defer until seeded",
    minSeedRatio: "Minimum seed ratio",
    minSeedTime: "Minimum seed time (minutes)",
    seedingPolicyHint: "Applied independently by each enabled torrent client before removal.",
    seedingThresholdHint: "Set at least one threshold. If both are set, both must be reached.",
    jellyfinApiHint: "Jellyfin → Dashboard → API Keys → + → create a key for CleanArr.",
    firstTimeSetup: "First-time setup — configure each service to get started.",
    autoConfigureWebhook: "Auto-configure webhook",
    autoConfigureWebhookDescription: "CleanArr configures the Jellyfin Webhook plugin automatically. The plugin must already be installed in Jellyfin.",
    connectJellyfinFirst: "Connect the Jellyfin server before auto-configuring the webhook.",
    setWebhookTokenFirst: "Set a webhook token in Runtime settings first — it will be included in the plugin config.",
    configuring: "Configuring…",
    configured: "Configured",
    installJellyfinWebhook: "Install the Jellyfin Webhook plugin",
    installJellyfinWebhookDescription: "Jellyfin → Dashboard → Plugins → Catalog → search Webhook → install → restart if prompted.",
    jellyfinInstallStep1: "Open Jellyfin → Dashboard → Catalog.",
    jellyfinInstallStep2: "Find the plugin named Webhook and install it.",
    jellyfinInstallStep3: "Restart Jellyfin if the plugin manager asks for it.",
    jellyfinInstallStep4: "After restart, open Jellyfin → Dashboard → Plugins → Webhook.",
    verifyDelivery: "Verify delivery",
    verifyDeliveryDescription: "CleanArr records every inbound webhook attempt so you can confirm delivery without a real deletion event.",
    deliveryStatus: "Delivery status",
    lastAttempt: "Last attempt",
    httpStatus: "HTTP status",
    lastItem: "Last item",
    notReceivedYet: "Not received yet",
    noItemReceived: "No item received yet",
    processing: "Processing",
    latestWebhookAttempt: "Latest webhook attempt",
    noJellyfinWebhook: "No Jellyfin webhook has reached CleanArr yet.",
    smokeTestCurl: "Smoke test (cURL)",
    tokenPrefilled: "token pre-filled",
    configureTokenFirst: "configure token first",
    smokeTestDescription: "Sends a synthetic ItemDeleted event to CleanArr. Use it to confirm network connectivity and token authentication before a real deletion.",
    copyCurl: "Copy cURL",
    generalSetupStep1: "Keep CleanArr in Dry Run until all services test green.",
    generalSetupStep2: "Set a webhook token. Jellyfin must send the same X-Webhook-Token header.",
    generalSetupStep3: "Only switch to Live mode after all downstream services are configured.",
    tryDifferentSearch: "Try a different search term.",
    noSeriesSetup: "Sonarr returned no series. Configure Sonarr in Setup first.",
    noMoviesSetup: "Radarr returned no movies. Configure Radarr in Setup first.",
    onDisk: "On disk",
    noFile: "No file",
    episodes: "episodes",
    seasons: "seasons",
    dryRunNoChanges: "No actual changes will be made.",
    seasonOfSeries: "Season {{season}} of {{series}}",
    movie: "Movie",
    item: "Item",
    webhookReceived: "Webhook received",
    tokenMismatch: "Token mismatch",
    payloadRejected: "Payload rejected",
    noDeliveryYet: "No delivery yet",
    partialFailure: "Partial failure",
    success: "Success",
    failed: "Failed",
    deleted: "Deleted",
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    skipped: "Skipped",
    unknown: "Unknown",
  },
  ru: {
    dashboard: "Панель",
    settings: "Настройки",
    activity: "Активность",
    library: "Библиотека",
    downloads: "Загрузки",
    downloadsActive: "активно",
    storageProvenance: "CleanArr получает свободное место для каждой папки медиатеки из настроенного Radarr или Sonarr. Пути и учётные данные остаются скрыты.",
    serviceDetails: "Технические сведения",
    recentActivitySummary: "Последняя активность",
    recentActivitySummaryDescription: "Последний результат доставки или очистки; технические сведения доступны при необходимости.",
    recentActivityProcessed: "Проверка очистки: {{item}}",
    recentActivityWebhook: "Событие медиасервера: {{item}}",
    eventDetails: "Сведения о событии",
    technicalDetails: "Технические сведения",
    viewDetails: "Открыть сведения",
    activityPageDescription: "Просматривайте результаты проверок очистки и события медиасервера. Подробности открываются только при необходимости.",
    live: "Включен",
    dryRun: "Тестовый режим",
    liveMode: "Рабочий режим",
    liveModeDescription: "Выполняются реальные удаления",
    dryRunDescription: "Реальные удаления отключены",
    status: "Статус",
    setup: "Настройка",
    setupWizard: "Мастер настройки",
    connectedServices: "Подключённые сервисы",
    webhookStatus: "Состояние webhook",
    latestEvent: "Последнее событие",
    webhookStatusDescription: "Последняя попытка доставки webhook от Jellyfin.",
    latestEventDescription: "Последний обработанный элемент.",
    noWebhookReceived: "Webhook пока не получен",
    logOut: "Выйти",
    navigation: "Основная навигация",
    runtimeSettingsSaved: "Настройки сохранены.",
    save: "Сохранить",
    saveChanges: "Сохранить изменения",
    saveSettings: "Сохранить настройки",
    cancel: "Отмена",
    delete: "Удалить",
    deleteSeries: "Удалить сериал",
    deleteItem: "Удалить фильм",
    series: "Сериалы",
    movies: "Фильмы",
    refresh: "Обновить",
    filter: "Фильтр",
    clear: "Очистить",
    activityTimeline: "Журнал активности",
    activityTimelineDescription: "Входящие webhooks от Jellyfin и события удаления в едином потоке.",
    eventCount: "событие",
    noActivityFiltered: "По текущему фильтру ничего не найдено.",
    noActivity: "Пока активности нет",
    noActivityDescription: "События отсутствуют.",
    noActivityWebhook: "Событий пока нет",
    sendWebhookToSeeActivity: "Отправьте webhook из Jellyfin или обработайте событие очистки, чтобы видеть историю.",
    sendWebhookForStatus: "Отправьте webhook из Jellyfin для получения статуса доставки.",
    noWebhookAttempts: "Попыток webhook пока нет.",
    webhookAttempts: "Попыток webhook пока нет.",
    setupCount: "Прогресс настройки",
    deletionsLogged: "удалений в журнале",
    noWebhookActivity: "Пока событий от webhook не было.",
    noItemsYet: "Записей пока нет.",
    noSeriesFound: "Сериалы не найдены",
    noSeriesMatch: "Нет совпадений по вашему запросу",
    noSeasonsFound: "Сезоны с эпизодами не найдены.",
    season: "Сезон",
    searchPlaceholderSeries: "Поиск сериалов…",
    searchPlaceholderMovies: "Поиск фильмов…",
    libraryDescription:
      "Просматривайте медиатеку и проверяйте привязанный к безопасности план очистки для настроенных сервисов перед подтверждением.",
    dryRunModeInfo: "Тестовый режим",
    noLiveChanges: "Реальные изменения не выполняются. Включите рабочий режим в настройках приложения, чтобы разрешить удаление.",
    deleteButton: "Удалить",
    confirmDelete: "Удалить",
    simulate: "Симулировать (тест)",
    confirmDeleteDescription:
      "Проверьте точный план перед подтверждением. Действия без полного доказательства владения сохраняются или блокируются.",
    titleDeleteConfirmation: "Удалить {{title}}?",
    dryRunModeNotice: "Тестовый режим",
    titleNotConfigured: "Метод авторизации сейчас не настроен.",
    backgroundTasks: "Фоновые задачи",
    preflightPlan: "Точный план удаления",
    preflightPlanHint: "Подтверждайте удаление только после проверки целей и защитных пропусков ниже.",
    preflightLoading: "Определяем цели и выполняем проверки безопасности…",
    preflightUnavailable: "Подтверждение недоступно, пока план не загружен без ошибок.",
    noPlannedActions: "Действия во внешних сервисах не найдены.",
    attempt: "попытка",
    planning: "Проверка плана",
    retrying: "Ожидание повтора",
    searchMovies: "Поиск фильмов…",
    noMoviesFound: "Фильмы не найдены",
    noMoviesMatch: "Нет совпадений по вашему поиску",
    general: "Общее",
    settingsUnavailable: "Настройки недоступны",
    tryAgain: "Обновите конфигурацию и повторите.",
    runtimeSettings: "Настройки приложения",
    appBehaviour: "Параметры работы и поведения приложения.",
    logLevel: "Уровень логирования",
    httpTimeoutSeconds: "Тайм-аут HTTP (с)",
    activityRetention: "Хранение активности",
    jellyfinMetadataLanguage: "Язык метаданных Jellyfin",
    uiLanguage: "Язык интерфейса",
    webhookToken: "Токен webhook",
    hideToken: "Скрыть токен",
    showToken: "Показать токен",
    regenerateToken: "Пересоздать токен",
    copyToken: "Копировать токен",
    tokenHint:
      "Генерируется автоматически. Пересоздайте только если нужно обновить ключ; затем повторите автонастройку в шаге Jellyfin.",
    allSettingsSaved: "Все настройки сохранены.",
    unsavedChanges: "Есть несохранённые изменения.",
    firstLaunchCreateAdmin: "Первый запуск — создайте учётную запись администратора.",
    signInWithLocalOrSso: "Войти с локальными учётными данными или через SSO.",
    signInWithLocalOnly: "Войти с локальными учётными данными.",
    signInWithSso: "Войти через SSO",
    authTitleSignIn: "Вход",
    authTitleCreateAdmin: "Создать администратора",
    username: "Имя пользователя",
    password: "Пароль",
    confirmPassword: "Подтвердите пароль",
    signInWithCredentials: "Войти через учётные данные",
    orDivider: "или",
    ssoSignInError: "Ошибка входа по SSO",
    continueWithSso: "Продолжить через SSO",
    ssoNotConfigured: "SSO ещё не настроен",
    connecting: "Подключение...",
    configureSsoBefore: "Настройте SSO в настройках приложения, затем перезагрузите экран.",
    noAuthConfigured: "Метод авторизации не настроен.",
    requestFailed: "Ошибка запроса",
    ssoAuthMode: "Режим SSO",
    ssoIssuer: "URL issuer",
    ssoClientId: "Client ID",
    ssoClientSecret: "Client Secret",
    ssoRedirectUri: "Redirect URI",
    ssoScopes: "Scopes",
    ssoAllowedUsers: "Разрешённые пользователи",
    ssoAllowedGroups: "Разрешённые группы",
    ssoGroupClaim: "Claim с группами",
    ssoRequiredClaim: "Обязательный claim",
    ssoRequiredValue: "Значение обязательного claim",
    ssoAccessPolicyHint:
      "Доступ по умолчанию запрещён. Пользователь должен совпасть с разрешённым пользователем или группой; обязательный claim служит дополнительным условием. Можно использовать только обязательный claim.",
    ssoModePasswordOnly: "Только локальные учётные данные",
    ssoModeSsoOnly: "Только SSO",
    ssoModeBoth: "Локально + SSO",
    ssoIssuerHint: "Полный URL OIDC issuer вашего провайдера.",
    ssoClientIdHint: "Public client ID вашей OIDC интеграции.",
    ssoClientSecretHint: "Секрет для токен endpoint провайдера.",
    ssoRedirectHint: "Обычно это CleanArr public URL + /api/auth/sso/callback.",
    ssoScopesHint: "Дополнительный список scope (необязательно).",
    ssoFieldDisabledHint: "SSO поля отключены в режиме только локальной авторизации.",
    webhookMessageLabel: "Сообщение:",
    webhookPayloadEventsLabel: "Событий в payload:",
    webhookNotificationLabel: "Уведомление:",
    webhookResultStatusLabel: "Результат обработки:",
    reasonLabel: "причина:",
    ssoModePasswordOnlyHint: "Только локальные учётные данные. Поля SSO отключены.",
    ssoModeSsoOnlyHint: "Только внешняя аутентификация через OIDC.",
    ssoModeBothHint: "Локальная и SSO авторизация включены.",
    add: "Добавить",
    edit: "Изменить",
    test: "Проверить",
    next: "Далее",
    back: "Назад",
    skipForNow: "Пропустить пока",
    done: "Готово",
    enabled: "Включено",
    runtimeTarget: "Отметить как предпочтительный/default",
    displayName: "Отображаемое имя",
    baseUrl: "Базовый URL",
    alreadyConfigured: "Уже настроено",
    ...SETUP_CONNECTION_COPY.ru,
    beforeYouSave: "Перед сохранением",
    beforeSaveDescription: "Укажите URL и учётные данные сервиса, затем запустите проверку. До включения рабочего режима результат должен быть успешным.",
    webhook: "Webhook",
    notConfigured: "Не настроено",
    healthy: "Доступен",
    unreachable: "Недоступен",
    noStatus: "Нет статуса",
    none: "Нет",
    active: "активных",
    recent: "недавних",
    dismiss: "Скрыть",
    progress: "прогресс",
    actions: "действий",
    deletion: "удаление",
    unexpectedRequestError: "Неожиданная ошибка запроса",
    unknownError: "Неизвестная ошибка",
    passwordsDoNotMatch: "Пароли не совпадают.",
    adminCreated: "Администратор создан. Настройте сервисы в мастере настройки.",
    signedIn: "Вход выполнен.",
    deletionStarted: "Удаление запущено в фоне.",
    backgroundRefreshFailed: "Не удалось обновить фоновые задачи",
    serviceUpdated: "обновлён",
    serviceAdded: "добавлен",
    serviceRemoved: "удалён",
    runtimeSettingsSummary: "Параметры приложения: журналирование, HTTP-таймаут, срок хранения событий, язык метаданных, SSO и токен webhook.",
    jellyfinLanguageHint: "Используется при запросе названий сериалов и фильмов из метаданных Jellyfin.",
    uiLanguageHint: "Изменяет язык интерфейса CleanArr.",
    runtimeSettingsDescription: "Изменения сохраняются и сразу применяются к работающему приложению.",
    recommendedFirstRun: "Рекомендуемые настройки первого запуска",
    recommendedDryRun: "Оставьте тестовый режим включённым, пока не проверите все интеграции.",
    httpTimeoutHint: "Увеличивайте только если сервисы Arr отвечают слишком медленно.",
    retentionHint: "Более старые события удаляются из базы данных SQLite.",
    closeAndRefresh: "Закройте это окно и обновите конфигурацию.",
    keepDryRun: "Оставить CleanArr в тестовом режиме",
    oneDay: "1 день",
    sevenDays: "7 дней",
    thirtyDays: "30 дней",
    ninetyDays: "90 дней",
    oneYear: "1 год",
    serviceRadarrDescription: "Сервис поиска и удаления фильмов.",
    serviceSonarrDescription: "Сервис поиска и удаления сериалов, сезонов и эпизодов.",
    serviceSeerrDescription: "Сервис очистки запросов и обращений.",
    serviceDownloaderDescription: "Один или несколько torrent-клиентов для поиска владельца и безопасного удаления раздач.",
    serviceJellyfinDescription: "Медиасервер для просмотра библиотеки и немедленного удаления элементов.",
    apiKey: "API-ключ",
    exampleUrl: "Пример URL",
    reverseProxyHint: "Поддерживаются пути через обратный прокси.",
    serviceUrlHint: "Укажите только URL сервиса. CleanArr автоматически добавит правильный путь API.",
    downloaderUrlHint: "Укажите базовый URL клиента. CleanArr добавит стандартный путь RPC, если он не указан.",
    radarrApiHint: "Radarr → Настройки → Общие → Безопасность → API Key.",
    sonarrApiHint: "Sonarr → Настройки → Общие → Безопасность → API Key.",
    seerrApiHint: "Seerr → Настройки → Общие → API Key.",
    downloaderUsernameHint: "Имя пользователя выбранного Web/RPC-интерфейса, если включена аутентификация.",
    downloaderPasswordHint: "Пароль выбранного Web/RPC-интерфейса, если включена аутентификация.",
    qbittorrentApiHint: "API key qBittorrent 5.2+; оставьте поле пустым для username/password.",
    delugePasswordHint: "Пароль Web JSON-RPC интерфейса Deluge.",
    torrentClient: "Torrent-клиент",
    allEnabledRouting: "Все включённые экземпляры Radarr, Sonarr и torrent-клиентов участвуют в маршрутизации.",
    disabled: "Отключено",
    defaultLabel: "Основной",
    seedingPolicy: "Политика удаления раздачи",
    seedingImmediate: "Удалять сразу",
    seedingKeep: "Оставлять раздачу",
    seedingDefer: "Ждать выполнения условий",
    minSeedRatio: "Минимальный ratio",
    minSeedTime: "Минимальное время раздачи (минуты)",
    seedingPolicyHint: "Применяется отдельно каждым включённым torrent-клиентом перед удалением.",
    seedingThresholdHint: "Укажите хотя бы один порог. Если указаны оба, должны быть выполнены оба.",
    jellyfinApiHint: "Jellyfin → Панель управления → API Keys → + → создайте ключ для CleanArr.",
    firstTimeSetup: "Первичная настройка — подключите необходимые сервисы.",
    autoConfigureWebhook: "Настроить webhook автоматически",
    autoConfigureWebhookDescription: "CleanArr автоматически настроит плагин Webhook в Jellyfin. Плагин должен быть заранее установлен.",
    connectJellyfinFirst: "Сначала подключите сервер Jellyfin, затем настройте webhook.",
    setWebhookTokenFirst: "Сначала задайте токен webhook в настройках приложения — он будет добавлен в конфигурацию плагина.",
    configuring: "Настройка…",
    configured: "Настроено",
    installJellyfinWebhook: "Установите плагин Webhook для Jellyfin",
    installJellyfinWebhookDescription: "Jellyfin → Панель управления → Плагины → Каталог → найдите Webhook → установите → при необходимости перезапустите Jellyfin.",
    jellyfinInstallStep1: "Откройте Jellyfin → Панель управления → Каталог.",
    jellyfinInstallStep2: "Найдите плагин Webhook и установите его.",
    jellyfinInstallStep3: "Перезапустите Jellyfin, если этого потребует менеджер плагинов.",
    jellyfinInstallStep4: "После перезапуска откройте Jellyfin → Панель управления → Плагины → Webhook.",
    verifyDelivery: "Проверка доставки",
    verifyDeliveryDescription: "CleanArr сохраняет каждую попытку webhook, поэтому доставку можно проверить без реального удаления.",
    deliveryStatus: "Статус доставки",
    lastAttempt: "Последняя попытка",
    httpStatus: "Статус HTTP",
    lastItem: "Последний элемент",
    notReceivedYet: "Пока не получено",
    noItemReceived: "Элементы пока не получены",
    processing: "Обработка",
    latestWebhookAttempt: "Последняя попытка webhook",
    noJellyfinWebhook: "Webhook из Jellyfin ещё не поступал в CleanArr.",
    smokeTestCurl: "Проверочный запрос (cURL)",
    tokenPrefilled: "токен уже подставлен",
    configureTokenFirst: "сначала настройте токен",
    smokeTestDescription: "Отправляет синтетическое событие ItemDeleted в CleanArr. Используйте его для проверки сети и токена до реального удаления.",
    copyCurl: "Копировать cURL",
    generalSetupStep1: "Оставьте CleanArr в тестовом режиме, пока все проверки сервисов не будут успешными.",
    generalSetupStep2: "Задайте токен webhook. Jellyfin должен отправлять его в заголовке X-Webhook-Token.",
    generalSetupStep3: "Включайте рабочий режим только после настройки всех внешних сервисов.",
    tryDifferentSearch: "Попробуйте изменить поисковый запрос.",
    noSeriesSetup: "Sonarr не вернул сериалов. Сначала настройте Sonarr.",
    noMoviesSetup: "Radarr не вернул фильмов. Сначала настройте Radarr.",
    onDisk: "На диске",
    noFile: "Файла нет",
    episodes: "эпизодов",
    seasons: "сезонов",
    dryRunNoChanges: "Реальные изменения не выполняются.",
    seasonOfSeries: "Сезон {{season}} сериала {{series}}",
    movie: "Фильм",
    item: "Элемент",
    webhookReceived: "Webhook получен",
    tokenMismatch: "Токен не совпадает",
    payloadRejected: "Данные отклонены",
    noDeliveryYet: "Доставок пока нет",
    partialFailure: "Частичная ошибка",
    success: "Успешно",
    failed: "Ошибка",
    deleted: "Удалено",
    queued: "В очереди",
    running: "Выполняется",
    completed: "Завершено",
    skipped: "Пропущено",
    unknown: "Неизвестно",
  },
}
const FALLBACK_UI_TEXTS: Record<string, Partial<UiTextMap>> = {
  de: { series: "Serien", movies: "Filme", deleteSeries: "Serie löschen", deleteItem: "Film löschen" },
  fr: { series: "Séries", movies: "Films", deleteSeries: "Supprimer la série", deleteItem: "Supprimer le film" },
  es: { series: "Series", movies: "Películas", deleteSeries: "Eliminar serie", deleteItem: "Eliminar película" },
  it: { series: "Serie", movies: "Film", deleteSeries: "Elimina serie", deleteItem: "Elimina film" },
  pt: { series: "Séries", movies: "Filmes", deleteSeries: "Eliminar série", deleteItem: "Eliminar filme" },
  tr: { series: "Diziler", movies: "Filmler", deleteSeries: "Diziyi sil", deleteItem: "Filmi sil" },
  pl: { series: "Seriale", movies: "Filmy", deleteSeries: "Usuń serial", deleteItem: "Usuń film" },
  uk: { series: "Серіали", movies: "Фільми", deleteSeries: "Видалити серіал", deleteItem: "Видалити фільм" },
  cs: { series: "Seriály", movies: "Filmy", deleteSeries: "Smazat seriál", deleteItem: "Smazat film" },
  zh: { series: "剧集", movies: "电影", deleteSeries: "删除剧集", deleteItem: "删除电影" },
  ja: { series: "シリーズ", movies: "映画", deleteSeries: "シリーズを削除", deleteItem: "映画を削除" },
}

export const DEFAULT_UI_LANG = "en"

export function resolveUiLanguage(value: string | null | undefined): string {
  if (!value) return DEFAULT_UI_LANG
  return value.trim().replace("_", "-").toLowerCase().split("-", 1)[0]
}

export function getUiText(value: string | null | undefined): UiTextMap {
  const language = resolveUiLanguage(value)
  const languageOverride = UI_TEXTS[language] ?? FALLBACK_UI_TEXTS[language] ?? {}
  const translations = { ...UI_TEXTS[DEFAULT_UI_LANG], ...languageOverride }
  return translations as UiTextMap
}
