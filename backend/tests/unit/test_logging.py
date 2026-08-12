"""Credential-redaction coverage for structured logs."""

from __future__ import annotations

import logging
import sys

from cleanarr.api.schemas import ActionResultResponse
from cleanarr.domain import ActionStatus
from cleanarr.infrastructure.logging import JsonFormatter


def test_json_formatter_redacts_credentials_from_messages_and_exceptions() -> None:
    try:
        raise RuntimeError(
            "request https://url-user:url-password@example.test/path?token=query-token "
            "Authorization: Bearer bearer-token api_key=plain-api-key password='plain-password'"
        )
    except RuntimeError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="cleanarr.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="client_secret=json-secret access_token=access-secret",
        args=(),
        exc_info=exception_info,
    )
    record.correlation_id = "correlation-123"

    formatted = JsonFormatter().format(record)

    for secret in (
        "url-password",
        "query-token",
        "bearer-token",
        "plain-api-key",
        "plain-password",
        "json-secret",
        "access-secret",
    ):
        assert secret not in formatted
    assert "[redacted]" in formatted
    assert '"correlation_id": "correlation-123"' in formatted


def test_action_response_redacts_persisted_messages_and_nested_details() -> None:
    response = ActionResultResponse(
        system="downloader",
        action="delete_hashes",
        status=ActionStatus.FAILED,
        message="Authorization: Bearer activity-secret",
        details={
            "api_key": "detail-secret",
            "nested": {"password": "nested-secret"},
            "url": "https://user:url-secret@example.test/path?token=query-secret",
        },
    )

    serialized = response.model_dump_json()

    for secret in ("activity-secret", "detail-secret", "nested-secret", "url-secret", "query-secret"):
        assert secret not in serialized
    assert serialized.count("[redacted]") >= 5
