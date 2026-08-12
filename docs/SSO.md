# OpenID Connect and reverse proxy

[English](SSO.md) · [Русский](SSO_RU.md)

CleanArr accepts OIDC identities only after validating provider discovery,
JWKS signature, an asymmetric algorithm allowlist, issuer, audience, expiry,
issued-at time, nonce, and the configured access policy. The authorization
code is additionally bound with PKCE S256. An access token is never accepted
as a replacement for a missing or invalid ID token.

## Provider application

Create a confidential OpenID Connect client with:

- authorization code flow;
- redirect URI `https://cleanarr.example/api/auth/sso/callback`;
- scopes `openid profile email` plus the scope that emits the configured group
  or custom claim;
- PKCE S256 support;
- an asymmetric ID-token signing algorithm such as RS256, PS256, ES256, or
  EdDSA;
- `client_secret_basic` or `client_secret_post` token endpoint authentication.

The configured issuer must exactly match the discovery document's `issuer`,
including its path and trailing slash. Provider endpoints must use HTTPS;
plain HTTP is accepted only on a loopback hostname for local development.

## Access policy

CleanArr fails closed: valid authentication alone does not grant administration.
Configure at least one policy in Settings or via environment variables:

- `SSO_ALLOWED_USERS`: usernames, emails, UPNs, or subjects;
- `SSO_ALLOWED_GROUPS` together with `SSO_GROUP_CLAIM` (default `groups`);
- `SSO_REQUIRED_CLAIM` together with `SSO_REQUIRED_VALUE`.

User and group allowlists are alternatives: matching either allows the
identity. A required claim is an additional condition when an allowlist is
also present. A required claim/value pair by itself is a complete policy.
Comparisons are case-insensitive and exact; partial or substring matches are
not accepted.

Start with `SSO_MODE=both`, test local and OIDC login in separate browser
sessions, and only then switch to `sso_only`. Use `both` permanently if a local
break-glass account is required.

## Upgrade from 0.4.x

Create and verify the SQLite backup documented in the Docker or native-package
installation guide before upgrading. CleanArr migrates an unversioned 0.4
runtime configuration through ordered schema versions 1 and 2 while preserving
the local administrator and existing OIDC client settings. Existing OIDC access
fails closed after the upgrade until an explicit allowlist or required
claim/value policy is saved; local login remains available only when the mode
is `password_only` or `both`.

To roll back, stop CleanArr, pin the previous image or package, restore the
verified pre-upgrade database, and start the previous version. Keep the failed
database separately until the restored login and configuration are verified.

## Reverse proxy contract

Terminate TLS at a trusted proxy, preserve the original `Host`, and send
forwarded headers only from the proxy network. Do not expose the application
port directly to untrusted clients when forwarded headers are enabled.

Set an explicit public `SSO_REDIRECT_URI`. If the proxy is not in Uvicorn's
trusted forwarded-IP set, also set `SESSION_COOKIE_SECURE=true`; otherwise the
backend sees internal HTTP and cannot infer the public HTTPS scheme. Verify in
browser developer tools that `cleanarr_session` has `Secure`, `HttpOnly`,
`SameSite=Strict`, a seven-day maximum age, and path `/`.

CleanArr checks `Origin` (or `Referer` as a fallback) and a per-session CSRF
token on every cookie-authenticated POST/PUT/PATCH/DELETE request. Automation
should use `Authorization: Bearer <ADMIN_SHARED_TOKEN>` or `X-Admin-Token`
instead of browser cookies; header-token requests do not use CSRF tokens.
The OIDC `state` value is additionally bound to a short-lived, `HttpOnly`,
`SameSite=Lax` callback cookie so a login started in another browser is rejected.

## Troubleshooting

- **SSO is not configured:** add an explicit access policy as well as issuer,
  client ID, client secret, and redirect URI.
- **Discovery issuer mismatch:** copy the issuer exactly from the discovery
  response; do not use an authorization endpoint URL.
- **Token validation or access policy failed:** verify the ID-token signing
  algorithm, audience/client ID, clock synchronization, nonce-capable code
  flow, and exact claim values.
- **Login succeeds but mutations return 403:** do not copy browser cookies into
  scripts; use the header-token automation interface. In the UI, reload the
  page to refresh the CSRF token.
- **Cookie is not Secure:** set `SESSION_COOKIE_SECURE=true` and verify TLS
  termination and forwarded-header trust.
