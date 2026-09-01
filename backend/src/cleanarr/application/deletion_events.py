"""Webhook execution coordination and durable successful-result idempotency."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from cleanarr.application.deletion_models import ProcessingResultResponse
from cleanarr.application.deletion_persistence import DeletionRepositoryPort
from cleanarr.domain import MediaDeletionEvent, OverallStatus, ProcessingResult

EventProcessor = Callable[[MediaDeletionEvent], Awaitable[ProcessingResult]]


class WebhookInterruptedUnknownError(RuntimeError):
    """A prior delivery may have mutated downstream state before interruption.

    The marker is intentionally not reconciled or replayed automatically because
    this coordinator cannot prove which downstream mutation stage was reached.
    """

    code = "interrupted_unknown"

    def __init__(self) -> None:
        super().__init__("A prior webhook delivery may have reached downstream services; automatic replay is blocked.")


class DeletionExecutionCoordinator:
    """Serialize mutations and suppress completed duplicate webhook events."""

    def __init__(self, repository: DeletionRepositoryPort, *, retention: timedelta = timedelta(days=7)) -> None:
        self._repository = repository
        self._retention = retention
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize persistence and remove only expired completed webhook results."""

        await asyncio.to_thread(self._repository.initialize)
        await asyncio.to_thread(self._repository.purge_webhooks, completed_before=self._cutoff())

    async def process_webhook(
        self,
        event: MediaDeletionEvent,
        processor: EventProcessor,
    ) -> tuple[ProcessingResult, bool]:
        """Process once under the global safety lock, returning duplicate state."""

        event_key = event_key_for(event)
        async with self.lock:
            cached = await asyncio.to_thread(
                self._repository.load_completed_webhook,
                event_key,
                completed_after=self._cutoff(),
            )
            if cached is not None:
                cached_event, cached_result = cached
                return cached_result.to_domain(cached_event), True

            incomplete = await asyncio.to_thread(self._repository.has_incomplete_webhook, event_key)
            if incomplete:
                raise WebhookInterruptedUnknownError()

            await asyncio.to_thread(
                self._repository.mark_webhook_processing,
                event_key,
                event,
                purge_before=self._cutoff(),
            )
            try:
                result = await processor(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                # No mutation-stage evidence exists here. Retain the marker so
                # a later delivery cannot repeat an ambiguous execution.
                raise

            if result.status is not OverallStatus.SUCCESS:
                await asyncio.to_thread(self._repository.delete_webhook, event_key)
            else:
                await asyncio.to_thread(
                    self._repository.mark_webhook_completed,
                    event_key,
                    ProcessingResultResponse.from_domain(result),
                )
            return result, False

    def _cutoff(self) -> datetime:
        return datetime.now(UTC) - self._retention


def event_key_for(event: MediaDeletionEvent) -> str:
    """Return the stable digest for one Jellyfin delivery payload."""

    payload = {
        "notification_type": event.notification_type,
        "item_type": event.item_type.value,
        "item_id": event.item_id,
        "name": event.name,
        "path": event.fingerprint.path,
        "tmdb_id": event.fingerprint.tmdb_id,
        "tvdb_id": event.fingerprint.tvdb_id,
        "imdb_id": event.fingerprint.imdb_id,
        "series_name": event.series_name,
        "series_id": event.series_id,
        "season_number": event.season_number,
        "episode_number": event.episode_number,
        "episode_end_number": event.episode_end_number,
        "occurred_at": _json_datetime(event.occurred_at),
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()


def _json_datetime(value: datetime | None) -> str | None:
    """Match Pydantic's stable JSON representation used by historic event keys."""

    if value is None:
        return None
    encoded = value.isoformat()
    return f"{encoded[:-6]}Z" if encoded.endswith("+00:00") else encoded
