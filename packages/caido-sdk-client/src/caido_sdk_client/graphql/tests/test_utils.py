"""Tests for to_user_error() and has_authorization_error() in graphql.utils."""

from __future__ import annotations

import pytest

from caido_sdk_client.errors.authorization import AuthorizationUserError
from caido_sdk_client.errors.cloud import CloudUserError
from caido_sdk_client.errors.misc import OtherUserError
from caido_sdk_client.graphql.utils import has_authorization_error, to_user_error


def _make_graphql_error(code: str, **extra: object) -> dict[str, object]:
    return {
        "message": "test error",
        "extensions": {
            "CAIDO": {"code": code, **extra},
        },
    }


@pytest.mark.parametrize(
    "reason",
    ["FORBIDDEN", "INVALID_TOKEN", "MISSING_SCOPE"],
)
def test_to_user_error_authorization_known_reason(reason: str) -> None:
    error = to_user_error(_make_graphql_error("AUTHORIZATION", reason=reason))
    assert isinstance(error, AuthorizationUserError)
    assert error.reason == reason


def test_to_user_error_authorization_unknown_reason_still_typed() -> None:
    error = to_user_error(_make_graphql_error("AUTHORIZATION", reason="EXPIRED_TOKEN"))
    assert error is not None
    assert isinstance(error, AuthorizationUserError)
    assert error.reason == "EXPIRED_TOKEN"


def test_to_user_error_authorization_missing_reason_is_other() -> None:
    error = to_user_error(_make_graphql_error("AUTHORIZATION"))
    assert error is not None
    assert isinstance(error, OtherUserError)


def test_to_user_error_authorization_non_string_reason_is_other() -> None:
    error = to_user_error(_make_graphql_error("AUTHORIZATION", reason=42))
    assert error is not None
    assert isinstance(error, OtherUserError)


def test_to_user_error_cloud_known_reason() -> None:
    error = to_user_error(_make_graphql_error("CLOUD", reason="UNAVAILABLE"))
    assert isinstance(error, CloudUserError)


def test_to_user_error_cloud_unknown_reason_is_other() -> None:
    error = to_user_error(_make_graphql_error("CLOUD", reason="RATE_LIMITED"))
    assert error is not None
    assert isinstance(error, OtherUserError)
    assert "RATE_LIMITED" in str(error)


def test_to_user_error_cloud_missing_reason_is_other() -> None:
    error = to_user_error(_make_graphql_error("CLOUD"))
    assert error is not None
    assert isinstance(error, OtherUserError)


def test_to_user_error_internal_with_message() -> None:
    error = to_user_error(_make_graphql_error("INTERNAL", message="something broke"))
    assert isinstance(error, OtherUserError)
    assert "something broke" in str(error)


def test_to_user_error_internal_missing_message_is_other() -> None:
    error = to_user_error(_make_graphql_error("INTERNAL"))
    assert error is not None
    assert isinstance(error, OtherUserError)
    assert "Internal error" in str(error)


def test_to_user_error_internal_non_string_message_is_other() -> None:
    error = to_user_error(_make_graphql_error("INTERNAL", message=123))
    assert error is not None
    assert isinstance(error, OtherUserError)


def test_to_user_error_unknown_code_returns_none() -> None:
    assert to_user_error(_make_graphql_error("TOTALLY_NEW_CODE")) is None


def test_to_user_error_no_extensions_returns_none() -> None:
    assert to_user_error({"message": "plain error"}) is None


def test_to_user_error_no_caido_extension_returns_none() -> None:
    error = to_user_error({"message": "error", "extensions": {"other": "stuff"}})
    assert error is None


def test_has_authorization_error_detects_known_reason() -> None:
    errors = [_make_graphql_error("AUTHORIZATION", reason="INVALID_TOKEN")]
    assert has_authorization_error(errors) is True


def test_has_authorization_error_detects_unknown_reason() -> None:
    errors = [_make_graphql_error("AUTHORIZATION", reason="EXPIRED_TOKEN")]
    assert has_authorization_error(errors) is True


def test_has_authorization_error_false_for_non_auth() -> None:
    errors = [_make_graphql_error("INTERNAL", message="oops")]
    assert has_authorization_error(errors) is False


def test_has_authorization_error_empty_list() -> None:
    assert has_authorization_error([]) is False


def test_has_authorization_error_mixed_errors() -> None:
    errors = [
        _make_graphql_error("INTERNAL", message="oops"),
        _make_graphql_error("AUTHORIZATION", reason="FORBIDDEN"),
    ]
    assert has_authorization_error(errors) is True
