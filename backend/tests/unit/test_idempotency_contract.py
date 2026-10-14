"""Contract coverage for browser-generated idempotency keys."""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cleanarr.api.download_schemas import DownloadActionRequest
from cleanarr.application.deletion_models import ManualDeleteBatchSubmitRequest, ManualDeleteRequest
from cleanarr.domain import ItemType
from cleanarr.domain.downloads import DownloadControlAction


def test_rfc4122_v4_key_is_accepted_by_all_destructive_request_schemas() -> None:
    key = uuid4()
    child = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=42)

    delete = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=42, idempotency_key=key)
    batch = ManualDeleteBatchSubmitRequest(
        children=[child],
        idempotency_key=key,
        confirmed_batch_hash="batch-plan-hash",
        confirmed_item_count=1,
    )
    download = DownloadActionRequest(
        client_id="client",
        info_hash="a" * 40,
        action=DownloadControlAction.PAUSE,
        idempotency_key=str(key),
    )

    assert delete.idempotency_key == key
    assert batch.idempotency_key == key
    assert download.idempotency_key == str(key)
    assert len(download.idempotency_key) == 36


@pytest.mark.parametrize(
    "model, payload",
    [
        (
            ManualDeleteRequest,
            {"item_type": ItemType.MOVIE, "radarr_movie_id": 42, "idempotency_key": "cleanarr-0123456789abcdef"},
        ),
        (
            ManualDeleteBatchSubmitRequest,
            {
                "children": [{"item_type": ItemType.MOVIE, "radarr_movie_id": 42}],
                "idempotency_key": "cleanarr-0123456789abcdef",
                "confirmed_batch_hash": "batch-plan-hash",
                "confirmed_item_count": 1,
            },
        ),
        (
            DownloadActionRequest,
            {
                "client_id": "client",
                "info_hash": "a" * 40,
                "action": DownloadControlAction.PAUSE,
                "idempotency_key": "cleanarr-0123456789abcdef",
            },
        ),
    ],
)
def test_legacy_non_uuid_fallback_is_rejected(model: type[object], payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)  # type: ignore[attr-defined]


def test_uuid_fixture_has_rfc4122_version_and_variant_bits() -> None:
    value = UUID("12345678-1234-4abc-8def-1234567890ab")
    assert value.version == 4
    assert value.variant == "specified in RFC 4122"
