from pathlib import Path

import pytest

from cleanarr.application.authentication import AuthenticationService, LoginThrottledError
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
                sso_allowed_users=["admin@example.com"],
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


def test_sso_access_policy_matches_user_group_and_required_claim(tmp_path: Path) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.BOTH)
    general = GeneralConfig(
        sso_mode=SSOAuthMode.BOTH,
        sso_allowed_users=["named@example.com"],
        sso_allowed_groups=["cleanarr-admins"],
        sso_group_claim="roles",
        sso_required_claim="tenant",
        sso_required_value="media",
    )

    assert (
        auth_service.authorize_sso_identity(
            general,
            {
                "preferred_username": "named",
                "email": "named@example.com",
                "roles": ["other"],
                "tenant": "media",
            },
        )
        == "named"
    )
    assert (
        auth_service.authorize_sso_identity(
            general,
            {
                "preferred_username": "group-member",
                "roles": ["CleanArr-Admins"],
                "tenant": ["media"],
            },
        )
        == "group-member"
    )

    with pytest.raises(PermissionError, match="access policy denied"):
        auth_service.authorize_sso_identity(
            general,
            {
                "preferred_username": "named",
                "email": "named@example.com",
                "tenant": "wrong",
            },
        )


def test_sso_without_explicit_access_policy_fails_closed(tmp_path: Path) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.BOTH)
    general = GeneralConfig(sso_mode=SSOAuthMode.BOTH)

    with pytest.raises(PermissionError, match="access policy denied"):
        auth_service.authorize_sso_identity(general, {"sub": "admin"})


def test_sso_only_without_access_policy_does_not_offer_registration(tmp_path: Path) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.SSO_ONLY)
    auth_service._config_service.update_general(  # noqa: SLF001 - exercises an upgraded fail-closed config
        GeneralConfig(
            sso_mode=SSOAuthMode.SSO_ONLY,
            sso_issuer_url="https://auth.example.com/application/o/cleanarr/",
            sso_client_id="cleanarr",
            sso_client_secret="secret",
        )
    )

    status = auth_service.get_status(None)

    assert status.sso_configured is False
    assert status.requires_registration is False


def test_local_login_is_throttled_and_sessions_receive_csrf_tokens(tmp_path: Path) -> None:
    auth_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.PASSWORD_ONLY)
    auth_service.register_admin(username="admin", password="correct-password")

    for _ in range(5):
        with pytest.raises(PermissionError, match="Invalid username or password"):
            auth_service.login(username="admin", password="wrong-password", source="192.0.2.10")

    with pytest.raises(LoginThrottledError):
        auth_service.login(username="admin", password="correct-password", source="192.0.2.10")

    fresh_service = build_auth_service(tmp_path, sso_mode=SSOAuthMode.PASSWORD_ONLY)
    fresh_service.register_admin(username="admin", password="correct-password")
    session = fresh_service.login(
        username="admin",
        password="correct-password",
        source="192.0.2.11",
    )
    assert session.username == "admin"
    assert fresh_service.verify_csrf_token(session.token, session.csrf_token)
