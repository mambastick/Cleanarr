"""File-backed runtime configuration store."""

from __future__ import annotations

import json
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
