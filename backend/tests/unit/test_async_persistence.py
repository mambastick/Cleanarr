"""Regression coverage for off-loop persistence and ordered progress writes."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cleanarr.application.deletion_jobs import (
    ManualDeletionJobService,
    _flush_writer_before_cancellation,
    _JobProgressReporter,
    _OrderedJobWriter,
    plan_hash,
)
from cleanarr.application.deletion_models import (
    ManualDeleteJobPhase,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint, OverallStatus
from cleanarr.infrastructure import config_store, database, deletion_repository, downloads_repository, users


@dataclass
class _Snapshot:
    phase: ManualDeleteJobPhase
    progress_percent: int
    message: str


class _SlowRepository:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.snapshots: list[_Snapshot] = []
        self.thread_ids: list[int] = []

    def save_job(self, snapshot: _Snapshot) -> None:
        self.started.set()
        self.release.wait(timeout=5)
        self.thread_ids.append(threading.get_ident())
        self.snapshots.append(snapshot)


@pytest.mark.asyncio
async def test_slow_progress_save_does_not_block_event_loop() -> None:
    repository = _SlowRepository()
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 30, "cleanup"))

    heartbeat_count = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_count
        while not repository.release.is_set():
            heartbeat_count += 1
            await asyncio.sleep(0)

    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.to_thread(repository.started.wait, 5)
    await asyncio.sleep(0.01)
    assert heartbeat_count > 0
    repository.release.set()
    await writer.flush()
    await heartbeat_task
    assert repository.thread_ids
    assert repository.thread_ids[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_cancellation_waits_for_inflight_writer_before_releasing() -> None:
    repository = _SlowRepository()
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 30, "cleanup"))
    flush_task = asyncio.create_task(_flush_writer_before_cancellation(writer))
    await asyncio.to_thread(repository.started.wait, 5)
    flush_task.cancel()
    await asyncio.sleep(0)
    assert not flush_task.done()
    repository.release.set()
    with pytest.raises(asyncio.CancelledError):
        await flush_task
    assert repository.snapshots


@pytest.mark.asyncio
async def test_progress_phase_is_persisted_before_external_mutation() -> None:
    persisted: list[_Snapshot] = []

    class Repository:
        def save_job(self, snapshot: _Snapshot) -> None:
            persisted.append(snapshot)

    repository = Repository()
    job = SimpleNamespace(phase=ManualDeleteJobPhase.PLANNING, progress_percent=5, message="planning")
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    reporter = _JobProgressReporter(job, writer)  # type: ignore[arg-type]
    external_mutation_started = False

    reporter(ManualDeleteJobPhase.CLEANING, 30, "starting mutation", "item")
    await reporter.flush()
    external_mutation_started = True

    assert external_mutation_started
    assert persisted[-1].phase is ManualDeleteJobPhase.CLEANING


@pytest.mark.asyncio
async def test_terminal_snapshot_is_fifo_after_coalesced_progress() -> None:
    class Repository:
        def __init__(self) -> None:
            self.snapshots: list[_Snapshot] = []

        def save_job(self, snapshot: _Snapshot) -> None:
            self.snapshots.append(snapshot)

    repository = Repository()
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 30, "first"))
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 50, "latest progress"))
    writer.submit(_Snapshot(ManualDeleteJobPhase.COMPLETED, 100, "done"))
    await writer.flush()

    assert [snapshot.message for snapshot in repository.snapshots] == ["latest progress", "done"]
    assert repository.snapshots[-1].phase is ManualDeleteJobPhase.COMPLETED


@pytest.mark.asyncio
async def test_writer_failure_is_replayed_by_later_flush() -> None:
    class Repository:
        calls = 0

        def save_job(self, snapshot: _Snapshot) -> None:
            self.calls += 1
            raise OSError("disk full")

    repository = Repository()
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 30, "cleanup"))
    with pytest.raises(OSError, match="disk full"):
        await writer.flush()
    writer.submit(_Snapshot(ManualDeleteJobPhase.COMPLETED, 100, "done"))
    with pytest.raises(OSError, match="disk full"):
        await writer.flush()
    assert repository.calls == 1


@pytest.mark.asyncio
async def test_confirmed_job_flushes_progress_before_runner_mutation(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    repository = deletion_repository.SQLiteDeletionRepository(db_path)
    event = MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="manual:radarr:1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=1, path="/media/movie"),
    )
    result = ProcessingResultResponse(
        item_type=ItemType.MOVIE,
        item_id=event.item_id,
        name=event.name,
        status=OverallStatus.SUCCESS,
        actions=[],
    )
    mutation_seen = asyncio.Event()
    job_id: str | None = None

    async def resolver(_payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(_payload: ManualDeleteRequest, _event: MediaDeletionEvent) -> ProcessingResultResponse:
        return result

    async def runner(
        _payload: ManualDeleteRequest, _event: MediaDeletionEvent, report: object
    ) -> ProcessingResultResponse:
        assert callable(report)
        report(ManualDeleteJobPhase.CLEANING, 30, "starting mutation", event.name)  # type: ignore[operator]
        await report.flush()  # type: ignore[attr-defined]
        persisted = await asyncio.to_thread(repository.load_job, job_id)
        assert persisted is not None
        assert persisted.phase is ManualDeleteJobPhase.CLEANING
        mutation_seen.set()
        return result

    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        retry_delays_seconds=(0,),
    )
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        confirmed_plan_hash=plan_hash(result),
        idempotency_key=uuid4(),
    )
    submitted = await service.submit(request)
    job_id = str(submitted.id)
    try:
        await asyncio.wait_for(mutation_seen.wait(), timeout=5)
    finally:
        await service.stop()


class _TrackedConnection:
    def __init__(self, connection: object) -> None:
        self._connection = connection
        self.closed = False

    def __enter__(self) -> _TrackedConnection:
        self._connection.__enter__()
        return self

    def __exit__(self, *args: object) -> object:
        return self._connection.__exit__(*args)

    def close(self) -> None:
        self.closed = True
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


@pytest.mark.parametrize(
    ("module",),
    [(config_store,), (database,), (deletion_repository,), (downloads_repository,), (users,)],
)
def test_repository_connection_context_closes_on_success_and_error(
    module: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked: list[_TrackedConnection] = []
    original_connect = module.sqlite3.connect  # type: ignore[attr-defined]

    def tracked_connect(*args: object, **kwargs: object) -> _TrackedConnection:
        connection = _TrackedConnection(original_connect(*args, **kwargs))
        tracked.append(connection)
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", tracked_connect)  # type: ignore[attr-defined]
    connect = module._connect  # type: ignore[attr-defined]
    path = tmp_path / f"{module.__name__.rsplit('.', 1)[-1]}.db"
    with connect(path) as connection:
        connection.execute("CREATE TABLE marker (value INTEGER)")
    with pytest.raises(RuntimeError, match="boom"):
        with connect(path) as connection:
            connection.execute("INSERT INTO marker VALUES (1)")
            raise RuntimeError("boom")
    assert tracked
    assert all(connection.closed for connection in tracked)


async def test_cancelling_initial_flush_keeps_thread_writer_drainable() -> None:
    repository = _SlowRepository()
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    writer.submit(_Snapshot(ManualDeleteJobPhase.CLEANING, 30, "cleanup"))
    flush_task = asyncio.create_task(writer.flush())
    await asyncio.to_thread(repository.started.wait, 5)
    flush_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await flush_task
    drain = asyncio.create_task(_flush_writer_before_cancellation(writer))
    await asyncio.sleep(0)
    assert not drain.done()
    repository.release.set()
    await drain
    assert len(repository.snapshots) == 1
