# Torrent clients

[English](TORRENT_CLIENTS.md) · [Русский](TORRENT_CLIENTS_RU.md)

CleanArr can route a proven Arr download hash to every enabled torrent-client
profile. A missing hash is treated as an idempotent success; an error from one
client is recorded without hiding successful removals from other clients.

## Supported adapters

| Client | API | Authentication | Default URL path |
| --- | --- | --- | --- |
| qBittorrent | Web API v2 | username/password cookie, or Bearer API key on qBittorrent 5.2+ | base Web UI URL; `/api/v2` is removed |
| Transmission | legacy RPC and JSON-RPC 2.0 with automatic negotiation | optional HTTP Basic authentication | `/transmission/rpc` |
| Deluge | Web JSON-RPC | Deluge Web password; the Web UI must be connected to a daemon | `/json` |
| rTorrent | HTTP XML-RPC | optional HTTP Basic authentication, normally supplied by the reverse proxy | `/RPC2` |

The configured path is preserved. The default path is added only when the URL
has no path, so reverse-proxy layouts remain usable.

## Removal behavior

Every adapter supports removing only the torrent entry or removing the entry
and its local data. CleanArr first checks ownership by normalized info hash and
does not turn a missing/already removed torrent into a failure.

When several torrent clients are enabled, CleanArr checks all of them. This is
intentional for installations that split downloads across instances or have
the same hash in more than one client. Partial authentication, timeout, and RPC
failures remain visible as per-client actions.

### Seeding policy

Each torrent-client profile has an independent removal policy:

- **Remove immediately** keeps the historical CleanArr behavior.
- **Keep torrent** records a skipped action and never removes a matching entry.
- **Defer until seeded** checks an optional minimum ratio and/or minimum seed
  time. If both thresholds are configured, both must be reached before removal.

The policy is evaluated on every cleanup attempt. An unmet threshold safely
skips that attempt; persistent manual jobs can be retried after the threshold
is met. qBittorrent, Transmission, and Deluge use the clients'
reported ratio and seeding-time values. rTorrent reports ratio in thousandths;
CleanArr normalizes it and derives elapsed time from `d.timestamp.finished`.
Dry-run performs the same ownership and policy lookup but never calls a removal
operation, so its action log reflects keep/defer decisions accurately.

## Downloads controls and seeding stop

The Downloads read model normalizes observations from every enabled client. A
field that a client did not provide remains nullable/unknown; it is never
presented as zero or a successful read. Listings are bounded and cursor-based,
and a partial source result remains explicitly partial.

Downloads exposes only reversible **pause** and **resume** controls, never entry
or data deletion. A manual control needs a fresh managed observation and a
client-generated idempotency key. Only `succeeded`, `already_in_state`, and
dry-run `simulated` are completion states. `failed`, `uncertain`, and
`reconcile_required` require operator review; retry an ambiguous request with
the exact same action and idempotency key.

The global automatic seeding-stop policy is separate from the per-profile
removal policy above and is disabled by default. It pauses only when fresh,
managed, seeding evidence satisfies configured ratio and/or time thresholds.
The mode is explicit (`all` or `any`), category/tag include/exclude scope is
fail-closed, and missing required metrics block the action. The policy never
removes a torrent entry or local data.

## rTorrent data deletion safety

rTorrent's `d.erase` removes the torrent entry but deliberately leaves its data
untouched. For the remove-with-data mode, CleanArr obtains the torrent data path
through XML-RPC, rejects empty, relative, parent-traversal, or root-level paths,
stops and closes the torrent, invokes `execute.throw` with `/bin/rm -rf --` as
separate arguments, and then calls `d.erase`.

This mode therefore requires the rTorrent XML-RPC endpoint to expose
`execute.throw` and the rTorrent process to have permission to remove its data.
Use a dedicated RPC endpoint with authentication and a restricted filesystem
account. If the path check or command fails, CleanArr does not erase the torrent
entry and records a failed action.

## Compatibility status

The adapters have automated protocol contract tests, including Transmission
generation negotiation, qBittorrent v1/v2 hybrid identifiers, authentication
failures, absent hashes, both removal modes, seeding thresholds, partial
multi-client failure, and rTorrent unsafe-path rejection. The release gate also
runs the adapters against digest-pinned real services. See the exact certified
versions, evidence boundary, and 1.x support policy in the public
[compatibility matrix](COMPATIBILITY.md).
