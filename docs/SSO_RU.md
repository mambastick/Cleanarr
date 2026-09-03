# OpenID Connect и reverse proxy

[English](SSO.md) · [Русский](SSO_RU.md)

CleanArr принимает OIDC identity только после проверки discovery провайдера,
JWKS-подписи, разрешённого асимметричного алгоритма, issuer, audience, срока
действия, issued-at, nonce и настроенной access policy. Authorization code
дополнительно связывается через PKCE S256. Access token не используется вместо
отсутствующего или ошибочного ID token.

## Приложение у провайдера

Создайте confidential OpenID Connect client со следующими параметрами:

- authorization code flow;
- redirect URI `https://cleanarr.example/api/auth/sso/callback`;
- scopes `openid profile email` и scope, добавляющий настроенную группу или
  custom claim;
- поддержка PKCE S256;
- асимметричная подпись ID token, например RS256, PS256, ES256 или EdDSA;
- аутентификация token endpoint через `client_secret_basic` или
  `client_secret_post`.

Настроенный issuer должен точно совпадать с полем `issuer` discovery document,
включая path и завершающий slash. Endpoint провайдера должен использовать
HTTPS; обычный HTTP разрешён только на loopback hostname для локальной
разработки.

## Access policy

CleanArr работает fail closed: успешной аутентификации недостаточно для прав
администратора. Задайте в Settings или окружении хотя бы одну политику:

- `SSO_ALLOWED_USERS`: usernames, email, UPN или subject;
- `SSO_ALLOWED_GROUPS` вместе с `SSO_GROUP_CLAIM` (по умолчанию `groups`);
- `SSO_REQUIRED_CLAIM` вместе с `SSO_REQUIRED_VALUE`.

Allowlist пользователей и групп альтернативны: достаточно совпадения с одним
из них. Если одновременно задан required claim, он служит дополнительным
условием. Пара required claim/value без allowlist также является полной
политикой. Сравнение регистронезависимое и точное; частичные совпадения не
принимаются.

Допуск identity и её полномочия разделены. При SSO-only bootstrap первая
допущенная identity становится администратором. Когда хотя бы один
администратор уже существует, новые SSO identity по умолчанию получают роль
viewer и используют только ограниченное read-only workspace, пока
администратор не изменит их сохраняемую роль. Повторный вход не перезаписывает
назначенную роль, а CleanArr запрещает понизить последнего администратора.

Сначала используйте `SSO_MODE=both`, проверьте локальный и OIDC-вход в разных
browser sessions и только затем переключайтесь на `sso_only`. Если нужен
локальный break-glass вход, оставьте режим `both`.

## Обновление с 0.4.x

До обновления создайте и проверьте SQLite backup по инструкции для Docker или
нативного пакета. CleanArr последовательно мигрирует неверсионированный runtime
config 0.4 через версии схемы 1 и 2, сохраняя локального администратора и
настройки OIDC client. После обновления OIDC работает fail closed, пока не будет
сохранён явный allowlist или пара required claim/value; локальный вход доступен
только в режимах `password_only` и `both`.

Для отката остановите CleanArr, закрепите предыдущий образ или пакет,
восстановите проверенную БД до обновления и запустите предыдущую версию.
Не удаляйте неудачно обновлённую БД, пока не проверены вход и конфигурация после
restore.

## Контракт reverse proxy

Завершайте TLS на доверенном proxy, сохраняйте исходный `Host` и передавайте
forwarded headers только из сети proxy. Не публикуйте порт приложения для
недоверенных клиентов, если включено доверие к forwarded headers.

Задайте явный публичный `SSO_REDIRECT_URI`. Если proxy не входит в доверенный
для Uvicorn набор forwarded IP, также задайте `SESSION_COOKIE_SECURE=true`:
иначе backend видит внутренний HTTP и не может определить публичную HTTPS
схему. В browser developer tools проверьте у `cleanarr_session` флаги `Secure`,
`HttpOnly`, `SameSite=Strict`, срок семь дней и path `/`.

Для каждого cookie-authenticated POST/PUT/PATCH/DELETE CleanArr проверяет
`Origin` (или `Referer`) и индивидуальный CSRF token сессии. Для автоматизации
используйте `Authorization: Bearer <ADMIN_SHARED_TOKEN>` или `X-Admin-Token`, а
не browser cookie; header-token запросам CSRF token не нужен.
OIDC `state` дополнительно связывается с короткоживущей callback-cookie с
флагами `HttpOnly` и `SameSite=Lax`, поэтому вход, начатый в другом browser,
отклоняется.

## Диагностика

- **SSO is not configured:** кроме issuer, client ID, client secret и redirect
  URI задайте явную access policy.
- **Discovery issuer mismatch:** точно скопируйте issuer из discovery response;
  URL authorization endpoint для этого не подходит.
- **Token validation or access policy failed:** проверьте алгоритм подписи ID
  token, audience/client ID, синхронизацию времени, code flow с nonce и точные
  значения claims.
- **Вход работает, но мутации возвращают 403:** не копируйте browser cookies в
  скрипты; используйте header-token interface. В UI перезагрузите страницу для
  обновления CSRF token.
- **У cookie нет Secure:** задайте `SESSION_COOKIE_SECURE=true` и проверьте TLS
  termination и forwarded-header trust.
