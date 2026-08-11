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

- Interactive access is protected by a local account, OpenID Connect SSO, or both. Keep a tested local break-glass account when using SSO-only mode.
- `ADMIN_SHARED_TOKEN` is an optional automation bypass. Treat it as a privileged secret and leave it unset unless it is required.
- Webhook delivery uses a shared token (`X-Webhook-Token`). Rotate it via Settings → General → Regenerate if compromised, then re-run auto-configure in the Jellyfin modal.
- API keys, the local account, and SSO settings are stored in the local SQLite database. Protect and back up `/config` (containers) or `/var/lib/cleanarr` (native packages).
- Terminate TLS at a trusted reverse proxy and do not expose the application over plain HTTP outside a trusted network.
