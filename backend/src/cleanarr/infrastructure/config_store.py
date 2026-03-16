"""Runtime configuration stores (file-backed and SQLite-backed)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock

from cleanarr.domain.config import RuntimeConfig


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
            return RuntimeConfig.model_validate(payload)

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
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS config ("
                "  id INTEGER PRIMARY KEY CHECK (id = 1),"
                "  config_json TEXT NOT NULL"
                ")"
            )
            conn.commit()

    def load(self) -> RuntimeConfig | None:
        """Return the persisted config, auto-migrating from a JSON file if needed."""

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT config_json FROM config WHERE id = 1"
                ).fetchone()
            if row:
                return RuntimeConfig.model_validate_json(row[0])
            # First run: migrate from legacy JSON file when present.
            if self._migrate_from and self._migrate_from.exists():
                payload = json.loads(self._migrate_from.read_text(encoding="utf-8"))
                config = RuntimeConfig.model_validate(payload)
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
