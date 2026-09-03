"""Runtime configuration stores (file-backed and SQLite-backed)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from pathlib import Path
from threading import Lock
from typing import Any

from cleanarr.domain.config import RuntimeConfig
from cleanarr.infrastructure.config_migrations import migrate_config_payload
from cleanarr.infrastructure.database import migrate_database


class FileConfigStore:
    """Persist runtime configuration in a JSON file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._lock = Lock()

    def load(self) -> RuntimeConfig | None:
        """Load a saved configuration when it exists."""

        with self._lock:
            if not self._path.exists():
                return None
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            config = RuntimeConfig.model_validate(migrate_config_payload(payload))
            if _schema_version(payload) == 3:
                _ensure_file_v3_backup(self._path)
            return config

    def save(self, config: RuntimeConfig) -> None:
        """Persist the current configuration atomically."""

        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            tmp_path.write_text(
                config.model_dump_json(indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)


class SqliteConfigStore:
    """SQLite-backed runtime configuration store.

    Stores the entire RuntimeConfig as a single JSON blob in a ``config`` table.
    On first access the store transparently migrates an existing
    ``runtime-config.json`` file so deployments can upgrade without data loss.
    """

    def __init__(self, db_path: str, *, migrate_from: str | None = None) -> None:
        self._db_path = Path(db_path)
        self._migrate_from = Path(migrate_from) if migrate_from else None
        self._lock = Lock()
        self._v3_backup_prepared = False
        self._validated_migrate_config: RuntimeConfig | None = None
        persisted_payload: dict[str, Any] | None = None
        if self._db_path.exists():
            persisted_payload = _read_sqlite_config_payload(self._db_path)
            if persisted_payload is not None:
                # Validate the persisted config before any database migration can
                # rewrite an otherwise unsupported or malformed installation.
                RuntimeConfig.model_validate(migrate_config_payload(persisted_payload))
                if _schema_version(persisted_payload) == 3:
                    _ensure_sqlite_v3_backup(self._db_path)
                    self._v3_backup_prepared = True
        if persisted_payload is None and self._migrate_from and self._migrate_from.exists():
            legacy_payload = _read_file_config_payload(self._migrate_from)
            self._validated_migrate_config = RuntimeConfig.model_validate(migrate_config_payload(legacy_payload))
            if _schema_version(legacy_payload) == 3:
                _ensure_file_v3_backup(self._migrate_from)
        migrate_database(self._db_path)

    def load(self) -> RuntimeConfig | None:
        """Return the persisted config, auto-migrating from a JSON file if needed."""

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT config_json FROM config WHERE id = 1").fetchone()
            if row:
                payload = json.loads(row[0])
                config = RuntimeConfig.model_validate(migrate_config_payload(payload))
                if _schema_version(payload) == 3 and not self._v3_backup_prepared:
                    _ensure_sqlite_v3_backup(self._db_path)
                return config
            # First run: migrate from legacy JSON file when present.
            if self._validated_migrate_config is not None:
                config = self._validated_migrate_config
                self._save_locked(config)
                return config
            return None

    def save(self, config: RuntimeConfig) -> None:
        """Persist the current configuration."""

        with self._lock:
            self._save_locked(config)

    def _save_locked(self, config: RuntimeConfig) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO config (id, config_json) VALUES (1, ?)"
                " ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json",
                (config.model_dump_json(),),
            )
            conn.commit()


def config_v3_backup_path(path: Path) -> Path:
    """Return the deterministic, operator-visible backup path for a v3 config."""

    return path.with_name(f"{path.stem}.config-v3.backup{path.suffix}")


