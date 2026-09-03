from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cleanarr.application.users import LastAdministratorError
from cleanarr.domain.users import UserAuthSource, UserRole
from cleanarr.infrastructure.users import SqliteUserAccountStore


def test_user_store_tracks_identity_and_preserves_role_on_future_sign_in(tmp_path: Path) -> None:
    store = SqliteUserAccountStore(str(tmp_path / "cleanarr.db"))
    admin = store.ensure_user("Admin", UserAuthSource.LOCAL, UserRole.ADMIN)
    viewer = store.ensure_user("viewer@example.com", UserAuthSource.SSO, UserRole.ADMIN)

    assert admin.role is UserRole.ADMIN
    assert viewer.last_seen_at is not None
    assert store.update_role(viewer.username, UserRole.VIEWER).role is UserRole.VIEWER

    signed_in_again = store.ensure_user("VIEWER@example.com", UserAuthSource.SSO, UserRole.ADMIN)
    assert signed_in_again.role is UserRole.VIEWER
    assert signed_in_again.username == "VIEWER@example.com"
    assert store.has_administrator()


def test_user_store_rejects_last_administrator_demotion(tmp_path: Path) -> None:
    store = SqliteUserAccountStore(str(tmp_path / "cleanarr.db"))
    store.ensure_user("admin", UserAuthSource.LOCAL, UserRole.ADMIN)

    with pytest.raises(LastAdministratorError, match="last administrator"):
        store.update_role("admin", UserRole.VIEWER)


def test_first_sso_identity_can_bootstrap_admin_then_new_identities_default_to_viewer(tmp_path: Path) -> None:
    store = SqliteUserAccountStore(str(tmp_path / "cleanarr.db"))

    first = store.ensure_sso_user("first@example.com")
    next_user = store.ensure_sso_user("viewer@example.com")

    assert first.role is UserRole.ADMIN
    assert next_user.role is UserRole.VIEWER


def test_concurrent_sso_bootstrap_creates_exactly_one_administrator(tmp_path: Path) -> None:
    db_path = str(tmp_path / "cleanarr.db")
    stores = (SqliteUserAccountStore(db_path), SqliteUserAccountStore(db_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        accounts = tuple(
            executor.map(lambda pair: pair[0].ensure_sso_user(pair[1]), zip(stores, ("one", "two"), strict=True))
        )

    assert sum(account.role is UserRole.ADMIN for account in accounts) == 1
