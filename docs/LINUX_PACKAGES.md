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

Stop CleanArr briefly and create a verified SQLite backup before an upgrade that
changes persistent state.

```bash
sudo systemctl stop cleanarr
sudo -u cleanarr /usr/bin/python3.12 -c 'import sqlite3; source=sqlite3.connect("/var/lib/cleanarr/cleanarr.db"); backup=sqlite3.connect("/var/lib/cleanarr/cleanarr.pre-upgrade.db"); source.backup(backup); print(backup.execute("PRAGMA integrity_check").fetchone()[0]); backup.close(); source.close()'
sudo systemctl start cleanarr
```

The integrity check must print `ok`. Store the verified backup outside the
server before an operating-system migration.

## Upgrade and rollback

Install the new package over the old one. The environment file and application data are retained.

```bash
sudo apt install ./cleanarr_<new-version>_amd64.deb
# or
sudo dnf install ./cleanarr_<new-version>_amd64.rpm

sudo systemctl restart cleanarr
```

The current SQLite schema is v5 and the persisted runtime configuration schema
is v3. Migrations are forward-only; SQLite v3/v4 add durable deletion
idempotency and batch state, while v5 adds Downloads observations, actions, and
policy evaluations. Create a verified pre-upgrade backup before upgrading.
Start an older build only after restoring the matching pre-upgrade backup. For
a complete rollback, stop CleanArr, restore the verified backup, install the
previous package, and start the service:

```bash
sudo systemctl stop cleanarr
sudo cp -a /var/lib/cleanarr/cleanarr.db /var/lib/cleanarr/cleanarr.failed-upgrade.db
sudo cp -a /var/lib/cleanarr/cleanarr.pre-upgrade.db /var/lib/cleanarr/cleanarr.db
sudo chown cleanarr:cleanarr /var/lib/cleanarr/cleanarr.db
sudo apt install ./cleanarr_<previous-version>_amd64.deb
# or: sudo dnf downgrade ./cleanarr_<previous-version>_amd64.rpm
sudo systemctl start cleanarr
sudo -u cleanarr /usr/bin/python3.12 -c 'import sqlite3; db=sqlite3.connect("/var/lib/cleanarr/cleanarr.db"); print(db.execute("PRAGMA integrity_check").fetchone()[0]); db.close()'
```

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