def _schema_version(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    value: Any = payload.get("config_schema_version")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _read_file_config_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Persisted runtime configuration contains invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Runtime configuration must be a JSON object.")
    return payload


def _ensure_file_v3_backup(source_path: Path) -> None:
    """Create one immutable sidecar copy before a v3 JSON config is rewritten."""

    backup_path = config_v3_backup_path(source_path)
    source_bytes = source_path.read_bytes()
    if _has_independent_backup(source_path, backup_path):
        if backup_path.read_bytes() != source_bytes:
            raise RuntimeError("The existing v3 configuration backup does not match the configuration being upgraded.")
        return
    tmp_path = backup_path.with_suffix(f"{backup_path.suffix}.tmp")
    try:
        tmp_path.unlink(missing_ok=True)
        tmp_path.write_bytes(source_bytes)
        tmp_path.replace(backup_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _ensure_sqlite_v3_backup(source_path: Path) -> None:
    """Create and integrity-check one SQLite backup before v3 config persistence."""

    backup_path = config_v3_backup_path(source_path)
    source_payload, source_digest = _read_sqlite_v3_snapshot(source_path)
    if _has_independent_backup(source_path, backup_path):
        backup_payload, backup_digest = _read_sqlite_v3_snapshot(backup_path)
        if backup_payload != source_payload or backup_digest != source_digest:
            raise RuntimeError("The existing v3 configuration backup does not match the configuration being upgraded.")
        return
    tmp_path = backup_path.with_suffix(f"{backup_path.suffix}.tmp")
    try:
        tmp_path.unlink(missing_ok=True)
        with sqlite3.connect(source_path) as source, sqlite3.connect(tmp_path) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("The automatic v3 configuration backup failed its integrity check.")
        backup_payload, backup_digest = _read_sqlite_v3_snapshot(tmp_path)
        if backup_payload != source_payload or backup_digest != source_digest:
            raise RuntimeError("The automatic v3 configuration backup does not contain the source v3 payload.")
        tmp_path.replace(backup_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _read_sqlite_v3_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Validate and fingerprint the complete rollback database without mutation."""

    try:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("The v3 configuration backup failed its integrity check.")
            row = connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()
            digest = _sqlite_logical_digest(connection)
    except sqlite3.Error as exc:
        raise RuntimeError("The v3 configuration backup is not a valid CleanArr SQLite database.") from exc
    if row is None or not isinstance(row[0], str):
        raise RuntimeError("The v3 configuration backup does not contain a runtime configuration.")
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("The v3 configuration backup contains invalid JSON.") from exc
    if not isinstance(payload, dict) or _schema_version(payload) != 3:
        raise RuntimeError("The configuration rollback artifact must contain schema v3.")
    return payload, digest


def _has_independent_backup(source_path: Path, backup_path: Path) -> bool:
    """Reject aliases that cannot serve as an immutable rollback artifact."""

    try:
        backup_stat = backup_path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(backup_stat.st_mode) or backup_stat.st_nlink != 1:
        raise RuntimeError("The v3 configuration backup must be an independent regular file.")
    source_stat = source_path.stat()
    if (backup_stat.st_dev, backup_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino):
        raise RuntimeError("The v3 configuration backup must be independent from the live configuration.")
    return True


def _read_sqlite_config_payload(path: Path) -> dict[str, Any] | None:
    """Read persisted config without mutating an older database schema."""

    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as connection:
        config_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'config'"
        ).fetchone()
        if config_table is None:
            return None
        row = connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()
    if row is None:
        return None
    if not isinstance(row[0], str):
        raise ValueError("Persisted runtime configuration must be JSON text.")
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError as exc:
        raise ValueError("Persisted runtime configuration contains invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Runtime configuration must be a JSON object.")
    return payload


def _sqlite_logical_digest(connection: sqlite3.Connection) -> str:
    """Bind a backup to all schema, rows, and compatibility pragmas."""

    material: list[object] = [
        ["user_version", int(connection.execute("PRAGMA user_version").fetchone()[0])],
        ["application_id", int(connection.execute("PRAGMA application_id").fetchone()[0])],
        [
            "schema",
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name, tbl_name, sql"
            ).fetchall(),
        ],
    ]
    table_names = [
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    ]
    for table_name in table_names:
        quoted = '"' + table_name.replace('"', '""') + '"'
        rows = [_sqlite_row_value(row) for row in connection.execute(f"SELECT * FROM {quoted}").fetchall()]
        rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        material.append(["table", table_name, rows])
    encoded = json.dumps(material, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sqlite_row_value(row: tuple[object, ...]) -> list[object]:
    result: list[object] = []
    for value in row:
        if isinstance(value, bytes):
            result.append({"blob": value.hex()})
        elif value is None or isinstance(value, (str, int, float)):
            result.append(value)
        else:
            result.append({"repr": repr(value)})
    return result
