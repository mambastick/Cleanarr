from pathlib import Path

import pytest

from cleanarr.application.authentication import AuthenticationService
from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.domain.config import GeneralConfig, RuntimeConfig, SSOAuthMode
from cleanarr.infrastructure.auth import InMemorySessionStore, PasswordHasher
from cleanarr.infrastructure.config_store import FileConfigStore
from cleanarr.infrastructure.settings import Settings


def build_auth_service(tmp_path: Path, *, sso_mode: SSOAuthMode) -> AuthenticationService:
    store = FileConfigStore(str(tmp_path / f"{sso_mode.value}.json"))
    store.save(
        RuntimeConfig(
            general=GeneralConfig(
                sso_mode=sso_mode,
                sso_issuer_url="https://auth.example.com/application/o/cleanarr/",
                sso_client_id="cleanarr",
                sso_client_secret="secret",
            )
        )
    )
    config_service = RuntimeConfigurationService(
        store=store,
        settings=Settings.model_construct(),
    )
    return AuthenticationService(
        config_service=config_service,
        password_hasher=PasswordHasher(),
        session_store=InMemorySessionStore(),
    )


@pytest.mark.parametrize(
    ("sso_mode", "sso_enabled", "sso_configured", "requires_registration"),
    [
        (SSOAuthMode.PASSWORD_ONLY, False, False, True),
        (SSOAuthMode.BOTH, True, True, False),
        (SSOAuthMode.SSO_ONLY, True, True, False),
    ],
)
def test_auth_status_reports_enabled_login_methods(
    tmp_path: Path,
    sso_mode: SSOAuthMode,
    sso_enabled: bool,
    sso_configured: bool,
    requires_registration: bool,
) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=sso_mode)

    status = auth_service.get_status(None)

    assert status.sso_mode is sso_mode
    assert status.sso_enabled is sso_enabled
    assert status.sso_configured is sso_configured
    assert status.requires_registration is requires_registration


def test_sso_only_rejects_local_login(tmp_path: Path) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.SSO_ONLY)

    with pytest.raises(PermissionError, match="Local authentication is disabled"):
        auth_service.login(username="admin", password="password")
