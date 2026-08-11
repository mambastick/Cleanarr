# Release process

[English](RELEASING.md) · [Русский](RELEASING_RU.md)

CleanArr release notes are always written in Russian and English. A release tag publishes the multi-architecture container image and native DEB/RPM packages from the same commit.

## Prepare

1. Update the version in `backend/pyproject.toml` and `backend/src/cleanarr/api/app.py`.
2. Add `docs/releases/vX.Y.Z.md` using this exact structure:

```markdown
## Русский

### Изменения

- ...

## English

### Changes

- ...
```

3. Run backend tests, frontend build, Docker build, and the native package smoke tests.
4. Merge the release commit into `main`.

## Publish

```bash
git tag -a vX.Y.Z -m "CleanArr X.Y.Z"
git push origin main vX.Y.Z
```

`.github/workflows/docker-release.yml` then:

- builds and publishes GHCR images for `linux/amd64` and `linux/arm64`;
- builds DEB and RPM packages for `amd64` and `arm64` on native runners;
- creates or updates the GitHub Release with `docs/releases/vX.Y.Z.md`;
- uploads packages and `SHA256SUMS`.

Do not move or recreate a published tag. If artifact publication must be recovered, use the manual workflow with the existing tag and confirm that the source version matches it.

## Manual artifact recovery

```bash
gh workflow run docker-release.yml \
  -f release_tag=vX.Y.Z \
  -f publish=true
```

This rebuilds native packages from the current default branch. Use it only when that branch still contains the exact tagged application version.
