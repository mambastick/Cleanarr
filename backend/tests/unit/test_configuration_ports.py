"""Parity evidence for the application configuration adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cleanarr.application.configuration import ConnectionTestResult, RuntimeConfigurationService
from cleanarr.domain.config import GeneralConfig, RadarrServiceConfig, RuntimeConfig
from cleanarr.infrastructure.settings import Settings


@dataclass
class MemoryRuntimeConfigStore:
    """Minimal store port used to inspect connection-test delegation."""

    config: RuntimeConfig

    def load(self) -> RuntimeConfig:
        return self.config

    def save(self, config: RuntimeConfig) -> None:
        self.config = config


@dataclass
class RecordingConnectionTester:
    """Deterministic application port fake."""

    result: ConnectionTestResult
    calls: list[tuple[RadarrServiceConfig, float]] = field(default_factory=list)

    async def test(self, payload: RadarrServiceConfig, *, timeout_seconds: float) -> ConnectionTestResult:
        self.calls.append((payload, timeout_seconds))
        return self.result


@pytest.mark.asyncio
async def test_runtime_configuration_delegates_connection_test_with_current_timeout() -> None:
    tester = RecordingConnectionTester(ConnectionTestResult(ok=True, message="Radarr responded successfully."))
    service = RuntimeConfigurationService(
        store=MemoryRuntimeConfigStore(RuntimeConfig(general=GeneralConfig(http_timeout_seconds=23.5))),
        settings=Settings.model_construct(),
        connection_tester=tester,
    )
    payload = RadarrServiceConfig(name="Radarr", url="https://radarr.example", api_key="key")

    result = await service.test_service(payload)

    assert result == ConnectionTestResult(ok=True, message="Radarr responded successfully.")
    assert tester.calls == [(payload, 23.5)]
