# Native Linux packages

[English](LINUX_PACKAGES.md) · [Русский](LINUX_PACKAGES_RU.md)

CleanArr releases include native DEB and RPM packages for `amd64` and `arm64`. The package installs the application under `/opt/cleanarr`, creates a dedicated unprivileged user, and registers a hardened systemd service.

## Supported systems

- a systemd-based Linux distribution;
- Python 3.12 available as `/usr/bin/python3.12`;
- DEB: Ubuntu 24.04 or another compatible distribution that provides `python3.12`;
- RPM: Fedora or a RHEL-compatible distribution that provides `python3.12`.

The packages are currently unsigned. Always download them from the official GitHub Release and verify `SHA256SUMS` before installing.

## Download and verify

Download the package for your architecture and `SHA256SUMS` from the matching [GitHub Release](https://github.com/mambastick/Cleanarr/releases).

```bash
sha256sum --check SHA256SUMS --ignore-missing
```

Asset names use the following format:

- `cleanarr_<version>_amd64.deb`
- `cleanarr_<version>_arm64.deb`
- `cleanarr_<version>_amd64.rpm`
- `cleanarr_<version>_arm64.rpm`

## Install

### Debian and Ubuntu

```bash
sudo apt install ./cleanarr_<version>_amd64.deb
```

### Fedora and RHEL-compatible distributions

```bash
sudo dnf install ./cleanarr_<version>_amd64.rpm
```

Review `/etc/cleanarr/cleanarr.env`, then start the service:

```bash
sudo systemctl enable --now cleanarr
systemctl status cleanarr --no-pager
curl --fail http://127.0.0.1:8089/health/ready
```

Open `http://server-address:8089` and complete the setup wizard. `DRY_RUN=true` is the package default.

## Paths

| Path | Purpose |
|---|---|
| `/opt/cleanarr` | Packaged application and Python dependencies |
| `/etc/cleanarr/cleanarr.env` | Environment configuration; preserved on upgrade |
| `/var/lib/cleanarr` | SQLite database and runtime state |
| `/usr/lib/systemd/system/cleanarr.service` | systemd service |
| `/usr/bin/cleanarr` | Command-line launcher |

The service listens on `0.0.0.0:8089`. Put it behind a trusted TLS reverse proxy before exposing it outside a private network.

## Logs and health

```bash
journalctl -u cleanarr -f
curl --fail http://127.0.0.1:8089/health/live
curl --fail http://127.0.0.1:8089/health/ready
```

## Backup

Stop CleanArr briefly or use the SQLite backup API before copying the database.

```bash
sudo systemctl stop cleanarr
sudo cp -a /var/lib/cleanarr /var/lib/cleanarr.backup
sudo systemctl start cleanarr
```

Store the backup outside the server before an operating-system migration.

## Upgrade and rollback

Install the new package over the old one. The environment file and application data are retained.

```bash
sudo apt install ./cleanarr_<new-version>_amd64.deb
# or
sudo dnf install ./cleanarr_<new-version>_amd64.rpm

sudo systemctl restart cleanarr
```

To roll back, restore the database backup if a schema migration requires it, then install the previous package and restart the service.

## Remove

```bash
sudo apt remove cleanarr
# or
sudo dnf remove cleanarr
```

Removal intentionally keeps `/var/lib/cleanarr` and the `cleanarr` system user. Delete retained data only after making and verifying a backup.

## Build locally

Requirements: Node.js 24, pnpm 10, Python 3.12, Go 1.26, and nFPM 2.47.

```bash
go install github.com/goreleaser/nfpm/v2/cmd/nfpm@v2.47.0
bash packaging/build-linux-packages.sh 0.2.10 amd64
```

Artifacts are written to `dist/` by default.
