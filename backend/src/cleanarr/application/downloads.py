"""Downloads use cases: bounded refresh, reversible actions and policy evaluation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid5

from cleanarr.application.download_policy import evaluate_seeding_stop_policy
from cleanarr.application.ports import DownloaderFleetPort, DownloadsRepositoryPort
from cleanarr.domain.config import GeneralConfig
from cleanarr.domain.downloads import (
    DownloadActionClaim,
    DownloadActionStatus,
    DownloadControlAction,
    DownloadControlOutcome,
    DownloaderControlResult,
    DownloaderListing,
    ListingFreshness,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)

_HASH = re.compile(r"^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")
_SAFE_ACTION_CODES = {
    "pre_read_failed",
    "pre_read_incomplete",
    "pre_state_unknown",
    "target_not_fresh",
    "not_found",
    "invalid_identifier",
    "unsupported",
    "unsupported_client_version",
    "not_configured",
    "unknown_client",
    "mutation_or_post_read_failed",
    "client_control_failed",
    "post_read_incomplete",
    "post_state_unverified",
    "already_in_desired_state",
    "applied",
    "unknown",
}


def resolve_snapshot_ownership(
    snapshots: tuple[TorrentSnapshot, ...],
    *,
    arr_history_hashes: set[str] | None,
    arr_source_failed: bool = False,
    downloader_complete: bool = True,
) -> tuple[TorrentSnapshot, ...]:
    """Attach ownership only from complete exact Arr history evidence.

    The caller must provide a complete, independently fetched set of Arr
    ``downloadId`` values.  No name, path, category, tracker, or watch signal
    participates in this decision.
    """

    by_hash: dict[str, int] = {}
    for item in snapshots:
        normalized_hash = item.info_hash.upper()
        by_hash[normalized_hash] = by_hash.get(normalized_hash, 0) + 1
    if arr_source_failed or arr_history_hashes is None:
        return tuple(
            replace(
                item,
                ownership=(
                    TorrentOwnership.CONFLICT if by_hash[item.info_hash.upper()] > 1 else TorrentOwnership.UNKNOWN
                ),
            )
            for item in snapshots
        )
    normalized = {value.upper() for value in arr_history_hashes if _HASH.fullmatch(value)}
    result = []
    for item in snapshots:
        normalized_hash = item.info_hash.upper()
        if by_hash[normalized_hash] > 1:
            ownership = TorrentOwnership.CONFLICT
        elif normalized_hash in normalized and not downloader_complete:
            ownership = TorrentOwnership.UNKNOWN
        elif normalized_hash in normalized:
            ownership = TorrentOwnership.MANAGED
        else:
            ownership = TorrentOwnership.UNMANAGED
        result.append(replace(item, info_hash=normalized_hash, ownership=ownership))
    return tuple(result)


class DownloadRequestError(ValueError):
    pass


class NullDownloaderFleet:
    """Typed no-configuration fleet; it cannot perform an external mutation."""

    def configured_client_ids(self) -> set[str]:
        return set()

    async def list_torrents(self) -> DownloaderListing:
        return DownloaderListing()

    async def control_torrent(
        self, client_id: str, info_hash: str, *, action: DownloadControlAction
    ) -> DownloaderControlResult:
        return DownloaderControlResult(
            client_id=client_id,
            client_name="not configured",
            client_kind="none",
            info_hash=info_hash,
            action=action,
            outcome=DownloadControlOutcome.UNKNOWN,
            code="not_configured",
        )


async def collect_arr_history_evidence(
    *,
    radarr: Any,
    radarr_configured: bool,
    sonarr: Any,
    sonarr_configured: bool,
) -> tuple[set[str] | None, bool]:
    """Collect bounded exact Arr download IDs for ownership proof."""

    if not radarr_configured and not sonarr_configured:
        return set(), False
    hashes: set[str] = set()
    failed = False
    for client, configured, catalog_method, history_method in (
        (radarr, radarr_configured, "list_movies", "list_movie_history"),
        (sonarr, sonarr_configured, "list_series", "list_series_history"),
    ):
        if not configured or client is None:
            continue
        try:
            catalog = list(await asyncio.wait_for(getattr(client, catalog_method)(), timeout=15))
            if len(catalog) > 100:
                failed = True
                continue
            histories = await asyncio.wait_for(_read_history_batch(client, catalog, history_method), timeout=30)
        except Exception:
            failed = True
            continue
        for records in histories:
            for record in records:
                event_type = str(getattr(record, "event_type", "")).casefold()
                if "grab" not in event_type and "import" not in event_type:
                    continue
                value = getattr(record, "download_id", None)
                if isinstance(value, str):
                    hashes.add(value)
    return hashes, failed


async def _read_history_batch(client: Any, catalog: list[Any], method_name: str) -> list[list[Any]]:
    semaphore = asyncio.Semaphore(4)

    async def one(
        item: Any,
        *,
        client: Any = client,
        method_name: str = method_name,
        semaphore: asyncio.Semaphore = semaphore,
    ) -> list[Any]:
        async with semaphore:
            return list(await getattr(client, method_name)(int(item.id)))

    return list(await asyncio.gather(*(one(item) for item in catalog)))


@dataclass(frozen=True)
class RefreshResult:
    snapshots: tuple[TorrentSnapshot, ...]
    failures: tuple[str, ...]
    complete: bool
    failure_details: tuple[tuple[str, str], ...] = ()


class DownloadsService:
    def __init__(
        self,
        *,
        repository: DownloadsRepositoryPort,
        downloader: DownloaderFleetPort,
        execution_lock: asyncio.Lock,
    ) -> None:
        self.repository = repository
        self.downloader = downloader
        self.execution_lock = execution_lock
        self._last_refresh = RefreshResult(tuple(), tuple(), False)

    def set_downloader(self, downloader: DownloaderFleetPort) -> None:
        """Replace the adapter graph after a runtime configuration reload."""

        self.downloader = downloader

    async def refresh(
        self,
        *,
        config: GeneralConfig,
        arr_history_hashes: set[str] | None = None,
        arr_source_failed: bool = False,
    ) -> RefreshResult:
        try:
            listing: DownloaderListing = await asyncio.wait_for(self.downloader.list_torrents(), timeout=30)
        except TimeoutError:
            self.repository.mark_all_stale("refresh_timeout")
            self._last_refresh = RefreshResult(tuple(self.repository.list_snapshots()), ("refresh_timeout",), False)
            return self._last_refresh
        except Exception:
            self.repository.mark_all_stale("refresh_failed")
            self._last_refresh = RefreshResult(tuple(self.repository.list_snapshots()), ("refresh_failed",), False)
            return self._last_refresh
        snapshots = tuple(replace(item, info_hash=item.info_hash.upper()) for item in listing.torrents)
        failed = {failure.client_id for failure in listing.failures}
        configured = self.downloader.configured_client_ids()
        configured |= {snapshot.client_id for snapshot in listing.torrents} | failed
        successful = configured - failed
        completed = set(listing.completed_client_ids)
        downloader_complete = not failed and successful == configured and (not completed or completed == configured)
        if arr_history_hashes is not None or arr_source_failed:
            snapshots = resolve_snapshot_ownership(
                snapshots,
                arr_history_hashes=arr_history_hashes,
                arr_source_failed=arr_source_failed,
                downloader_complete=downloader_complete,
            )
        self.repository.save_listing(snapshots, successful)
        self._last_refresh = RefreshResult(
            snapshots,
            tuple(sorted({failure.code for failure in listing.failures})),
            not failed,
            tuple(sorted({(failure.client_id, failure.code) for failure in listing.failures})),
        )
        return self._last_refresh

    def snapshots(self) -> list[TorrentSnapshot]:
        return self.repository.list_snapshots()

    @property
    def last_refresh(self) -> RefreshResult:
        return self._last_refresh

    async def control(
        self,
        *,
        client_id: str,
        info_hash: str,
        action: DownloadControlAction,
        idempotency_key: str,
        max_attempts: int = 1,
        dry_run: bool = False,
        allow_retry: bool = False,
        source: str = "manual",
    ) -> tuple[str, DownloadActionStatus, str | None]:
        max_attempts = max(1, min(max_attempts, 5))
        if not client_id or not _HASH.fullmatch(info_hash):
            raise DownloadRequestError("invalid_target")
        try:
            UUID(idempotency_key)
        except ValueError as exc:
            raise DownloadRequestError("invalid_idempotency_key") from exc
        normalized_hash = info_hash.upper()
        canonical = json.dumps(
            {
                "action": action.value,
                "client_id": client_id,
                "info_hash": normalized_hash,
                "execution_mode": "dry_run" if dry_run else "live",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        claim: DownloadActionClaim = self.repository.claim_action(
            idempotency_key=idempotency_key,
            canonical_request=canonical,
            client_id=client_id,
            info_hash=normalized_hash,
            action=action,
            max_attempts=max_attempts,
            allow_retry=allow_retry,
            source=source,
        )
        if claim.conflict:
            raise DownloadRequestError("idempotency_conflict")
        if claim.status is not DownloadActionStatus.QUEUED:
            return claim.action_id, claim.status, claim.code
        async with self.execution_lock:
            current_record = self.repository.action_record(claim.action_id)
            if current_record is None:
                return claim.action_id, DownloadActionStatus.FAILED, "action_not_found"
            if current_record.status is not DownloadActionStatus.QUEUED:
                return claim.action_id, current_record.status, current_record.code
            # Count every policy/manual execution attempt, including a
            # definite pre-mutation block such as a stale target.  Otherwise
            # policy retries could observe attempt_count=0 forever and evade
            # their configured bound.
            self.repository.increment_attempt(claim.action_id)
            current = self.repository.get_snapshot(client_id, normalized_hash)
            if current is None or current.freshness is not ListingFreshness.FRESH:
                self.repository.update_action(
                    claim.action_id,
                    DownloadActionStatus.FAILED,
                    code="target_not_fresh",
                    result={"outcome": "blocked", "code": "target_not_fresh"},
                )
                return claim.action_id, DownloadActionStatus.FAILED, "target_not_fresh"
            desired_states = (
                {TorrentState.STOPPED}
                if action is DownloadControlAction.PAUSE
                else {TorrentState.DOWNLOADING, TorrentState.SEEDING, TorrentState.QUEUED, TorrentState.CHECKING}
            )
            if current.state in desired_states:
                self.repository.update_action(
                    claim.action_id,
                    DownloadActionStatus.ALREADY_IN_STATE,
                    code="already_in_desired_state",
                    result={
                        "outcome": "already_in_desired_state",
                        "code": "already_in_desired_state",
                        "before_state": current.state.value,
                        "after_state": current.state.value,
                    },
                )
                return claim.action_id, DownloadActionStatus.ALREADY_IN_STATE, "already_in_desired_state"
            self.repository.update_action(claim.action_id, DownloadActionStatus.RUNNING, code="running")
            if dry_run:
                self.repository.update_action(
                    claim.action_id,
                    DownloadActionStatus.SIMULATED,
                    code="dry_run",
                    result={
                        "outcome": "simulated",
                        "code": "dry_run",
                        "before_state": current.state.value,
                    },
                )
                return claim.action_id, DownloadActionStatus.SIMULATED, "dry_run"
            try:
                result = await self.downloader.control_torrent(client_id, normalized_hash, action=action)
            except Exception:
                self.repository.update_action(
                    claim.action_id,
                    DownloadActionStatus.UNCERTAIN,
                    code="mutation_or_post_read_failed",
                    result={"outcome": "unknown", "code": "mutation_or_post_read_failed"},
                )
                return claim.action_id, DownloadActionStatus.UNCERTAIN, "mutation_or_post_read_failed"
            code = getattr(result, "code", None)
            if code is not None and (not isinstance(code, str) or code not in _SAFE_ACTION_CODES):
                code = "unknown"
            outcome = getattr(getattr(result, "outcome", None), "value", str(getattr(result, "outcome", "")))
            if code in {"mutation_or_post_read_failed", "client_control_failed"}:
                status = DownloadActionStatus.UNCERTAIN
            elif code in {"post_read_incomplete", "post_state_unverified"}:
                status = DownloadActionStatus.RECONCILE_REQUIRED
            elif outcome == "already_in_desired_state":
                status = DownloadActionStatus.ALREADY_IN_STATE
            elif outcome == "applied":
                status = DownloadActionStatus.SUCCEEDED
            else:
                status = DownloadActionStatus.FAILED
            before_snapshot = getattr(result, "before", None)
            after_snapshot = getattr(result, "after", None)
            result_summary: dict[str, object] = {
                "outcome": outcome or "unknown",
                "code": code,
                "before_state": before_snapshot.state.value if isinstance(before_snapshot, TorrentSnapshot) else None,
                "after_state": after_snapshot.state.value if isinstance(after_snapshot, TorrentSnapshot) else None,
            }
            self.repository.update_action(claim.action_id, status, code=code, result=result_summary)
            return claim.action_id, status, code

    async def evaluate_and_apply_policy(self, *, config: GeneralConfig) -> None:
        revision, evaluations = self.evaluate_policy(config=config)
        if not config.seeding_stop_policy.enabled:
            return
        for evaluation in evaluations:
            if evaluation["decision"] != "eligible":
                continue
            client_id = str(evaluation["client_id"])
            info_hash = str(evaluation["info_hash"])
            snapshot = self.repository.get_snapshot(client_id, info_hash)
            if snapshot is None:
                continue
            execution_mode = "dry_run" if config.dry_run else "live"
            key = str(
                uuid5(
                    UUID("00000000-0000-0000-0000-000000000001"),
                    f"{revision}:{execution_mode}:{client_id}:{info_hash}",
                )
            )
            await self.control(
                client_id=client_id,
                info_hash=info_hash,
                action=DownloadControlAction.PAUSE,
                idempotency_key=key,
                max_attempts=config.seeding_stop_policy.max_attempts,
                dry_run=config.dry_run,
                allow_retry=True,
                source="policy",
            )

    def evaluate_policy(self, *, config: GeneralConfig) -> tuple[str, list[dict[str, object]]]:
        policy = config.seeding_stop_policy
        revision = hashlib.sha256(policy.model_dump_json().encode()).hexdigest()[:32]
        evaluations: list[dict[str, object]] = []
        for snapshot in self.snapshots():
            evaluation = evaluate_seeding_stop_policy(policy, snapshot)
            self.repository.record_policy_evaluation(
                revision=revision,
                snapshot=snapshot,
                facts=evaluation.facts,
                reason_code=evaluation.reason_code,
                decision=evaluation.decision.value,
            )
            evaluations.append(
                {
                    "client_id": snapshot.client_id,
                    "info_hash": snapshot.info_hash,
                    "decision": evaluation.decision.value,
                    "reason_code": evaluation.reason_code,
                }
            )
        return revision, evaluations


def encode_cursor(filters: dict[str, str | None], last: tuple[str, str]) -> str:
    payload = {"filters": filters, "last": list(last)}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, filters: dict[str, str | None]) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("filters") != filters or not isinstance(payload.get("last"), list):
            raise ValueError
        client_id, info_hash = payload["last"]
        if not isinstance(client_id, str) or not isinstance(info_hash, str):
            raise ValueError
        return client_id, info_hash
    except Exception as exc:
        raise DownloadRequestError("invalid_cursor") from exc
