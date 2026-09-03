# Compatibility matrix

[English](COMPATIBILITY.md) · [Русский](COMPATIBILITY_RU.md)

This is the public compatibility contract for CleanArr 0.9 release candidates
and the 1.x series. A service is supported only when the exact line below has
passed the automated real-service gate; a successful connection by itself is
not certification.

Last full local certification: **2026-08-12**. The release workflow repeats the
same digest-pinned gate from a clean GitHub-hosted runner before publishing any
tag.

## Certified dependency versions

| Dependency | Certified version | API contract | Reproducible fixture |
| --- | --- | --- | --- |
| qBittorrent | 5.2.3 | Web API v2; cookie login and version discovery | `lscr.io/linuxserver/qbittorrent:5.2.3_v2.0.14-ls471@sha256:6816d2b144b1eb97665f886e41e18a14d026ba78c9d0953fc68a1211ea819433` |
| Transmission, legacy generation | 4.0.6 | legacy RPC with session-ID negotiation and Basic auth | `lscr.io/linuxserver/transmission:4.0.6-r6-ls326@sha256:452310cb020c036d293e879698097acb6cc653db2676610bf8e3b58a3f4d2af5` |
| Transmission, modern generation | 4.1.3 | JSON-RPC 2.0 with session-ID negotiation and Basic auth | `lscr.io/linuxserver/transmission:4.1.3-r0-ls357@sha256:81787bc706d3833d252e6d8b94545fea46bf2156f616320991a395619a477d2c` |
| Deluge | 2.2.0 | authenticated Web JSON-RPC connected to a daemon | `lscr.io/linuxserver/deluge:2.2.0-ls381@sha256:33a939576f7ecfc1227db1a0cb2afce030ce983e620ec9d93c956e3700e21fe9` |
| rTorrent | 0.16.17 | authenticated HTTP XML-RPC | `crazymax/rtorrent-rutorrent:5.3.7-0.16.17@sha256:395f32ff75ab84a5615336829c4b846c154113129bc90b911c08a0f5261043f1` |
| Radarr | 6.3.0.10514 | API v3 | `lscr.io/linuxserver/radarr:version-6.3.0.10514@sha256:a45b5ab0f850f39edb4cc9c95bbd967b52ddc3d4574a4dfb45561177db6c88f4` |
| Sonarr | 4.0.19.2979 | API v3 | `lscr.io/linuxserver/sonarr:version-4.0.19.2979@sha256:373159ba768e23a3a1c497d9f2b936addf8fd5b1fdce7dd6a14080ac928bfda0` |
| Seerr | 3.4.1 | API v1 | `ghcr.io/seerr-team/seerr:v3.4.1@sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1` |
| Jellyfin | 10.11.11 | authenticated server API | `jellyfin/jellyfin:10.11.11@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db` |

The rTorrent fixture includes a ruTorrent web frontend, but only the rTorrent
XML-RPC engine is certified. ruTorrent and Flood are frontends, not separate
download engines. Other releases, including a newer upstream rTorrent release,
remain outside the support contract until their exact version is added here
with a green gate.

## What the gate proves

For every listed dependency the gate starts a fresh isolated service, verifies
the reported version and authenticated health contract, and proves that invalid
credentials fail closed. Each torrent-client test then:

- creates a real deterministic torrent through the native API;
- reads one normalized snapshot and verifies its state, size, progress, and
  freshness contract;
- pauses and resumes it through the native reversible command, verifies the
  resulting normalized state, and proves that repeating each command is
  idempotent;
- verifies a non-mutating dry-run lookup;
- removes the torrent entry without data;
- treats a second removal as an idempotent missing result;
- adds it again and exercises remove-with-data.

The ordinary required suite complements this live gate with BitTorrent v1/v2
and hybrid identifier matching, timeouts, seeding policy, retry/partial failure,
pack/shared-path/cross-seed rejection, all media item types, restart recovery,
duplicate-event handling, and simultaneous multi-instance routing. The live
Radarr, Sonarr, Jellyfin, and Seerr fixtures verify the exact authenticated API
versions and read contracts used by those scenario flows.

The candidate rehearsal covers both directions with real released containers:
`v0.2.11 -> candidate -> restored v0.2.11`,
`v0.9.0 -> candidate -> restored v0.9.0`,
`v1.0.0 -> candidate -> restored v1.0.0`, and the latest stable
`v1.1.0 -> candidate -> restored v1.1.0`. It checks the verified backup,
database/config schema migration, retained configuration, and retained activity
history. The v1.1.0 path additionally restores the automatic schema-v3 sidecar
created before the candidate writes configuration schema 4 or database schema 6.

Run the complete gate locally from a clean checkout:

```bash
backend/.venv/bin/python compatibility/run.py
docker build --provenance=false -f deploy/Dockerfile -t cleanarr:compatibility-candidate .
backend/.venv/bin/python compatibility/rehearse_upgrade.py cleanarr:compatibility-candidate
```

The services bind test ports only to `127.0.0.1`, use disposable volumes, and
are removed after the run. `CLEANARR_COMPAT_KEEP=1` may be used only for local
diagnosis; it intentionally retains the stack and prints its generated project
and runtime paths.

## 2.0 continuity boundary

CleanArr v1.1.0 certified normalized Downloads reads and idempotent pause/resume
mapping for all four torrent adapters. The v2.0 candidate carries those
contracts forward without adding destructive authority. It may claim continuity
only when this exact pinned profile, container/package smoke, the latest stable
v1.1.0-to-v6/config-v4 backup/restore rehearsal, and the populated v5-to-v6 and
config-v3-to-v4 migration tests pass from the release commit.

The profile does **not** by itself certify seeding-stop policy execution,
cleanup-candidate aggregation, first-run workflow, or batch APIs. A successful
connection test, HTTP response, or cached observation is never compatibility
evidence for those flows.

## 1.x and 2.x compatibility and deprecation policy

- The exact rows above are the tested support floor for 1.0. Patch releases of
  a dependency are not silently claimed compatible; CI must certify them first.
- CleanArr 2.0 carries forward the documented 1.x webhook,
  configuration-export, database, adapter, and fail-closed safety contracts.
  The major version identifies the new production UI and authenticated
  administrator/viewer boundary; it does not remove a Tier 1 integration or
  bypass an announced deprecation window.
- CleanArr 2.x keeps those documented contracts backward compatible. Additive
  fields and ordered migrations may ship in minor releases.
- A planned removal or incompatible behavior change is announced in both
  languages for at least one CleanArr minor release and 90 days before removal.
- A deprecated configuration key remains readable during that window and is
  migrated when a lossless migration exists.
- A critical security or data-loss issue may require faster removal. The release
  notes must identify the exception, the affected versions, and the safe
  migration or rollback path.
- Breaking API/configuration changes outside a security exception require a new
  CleanArr major version. A supported dependency version is never removed
  silently.
