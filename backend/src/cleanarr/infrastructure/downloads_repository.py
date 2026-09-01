"""SQLite persistence for normalized downloads and reversible action claims."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cleanarr.domain.downloads import (
    DownloadActionClaim,
    DownloadActionStatus,
    DownloadControlAction,
    ListingFreshness,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.infrastructure.database import migrate_database

RETRYABLE_BEFORE_MUTATION_CODES = frozenset(
    {
        "pre_read_failed",
        "pre_read_incomplete",
        "pre_state_unknown",
        "target_not_fresh",
        "not_found",
        "invalid_identifier",
        "unsupported",
    }
)
_SAFE_ACTION_CODES = RETRYABLE_BEFORE_MUTATION_CODES | {
    "queued",
    "running",
    "dry_run",
    "already_in_desired_state",
    "applied",
    "mutation_or_post_read_failed",
    "client_control_failed",
    "post_read_incomplete",
    "post_state_unverified",
    "restart_recovery",
    "not_configured",
    "unknown_client",
    "unknown",
    "unsupported_client_version",
}


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


def snapshot_to_json(snapshot: TorrentSnapshot) -> str:
    return json.dumps(
        {
            "client_id": snapshot.client_id,
            "client_name": snapshot.client_name,
            "client_kind": snapshot.client_kind,
            "info_hash": snapshot.info_hash,
            "display_name": snapshot.display_name,
            "state": snapshot.state.value,
            "observed_at": snapshot.observed_at.isoformat(),
            "progress": snapshot.progress,
            "total_bytes": snapshot.total_bytes,
            "downloaded_bytes": snapshot.downloaded_bytes,
            "uploaded_bytes": snapshot.uploaded_bytes,
            "ratio": snapshot.ratio,
            "seeding_time_seconds": snapshot.seeding_time_seconds,
            "download_speed_bytes_per_second": snapshot.download_speed_bytes_per_second,
            "upload_speed_bytes_per_second": snapshot.upload_speed_bytes_per_second,
            "eta_seconds": snapshot.eta_seconds,
            "added_at": _dt(snapshot.added_at),
            "completed_at": _dt(snapshot.completed_at),
            "activity_at": _dt(snapshot.activity_at),
            "category": snapshot.category,
            "tags": list(snapshot.tags) if snapshot.tags is not None else None,
            "tracker_summary": snapshot.tracker_summary,
            "freshness": snapshot.freshness.value,
            "ownership": snapshot.ownership.value,
            "unavailable_reason": snapshot.unavailable_reason,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def snapshot_from_json(payload: str) -> TorrentSnapshot:
    value: dict[str, Any] = json.loads(payload)
    return TorrentSnapshot(
        client_id=str(value["client_id"]),
        client_name=str(value["client_name"]),
        client_kind=str(value["client_kind"]),
        info_hash=str(value["info_hash"]),
        display_name=value.get("display_name"),
        state=TorrentState(value.get("state", TorrentState.UNKNOWN)),
        observed_at=_parse_dt(value.get("observed_at")) or datetime.now(UTC),
        progress=value.get("progress"),
        total_bytes=value.get("total_bytes"),
        downloaded_bytes=value.get("downloaded_bytes"),
        uploaded_bytes=value.get("uploaded_bytes"),
        ratio=value.get("ratio"),
        seeding_time_seconds=value.get("seeding_time_seconds"),
        download_speed_bytes_per_second=value.get("download_speed_bytes_per_second"),
        upload_speed_bytes_per_second=value.get("upload_speed_bytes_per_second"),
        eta_seconds=value.get("eta_seconds"),
        added_at=_parse_dt(value.get("added_at")),
        completed_at=_parse_dt(value.get("completed_at")),
        activity_at=_parse_dt(value.get("activity_at")),
        category=value.get("category"),
        tags=tuple(value["tags"]) if value.get("tags") is not None else None,
        tracker_summary=value.get("tracker_summary"),
        freshness=ListingFreshness(value.get("freshness", ListingFreshness.UNKNOWN)),
        ownership=TorrentOwnership(value.get("ownership", TorrentOwnership.UNKNOWN)),
        unavailable_reason=value.get("unavailable_reason"),
    )


class DownloadsRepository:
    """Thread-safe, short-lived SQLite operations; no external payloads are stored."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        migrate_database(db_path)

    def save_listing(self, snapshots: tuple[TorrentSnapshot, ...], successful_clients: set[str]) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            # Every prior observation is stale until this complete cycle
            # explicitly refreshes it. Failed/removed clients therefore can
            # never remain eligible for an automatic action.
            rows = db.execute("SELECT client_id, info_hash, snapshot_json FROM download_observations").fetchall()
            for client_id, info_hash, payload in rows:
                old = snapshot_from_json(payload)
                db.execute(
                    "UPDATE download_observations SET snapshot_json=?, freshness=? WHERE client_id=? AND info_hash=?",
                    (
                        snapshot_to_json(
                            replace(
                                old,
                                freshness=ListingFreshness.STALE,
                                unavailable_reason=old.unavailable_reason or "refresh_not_confirmed",
                            )
                        ),
                        ListingFreshness.STALE.value,
                        client_id,
                        info_hash,
                    ),
                )
            for snapshot in snapshots:
                db.execute(
                    "INSERT INTO download_observations(client_id, info_hash, snapshot_json, observed_at, freshness) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(client_id, info_hash) DO UPDATE SET "
                    "snapshot_json=excluded.snapshot_json, observed_at=excluded.observed_at, "
                    "freshness=excluded.freshness",
                    (
                        snapshot.client_id,
                        snapshot.info_hash,
                        snapshot_to_json(snapshot),
                        snapshot.observed_at.isoformat(),
                        snapshot.freshness.value,
                    ),
                )
            for client_id in successful_clients:
                present = {item.info_hash for item in snapshots if item.client_id == client_id}
                rows = db.execute(
                    "SELECT info_hash, snapshot_json FROM download_observations WHERE client_id = ?", (client_id,)
                ).fetchall()
                for info_hash, payload in rows:
                    if info_hash not in present:
                        old = snapshot_from_json(payload)
                        db.execute(
                            "UPDATE download_observations SET snapshot_json=?, freshness=? "
                            "WHERE client_id=? AND info_hash=?",
                            (
                                snapshot_to_json(replace(old, freshness=ListingFreshness.STALE)),
                                ListingFreshness.STALE.value,
                                client_id,
                                info_hash,
                            ),
                        )
            db.commit()

    def mark_all_stale(self, reason: str = "refresh_not_confirmed") -> None:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT client_id, info_hash, snapshot_json FROM download_observations").fetchall()
            for client_id, info_hash, payload in rows:
                old = snapshot_from_json(payload)
                db.execute(
                    "UPDATE download_observations SET snapshot_json=?, freshness=? WHERE client_id=? AND info_hash=?",
                    (
                        snapshot_to_json(replace(old, freshness=ListingFreshness.STALE, unavailable_reason=reason)),
                        ListingFreshness.STALE.value,
                        client_id,
                        info_hash,
                    ),
                )
            db.commit()

    def list_snapshots(self) -> list[TorrentSnapshot]:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(
                "SELECT snapshot_json FROM download_observations ORDER BY client_id, info_hash"
            ).fetchall()
        return [snapshot_from_json(str(row[0])) for row in rows]

    def get_snapshot(self, client_id: str, info_hash: str) -> TorrentSnapshot | None:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT snapshot_json FROM download_observations WHERE client_id=? AND info_hash=?",
                (client_id, info_hash),
            ).fetchone()
        return snapshot_from_json(row[0]) if row else None

    def claim_action(
        self,
        *,
        idempotency_key: str,
        canonical_request: str,
        client_id: str,
        info_hash: str,
        action: DownloadControlAction,
        max_attempts: int,
        allow_retry: bool = False,
        source: str = "manual",
    ) -> DownloadActionClaim:
        now = datetime.now(UTC).isoformat()
        action_id = uuid4().hex
        with sqlite3.connect(self.db_path) as db:
            try:
                db.execute(
                    "INSERT INTO download_actions("
                    "id,idempotency_key,canonical_request_json,client_id,info_hash,action,status,code,"
                    "source,created_at,updated_at,max_attempts) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        action_id,
                        idempotency_key,
                        canonical_request,
                        client_id,
                        info_hash,
                        action.value,
                        DownloadActionStatus.QUEUED.value,
                        "queued",
                        source if source in {"manual", "policy"} else "manual",
                        now,
                        now,
                        max_attempts,
                    ),
                )
                db.commit()
                # The queued state is itself a persisted, machine-readable
                # outcome.  Returning it here keeps concurrent duplicate
                # callers consistent with the row they just claimed.
                return DownloadActionClaim(action_id, DownloadActionStatus.QUEUED, code="queued")
            except sqlite3.IntegrityError:
                row = db.execute(
                    "SELECT id, status, canonical_request_json, code, attempt_count, max_attempts "
                    "FROM download_actions WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if row is None:
                    raise
                if str(row[2]) != canonical_request:
                    return DownloadActionClaim(str(row[0]), DownloadActionStatus(str(row[1])), conflict=True)
                existing_status = DownloadActionStatus(str(row[1]))
                existing_code = str(row[3]) if row[3] is not None else None
                retryable = (
                    existing_status is DownloadActionStatus.FAILED and existing_code in RETRYABLE_BEFORE_MUTATION_CODES
                )
                if allow_retry and retryable and int(row[4]) < min(max_attempts, int(row[5])):
                    db.execute(
                        "UPDATE download_actions SET status=?, updated_at=?, max_attempts=? WHERE id=?",
                        (DownloadActionStatus.QUEUED.value, now, max_attempts, str(row[0])),
                    )
                    db.commit()
                    return DownloadActionClaim(str(row[0]), DownloadActionStatus.QUEUED, code="queued")
                return DownloadActionClaim(str(row[0]), existing_status, code=existing_code)

    def update_action(
        self, action_id: str, status: DownloadActionStatus, *, code: str | None = None, result: object = None
    ) -> None:
        code = code if code in _SAFE_ACTION_CODES else ("unknown" if code is not None else None)
        if isinstance(result, dict) and code is not None:
            result = {**result, "code": result.get("code", code)}
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE download_actions SET status=?, code=?, result_json=?, updated_at=? WHERE id=?",
                (
                    status.value,
                    code,
                    _safe_result_summary(result),
                    datetime.now(UTC).isoformat(),
                    action_id,
                ),
            )
            db.commit()

    def action_status(self, action_id: str) -> DownloadActionStatus | None:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("SELECT status FROM download_actions WHERE id=?", (action_id,)).fetchone()
        return DownloadActionStatus(str(row[0])) if row else None

    def action_record(self, action_id: str) -> DownloadActionClaim | None:
        """Return the durable status and machine-readable code for a claim."""

        with sqlite3.connect(self.db_path) as db:
            row = db.execute("SELECT status, code FROM download_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            return None
        return DownloadActionClaim(
            action_id=action_id,
            status=DownloadActionStatus(str(row[0])),
            code=str(row[1]) if row[1] is not None else None,
        )

    def latest_action_projections(self, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, object]]:
        """Return one safe, bounded audit projection per observed torrent."""

        if not keys:
            return {}
        if len(keys) > 50:
            raise ValueError("At most 50 action projections may be requested.")
        ordered_keys = sorted(keys)
        predicate = " OR ".join("(client_id=? AND info_hash=?)" for _ in ordered_keys)
        parameters = tuple(value for key in ordered_keys for value in key)
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(
                "SELECT id, client_id, info_hash, source, status, code, attempt_count, max_attempts, "
                "created_at, updated_at, result_json FROM download_actions "
                f"WHERE {predicate} ORDER BY updated_at DESC, id DESC",
                parameters,
            ).fetchall()
        projections: dict[tuple[str, str], dict[str, object]] = {}
        for (
            action_id,
            client_id,
            info_hash,
            source,
            status,
            code,
            attempt_count,
            max_attempts,
            created_at,
            updated_at,
            result_json,
        ) in rows:
            key = (str(client_id), str(info_hash))
            if key in projections:
                continue
            projections[key] = {
                "action_id": str(action_id),
                "source": str(source) if str(source) in {"manual", "policy"} else "manual",
                "status": str(status),
                "code": str(code) if code in _SAFE_ACTION_CODES else ("unknown" if code is not None else None),
                "attempt_count": int(attempt_count),
                "max_attempts": int(max_attempts),
                "created_at": str(created_at),
                "updated_at": str(updated_at),
                "result": _parse_result_summary(result_json),
            }
        return projections

    def increment_attempt(self, action_id: str) -> int:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "UPDATE download_actions SET attempt_count=attempt_count+1, updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), action_id),
            )
            row = db.execute("SELECT attempt_count FROM download_actions WHERE id=?", (action_id,)).fetchone()
            db.commit()

        return int(row[0]) if row else 0

    def recover_running_actions(self) -> int:
        with sqlite3.connect(self.db_path) as db:
            result = db.execute(
                "UPDATE download_actions SET status=?, code=?, updated_at=? WHERE status=?",
                (
                    DownloadActionStatus.RECONCILE_REQUIRED.value,
                    "restart_recovery",
                    datetime.now(UTC).isoformat(),
                    DownloadActionStatus.RUNNING.value,
                ),
            )
            db.commit()
            return result.rowcount

    def action_status_counts(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT status, COUNT(*) FROM download_actions GROUP BY status").fetchall()
        allowed = {status.value for status in DownloadActionStatus}
        return {str(status): int(count) for status, count in rows if str(status) in allowed}

    def policy_decision_counts(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT decision, COUNT(*) FROM policy_evaluations GROUP BY decision").fetchall()
        return {
            str(decision): int(count)
            for decision, count in rows
            if str(decision) in {"eligible", "blocked", "excluded"}
        }

    def latest_policy_evaluations(self) -> dict[tuple[str, str], dict[str, object]]:
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(
                "SELECT client_id, info_hash, reason_code, decision, facts_json "
                "FROM policy_evaluations ORDER BY evaluated_at ASC, id ASC"
            ).fetchall()
        return {
            (str(client_id), str(info_hash)): {
                "reason_code": str(reason_code),
                "decision": str(decision),
                "facts": json.loads(facts_json),
            }
            for client_id, info_hash, reason_code, decision, facts_json in rows
        }

    def record_policy_evaluation(
        self, *, revision: str, snapshot: TorrentSnapshot, facts: dict[str, object], reason_code: str, decision: str
    ) -> None:
        safe_facts = json.dumps(_safe_policy_facts(facts), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO policy_evaluations("
                "policy_revision,client_id,info_hash,observation_key,facts_json,reason_code,decision,evaluated_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(policy_revision, observation_key) DO UPDATE SET "
                "client_id=excluded.client_id, info_hash=excluded.info_hash, facts_json=excluded.facts_json, "
                "reason_code=excluded.reason_code, decision=excluded.decision, evaluated_at=excluded.evaluated_at",
                (
                    revision,
                    snapshot.client_id,
                    snapshot.info_hash,
                    snapshot.observation_key,
                    safe_facts,
                    reason_code,
                    decision,
                    datetime.now(UTC).isoformat(),
                ),
            )
            db.execute(
                "DELETE FROM policy_evaluations WHERE id NOT IN "
                "(SELECT id FROM policy_evaluations ORDER BY evaluated_at DESC LIMIT 5000)"
            )
            db.commit()


def _safe_result_summary(result: object) -> str | None:
    """Serialize only bounded result fields, never adapter payloads."""

    if not isinstance(result, dict):
        return None
    safe: dict[str, str | None] = {}
    for field in ("outcome", "code", "before_state", "after_state"):
        value = result.get(field)
        if value is None:
            safe[field] = None
        elif isinstance(value, str) and len(value) <= 64:
            safe[field] = "unknown" if field == "code" and value not in _SAFE_ACTION_CODES else value
    return json.dumps(safe, sort_keys=True, separators=(",", ":"))


def _parse_result_summary(value: str | None) -> dict[str, str | None] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    sanitized = _safe_result_summary(parsed)
    if sanitized is None:
        return None
    return cast(dict[str, str | None], json.loads(sanitized))


def _safe_policy_facts(facts: dict[str, object]) -> dict[str, object]:
    allowed = {
        "ratio",
        "seeding_minutes",
        "state",
        "freshness",
        "ownership",
        "ratio_passed",
        "seeding_minutes_passed",
    }
    return {
        key: value
        for key, value in facts.items()
        if key in allowed and (value is None or isinstance(value, (bool, int, float, str)))
    }
