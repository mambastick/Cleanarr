# Security Policy

[English](SECURITY.md) · [Русский](SECURITY_RU.md)

## Supported versions

Only the latest release on `main` is actively maintained.

## Reporting a vulnerability

**Please do not open a public GitHub Issue for security vulnerabilities.**

Report security issues privately via [GitHub Security Advisories](../../security/advisories/new).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigation

You can expect an acknowledgement within 72 hours and a fix or mitigation plan within 14 days, depending on severity.

## Scope

CleanArr is a self-hosted application intended for use on private home networks. Key security considerations:

- Interactive access is protected by a local account, OpenID Connect SSO, or both. OIDC validates discovery/JWKS signatures, algorithm, issuer, audience, expiry, nonce, and an explicit access policy. Keep `both` mode with a tested local account when a break-glass login is required; local login is intentionally disabled in `sso_only` mode.
- Browser sessions use an `HttpOnly`, `SameSite=Strict` cookie plus a per-session CSRF token and same-origin checks for mutations. Set `SESSION_COOKIE_SECURE=true` behind a TLS reverse proxy when forwarded HTTPS metadata is not trusted by the application process.
- `ADMIN_SHARED_TOKEN` is an optional automation bypass. Treat it as a privileged secret and leave it unset unless it is required.
- Webhook delivery uses a shared token (`X-Webhook-Token`). Rotate it via Settings → General → Regenerate if compromised, then re-run auto-configure in the Jellyfin modal.
- API keys, the local account, and SSO settings are stored in the local SQLite database. Protect and back up `/config` (containers) or `/var/lib/cleanarr` (native packages).
- Terminate TLS at a trusted reverse proxy and do not expose the application over plain HTTP outside a trusted network.
