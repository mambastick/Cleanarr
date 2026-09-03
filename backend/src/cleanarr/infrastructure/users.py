"""SQLite persistence for authenticated CleanArr users."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from cleanarr.application.users import LastAdministratorError, UserNotFoundError
from cleanarr.domain.users import UserAccount, UserAuthSource, UserRole
from cleanarr.infrastructure.database import migrate_database


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(username: str) -> str:
    return username.strip().casefold()


class SqliteUserAccountStore:
    """Store known local/SSO identities without storing provider claims."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._lock = Lock()
        migrate_database(self._db_path)

    def ensure_user(self, username: str, auth_source: UserAuthSource, default_role: UserRole) -> UserAccount:
        normalized = username.strip()
        if not normalized:
            raise ValueError("Username cannot be empty.")
        now = _now()
        with self._lock, sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "INSERT INTO user_accounts(username_key,username,role,auth_source,created_at,last_seen_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(username_key) DO UPDATE SET "
                "username=excluded.username,last_seen_at=excluded.last_seen_at,updated_at=excluded.updated_at",
                (_key(normalized), normalized, default_role.value, auth_source.value, now, now, now),
            )
            row = connection.execute(
                "SELECT username,role,auth_source,created_at,last_seen_at,updated_at "
                "FROM user_accounts WHERE username_key=?",
                (_key(normalized),),
            ).fetchone()
            connection.commit()
        return _account(row)

    def ensure_sso_user(self, username: str) -> UserAccount:
        """Atomically bootstrap the first administrator, then default new SSO users to viewer."""

        normalized = username.strip()
        if not normalized:
            raise ValueError("Username cannot be empty.")
        now = _now()
        with self._lock, sqlite3.connect(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM user_accounts WHERE username_key=?", (_key(normalized),)
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE user_accounts SET username=?,last_seen_at=?,updated_at=? WHERE username_key=?",
                    (normalized, now, now, _key(normalized)),
                )
            else:
                has_admin = connection.execute("SELECT 1 FROM user_accounts WHERE role='admin' LIMIT 1").fetchone()
                role = UserRole.VIEWER if has_admin else UserRole.ADMIN
                connection.execute(
                    "INSERT INTO user_accounts("
                    "username_key,username,role,auth_source,created_at,last_seen_at,updated_at"
                    ") "
                    "VALUES(?,?,?,?,?,?,?)",
                    (_key(normalized), normalized, role.value, UserAuthSource.SSO.value, now, now, now),
                )
            row = connection.execute(
                "SELECT username,role,auth_source,created_at,last_seen_at,updated_at "
                "FROM user_accounts WHERE username_key=?",
                (_key(normalized),),
            ).fetchone()
            connection.commit()
        return _account(row)

    def touch_user(self, username: str) -> UserAccount | None:
        now = _now()
        with self._lock, sqlite3.connect(self._db_path) as connection:
            cursor = connection.execute(
                "UPDATE user_accounts SET last_seen_at=?,updated_at=? WHERE username_key=?",
                (now, now, _key(username)),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT username,role,auth_source,created_at,last_seen_at,updated_at "
                "FROM user_accounts WHERE username_key=?",
                (_key(username),),
            ).fetchone()
            connection.commit()
        return _account(row)

    def get_role(self, username: str) -> UserRole | None:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT role FROM user_accounts WHERE username_key=?", (_key(username),)
            ).fetchone()
        return UserRole(str(row[0])) if row else None

    def has_administrator(self) -> bool:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute("SELECT 1 FROM user_accounts WHERE role='admin' LIMIT 1").fetchone()
        return row is not None

    def list_users(self) -> tuple[UserAccount, ...]:
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT username,role,auth_source,created_at,last_seen_at,updated_at FROM user_accounts "
                "ORDER BY last_seen_at IS NULL,last_seen_at DESC,username_key"
            ).fetchall()
        return tuple(_account(row) for row in rows)

    def update_role(self, username: str, role: UserRole) -> UserAccount:
        now = _now()
        with self._lock, sqlite3.connect(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT username,role FROM user_accounts WHERE username_key=?",
                (_key(username),),
            ).fetchone()
            if row is None:
                raise UserNotFoundError("User was not found.")
            current_role = UserRole(str(row[1]))
            if current_role is UserRole.ADMIN and role is not UserRole.ADMIN:
                admin_count = int(
                    connection.execute("SELECT COUNT(*) FROM user_accounts WHERE role='admin'").fetchone()[0]
                )
                if admin_count <= 1:
                    raise LastAdministratorError("The last administrator cannot be demoted.")
            connection.execute(
                "UPDATE user_accounts SET role=?,updated_at=? WHERE username_key=?",
                (role.value, now, _key(username)),
            )
            updated = connection.execute(
                "SELECT username,role,auth_source,created_at,last_seen_at,updated_at "
                "FROM user_accounts WHERE username_key=?",
                (_key(username),),
            ).fetchone()
            connection.commit()
        return _account(updated)


def _account(row: sqlite3.Row | tuple[object, ...] | None) -> UserAccount:
    if row is None:
        raise RuntimeError("User account row disappeared during a transaction.")
    return UserAccount(
        username=str(row[0]),
        role=UserRole(str(row[1])),
        auth_source=UserAuthSource(str(row[2])),
        created_at=str(row[3]),
        last_seen_at=str(row[4]) if row[4] is not None else None,
        updated_at=str(row[5]),
    )
