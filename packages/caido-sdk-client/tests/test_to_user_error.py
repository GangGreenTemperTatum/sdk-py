"""Tests for to_user_error() preserving error classification.

Verifies that recognized CAIDO error codes with unknown reasons
produce typed errors instead of silently returning None.
"""

from __future__ import annotations

from caido_sdk_client.errors.authorization import AuthorizationUserError
from caido_sdk_client.errors.cloud import CloudUserError
from caido_sdk_client.errors.misc import OtherUserError
from caido_sdk_client.graphql.utils import has_authorization_error, to_user_error


def _make_graphql_error(code: str, **extra: object) -> dict[str, object]:
    """Build a GraphQL error dict with CAIDO extensions."""
    return {
        "message": "test error",
        "extensions": {
            "CAIDO": {"code": code, **extra},
        },
    }


class TestToUserErrorAuthorization:
    """AUTHORIZATION code handling."""

    def test_known_reason_forbidden(self) -> None:
        error = to_user_error(_make_graphql_error("AUTHORIZATION", reason="FORBIDDEN"))
        assert isinstance(error, AuthorizationUserError)
        assert error.reason == "FORBIDDEN"

    def test_known_reason_invalid_token(self) -> None:
        error = to_user_error(
            _make_graphql_error("AUTHORIZATION", reason="INVALID_TOKEN")
        )
        assert isinstance(error, AuthorizationUserError)
        assert error.reason == "INVALID_TOKEN"

    def test_known_reason_missing_scope(self) -> None:
        error = to_user_error(
            _make_graphql_error("AUTHORIZATION", reason="MISSING_SCOPE")
        )
        assert isinstance(error, AuthorizationUserError)
        assert error.reason == "MISSING_SCOPE"

    def test_unknown_reason_still_returns_authorization_error(self) -> None:
        """A new server-side reason should still be classified as auth, not None."""
        error = to_user_error(
            _make_graphql_error("AUTHORIZATION", reason="EXPIRED_TOKEN")
        )
        assert error is not None, "Should not return None for recognized code"
        assert isinstance(error, AuthorizationUserError)
        assert error.reason == "EXPIRED_TOKEN"

    def test_missing_reason_returns_other_error(self) -> None:
        """Missing reason string should produce an error, not None."""
        error = to_user_error(_make_graphql_error("AUTHORIZATION"))
        assert error is not None
        assert isinstance(error, OtherUserError)

    def test_non_string_reason_returns_other_error(self) -> None:
        error = to_user_error(_make_graphql_error("AUTHORIZATION", reason=42))
        assert error is not None
        assert isinstance(error, OtherUserError)


class TestToUserErrorCloud:
    """CLOUD code handling."""

    def test_known_reason(self) -> None:
        error = to_user_error(_make_graphql_error("CLOUD", reason="UNAVAILABLE"))
        assert isinstance(error, CloudUserError)

    def test_unknown_reason_returns_other_error(self) -> None:
        """A new cloud reason should produce OtherUserError, not None."""
        error = to_user_error(_make_graphql_error("CLOUD", reason="RATE_LIMITED"))
        assert error is not None, "Should not return None for recognized code"
        assert isinstance(error, OtherUserError)
        assert "RATE_LIMITED" in str(error)

    def test_missing_reason_returns_other_error(self) -> None:
        error = to_user_error(_make_graphql_error("CLOUD"))
        assert error is not None
        assert isinstance(error, OtherUserError)


class TestToUserErrorInternal:
    """INTERNAL code handling."""

    def test_with_message(self) -> None:
        error = to_user_error(
            _make_graphql_error("INTERNAL", message="something broke")
        )
        assert isinstance(error, OtherUserError)
        assert "something broke" in str(error)

    def test_missing_message_returns_other_error(self) -> None:
        """Missing message should produce a fallback error, not None."""
        error = to_user_error(_make_graphql_error("INTERNAL"))
        assert error is not None, "Should not return None for recognized code"
        assert isinstance(error, OtherUserError)
        assert "Internal error" in str(error)

    def test_non_string_message_returns_other_error(self) -> None:
        error = to_user_error(_make_graphql_error("INTERNAL", message=123))
        assert error is not None
        assert isinstance(error, OtherUserError)


class TestToUserErrorUnrecognizedCode:
    """Unrecognized codes should still return None (no CAIDO classification)."""

    def test_unknown_code_returns_none(self) -> None:
        error = to_user_error(_make_graphql_error("TOTALLY_NEW_CODE"))
        assert error is None

    def test_no_extensions_returns_none(self) -> None:
        error = to_user_error({"message": "plain error"})
        assert error is None

    def test_no_caido_extension_returns_none(self) -> None:
        error = to_user_error({"message": "error", "extensions": {"other": "stuff"}})
        assert error is None


class TestHasAuthorizationError:
    """has_authorization_error() should detect auth errors including unknown reasons."""

    def test_detects_known_auth_error(self) -> None:
        errors = [_make_graphql_error("AUTHORIZATION", reason="INVALID_TOKEN")]
        assert has_authorization_error(errors) is True

    def test_detects_unknown_auth_reason(self) -> None:
        """An unknown auth reason should still be detected as an auth error."""
        errors = [_make_graphql_error("AUTHORIZATION", reason="EXPIRED_TOKEN")]
        assert has_authorization_error(errors) is True

    def test_non_auth_error(self) -> None:
        errors = [_make_graphql_error("INTERNAL", message="oops")]
        assert has_authorization_error(errors) is False

    def test_empty_list(self) -> None:
        assert has_authorization_error([]) is False

    def test_mixed_errors(self) -> None:
        errors = [
            _make_graphql_error("INTERNAL", message="oops"),
            _make_graphql_error("AUTHORIZATION", reason="FORBIDDEN"),
        ]
        assert has_authorization_error(errors) is True
