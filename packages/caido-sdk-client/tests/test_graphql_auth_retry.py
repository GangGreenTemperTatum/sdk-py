"""Tests for GraphQL client auth retry on authorization errors.

Verifies that _execute() detects authorization errors, refreshes
the token, and retries once — matching the REST client behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from caido_sdk_client.errors.authorization import AuthorizationUserError
from caido_sdk_client.errors.graphql import OperationUserError
from caido_sdk_client.graphql.client import GraphQLClient
from gql.transport.exceptions import TransportQueryError


def _make_auth_mock(*, can_refresh: bool = True) -> MagicMock:
    """Create a mock AuthManager."""
    auth = MagicMock()
    auth.get_access_token.return_value = "test-token"
    auth.can_refresh.return_value = can_refresh
    auth.refresh = AsyncMock()
    auth.on_token_refresh.return_value = lambda: None
    return auth


def _make_auth_query_error() -> TransportQueryError:
    """Create a TransportQueryError with an authorization CAIDO extension."""
    return TransportQueryError(
        "auth error",
        errors=[
            {
                "message": "Unauthorized",
                "extensions": {
                    "CAIDO": {
                        "code": "AUTHORIZATION",
                        "reason": "INVALID_TOKEN",
                    },
                },
            }
        ],
    )


def _make_non_auth_query_error() -> TransportQueryError:
    """Create a TransportQueryError without an authorization extension."""
    return TransportQueryError(
        "some error",
        errors=[
            {
                "message": "Something else",
                "extensions": {
                    "CAIDO": {
                        "code": "INTERNAL",
                        "message": "Internal server error",
                    },
                },
            }
        ],
    )


class TestGraphQLAuthRetry:
    """GraphQL client should retry on authorization errors."""

    @pytest.mark.asyncio
    async def test_retries_on_auth_error_and_succeeds(self) -> None:
        """First call gets 401, refresh succeeds, retry returns data."""
        auth = _make_auth_mock(can_refresh=True)
        client = GraphQLClient("http://localhost:8080", auth)

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_auth_query_error()
            return {"data": "success"}

        with patch.object(
            client._http_client, "execute_async", side_effect=mock_execute
        ):
            result = await client._execute("query { test }", None)

        assert result == {"data": "success"}
        assert call_count == 2
        auth.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_retry_when_cannot_refresh(self) -> None:
        """If can_refresh() is False, should raise immediately."""
        auth = _make_auth_mock(can_refresh=False)
        client = GraphQLClient("http://localhost:8080", auth)

        with patch.object(
            client._http_client,
            "execute_async",
            side_effect=_make_auth_query_error(),
        ):
            with pytest.raises(AuthorizationUserError):
                await client._execute("query { test }", None)

        auth.refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_retry_twice(self) -> None:
        """If retry also gets auth error, should raise (no infinite loop)."""
        auth = _make_auth_mock(can_refresh=True)
        client = GraphQLClient("http://localhost:8080", auth)

        with patch.object(
            client._http_client,
            "execute_async",
            side_effect=_make_auth_query_error(),
        ):
            with pytest.raises(AuthorizationUserError):
                await client._execute("query { test }", None)

        # refresh is called once (first attempt), then the retry fails and raises
        auth.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_retry_on_non_auth_error(self) -> None:
        """Non-authorization errors should not trigger retry."""
        auth = _make_auth_mock(can_refresh=True)
        client = GraphQLClient("http://localhost:8080", auth)

        with patch.object(
            client._http_client,
            "execute_async",
            side_effect=_make_non_auth_query_error(),
        ):
            with pytest.raises(Exception):
                await client._execute("query { test }", None)

        auth.refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_retry_without_errors_list(self) -> None:
        """TransportQueryError with no errors list should not retry."""
        auth = _make_auth_mock(can_refresh=True)
        client = GraphQLClient("http://localhost:8080", auth)

        exc = TransportQueryError("bare error", errors=None)
        with patch.object(client._http_client, "execute_async", side_effect=exc):
            with pytest.raises(OperationUserError):
                await client._execute("query { test }", None)

        auth.refresh.assert_not_awaited()
