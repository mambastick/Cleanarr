# Security Policy

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

- The admin API is protected by a shared token (`ADMIN_SHARED_TOKEN`). Do not expose CleanArr directly to the internet without authentication (e.g. a reverse proxy with auth).
- Webhook delivery uses a shared token (`X-Webhook-Token`). Rotate it via Settings → General → Regenerate if compromised, then re-run auto-configure in the Jellyfin modal.
- API keys for Radarr, Sonarr, Jellyfin, etc. are stored in the local SQLite database. Protect access to the `/config` volume.
