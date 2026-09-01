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

3. Run backend tests, frontend build, Docker build, native package smoke tests,
   the digest-pinned real-service compatibility stack, and the upgrade/rollback
   rehearsal documented in [Compatibility matrix](COMPATIBILITY.md).
4. Merge the release commit into `main`.

For a future release containing the post-1.0 Downloads/deletion slice, run the
candidate compatibility profile that proves normalized reads and pause/resume
for all four adapters, then rehearse the latest stable v1.0.0 state into the
candidate v5/config-v3 schema and back through a verified backup. Keep the
direct populated v4-to-v5 migration test as separate evidence. Do not describe
those contracts as certified until all evidence passes from the release commit.

## Publish

```bash
git tag -a vX.Y.Z -m "CleanArr X.Y.Z"
git push origin main vX.Y.Z
```

`.github/workflows/docker-release.yml` then:

- blocks publication until the ordinary quality suite and real-service
  compatibility/upgrade gate both pass from a clean checkout;
- builds and publishes GHCR images for `linux/amd64` and `linux/arm64`;
- builds DEB and RPM packages for `amd64` and `arm64` on native runners;
- creates or updates the GitHub Release with `docs/releases/vX.Y.Z.md`;
- uploads packages, SPDX JSON SBOMs, and `SHA256SUMS`;
- creates signed GitHub artifact attestations for release files and build/SBOM
  attestations for the GHCR image digest.

The required quality workflow fails on fixable high/critical dependency or
container vulnerabilities, committed secrets, and high/critical deployment
misconfiguration findings reported by Trivy. A release must not bypass a red
scan. The compatibility workflow must also prove the published dependency
matrix and backup-based rollback. A release must not bypass either red gate.

## Verify downloaded artifacts

```bash
sha256sum --check SHA256SUMS
gh attestation verify cleanarr_X.Y.Z_amd64.deb -R mambastick/Cleanarr
gh attestation verify oci://ghcr.io/mambastick/cleanarr:X.Y.Z -R mambastick/Cleanarr
```

The checksum proves that a download matches the release manifest. The
attestation additionally binds the artifact or image digest to this repository,
commit, and GitHub Actions build identity. SPDX JSON files in the release assets
describe the container and native-package dependency sets.

Do not move or recreate a published tag. If artifact publication must be recovered, use the manual workflow with the existing tag and confirm that the source version matches it.

## Manual artifact recovery

```bash
gh workflow run docker-release.yml \
  -f release_tag=vX.Y.Z \
  -f publish=true
```

This rebuilds native packages from the current default branch. Use it only when
that branch still contains the exact tagged application version. Manual recovery
does not republish the container image; preserve and verify its original
digest-bound attestations.
