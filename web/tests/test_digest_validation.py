from __future__ import annotations

import pytest

from web.tests.test_registry_api import (  # noqa: F401
    build_headers,
    create_asset,
    registry_client,
    seed_built_design,
)

MALFORMED_DIGESTS = [
    "not-a-digest",
    "A" * 64,
    "0" * 63,
    "0" * 65,
    "é" * 64,
    "0" * 63 + "ß",
]


def assert_structured_validation_error(response) -> None:
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "invalid_request"
    assert isinstance(payload["detail"], list)
    assert payload["detail"]
    for entry in payload["detail"]:
        assert set(entry) == {"field", "code", "message"}
        assert entry["message"].isascii()
        assert len(entry["message"]) <= 201


@pytest.mark.parametrize("digest", MALFORMED_DIGESTS)
def test_design_review_rejects_malformed_expected_digest(
    registry_client, digest
) -> None:
    seeded = seed_built_design(registry_client, design_id="design-review-digest")

    response = registry_client.post(
        f"/api/designs/{seeded['design_id']}/reviews",
        headers=build_headers(subject_id="reviewer-1", roles="reviewer"),
        json={"expected_digest": digest, "decision": "approved"},
    )

    assert_structured_validation_error(response)


@pytest.mark.parametrize("digest", MALFORMED_DIGESTS)
def test_build_submission_rejects_malformed_expected_digest(
    registry_client, digest
) -> None:
    seeded = seed_built_design(registry_client, design_id="design-build-digest")

    response = registry_client.post(
        f"/api/designs/{seeded['design_id']}/builds",
        headers=build_headers(subject_id="author-1", roles="author"),
        json={"expected_digest": digest},
    )

    assert_structured_validation_error(response)


@pytest.mark.parametrize("digest", MALFORMED_DIGESTS)
def test_version_review_rejects_malformed_expected_digest(
    registry_client, digest
) -> None:
    response = registry_client.post(
        "/api/registry/versions/version-1/reviews",
        headers=build_headers(subject_id="reviewer-1", roles="reviewer"),
        json={"expected_digest": digest, "decision": "approved"},
    )

    assert_structured_validation_error(response)


@pytest.mark.parametrize("digest", MALFORMED_DIGESTS)
def test_version_publish_rejects_malformed_expected_digest(
    registry_client, digest
) -> None:
    response = registry_client.post(
        "/api/registry/versions/version-1/publish",
        headers=build_headers(roles="registry-admin"),
        json={"expected_digest": digest, "channel": "stable"},
    )

    assert_structured_validation_error(response)


@pytest.mark.parametrize("digest", MALFORMED_DIGESTS)
def test_version_revoke_rejects_malformed_expected_digest(
    registry_client, digest
) -> None:
    response = registry_client.post(
        "/api/registry/versions/version-1/revoke",
        headers=build_headers(roles="registry-admin"),
        json={"expected_digest": digest},
    )

    assert_structured_validation_error(response)


def test_validation_detail_is_bounded(registry_client) -> None:
    response = registry_client.post(
        "/api/registry/assets",
        headers=build_headers(),
        json={"type": "invalid", "slug": "Bad_Slug"},
    )

    assert response.status_code == 422
    assert len(response.json()["detail"]) <= 10
