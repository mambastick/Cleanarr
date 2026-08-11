# Contributing to CleanArr

[English](CONTRIBUTING.md) · [Русский](CONTRIBUTING_RU.md)

Thank you for your interest in contributing! This document covers how to get started.

## Prerequisites

- Python 3.12+
- Node.js 24+ and pnpm 10
- Docker (for building the image)
- A running instance of at least one supported service (Jellyfin, Radarr, Sonarr, etc.) for integration testing

## Local development setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn cleanarr.api.app:app --reload
```

The API will be available at `http://localhost:8000`.

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

The dev server proxies `/api` to `http://localhost:8000` by default.

## How to contribute

1. **Fork** the repository and create a branch from `main`
2. **Make your changes** — keep commits focused and atomic
3. **Test** your changes manually against real services where possible
4. **Open a Pull Request** against `main` with a clear description of what and why

## Commit style

Follow the [Conventional Commits](https://www.conventionalcommits.org) format:

```
feat(scope): short description

Longer explanation if needed.
```

Common scopes: `backend`, `frontend`, `deploy`, `docs`.

## Reporting bugs

Open a [GitHub Issue](../../issues/new?template=bug_report.md) with:
- Steps to reproduce
- Expected vs actual behavior
- Logs from the CleanArr container (`kubectl logs` or `docker logs`)
- Versions of CleanArr and connected services

## Suggesting features

Open a [GitHub Issue](../../issues/new?template=feature_request.md) describing the use case and the proposed solution.

## Code style

- **Python**: formatted with `ruff format`, linted with `ruff check`
- **TypeScript/TSX**: formatted with Prettier (if configured), type-checked with `tsc --noEmit`

Please make sure `tsc --noEmit` passes before opening a PR.

## Releases

Every release must include Russian and English notes. Native `.deb` and `.rpm` packages are built for `amd64` and `arm64` from the same tag as the container image. Follow [the release guide](docs/RELEASING.md).
