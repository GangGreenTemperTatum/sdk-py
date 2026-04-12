"""Tests for GraphQLClient auth retry on authorization errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gql.transport.exceptions import TransportQueryError

from caido_sdk_client.errors.authorization import AuthorizationUserError
from caido_sdk_client.errors.graphql import OperationUserError
from caido_sdk_client.graphql.client import GraphQLClient


def _make_auth_mock(*, can_refresh: bool = True) -> MagicMock:
    auth = MagicMock()
    auth.get_access_token.return_value = "test-token"
    auth.can_refresh.return_value = can_refresh
    auth.refresh = AsyncMock()
    auth.on_token_refresh.return_value = lambda: None
    return auth


def _make_auth_query_error() -> TransportQueryError:
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


async def test_graphql_execute_retries_on_auth_error_and_succeeds() -> None:
    auth = _make_auth_mock(can_refresh=True)
    client = GraphQLClient("http://localhost:8080", auth)

    call_count = 0

    async def mock_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _make_auth_query_error()
        return {"data": "success"}

    with patch.object(client._http_client, "execute_async", side_effect=mock_execute):
        result = await client._execute("query { test }", None)

    assert result == {"data": "success"}
    assert call_count == 2
    auth.refresh.assert_awaited_once()


async def test_graphql_execute_does_not_retry_when_cannot_refresh() -> None:
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


async def test_graphql_execute_does_not_retry_twice() -> None:
    auth = _make_auth_mock(can_refresh=True)
    client = GraphQLClient("http://localhost:8080", auth)

    with patch.object(
        client._http_client,
        "execute_async",
        side_effect=_make_auth_query_error(),
    ):
        with pytest.raises(AuthorizationUserError):
            await client._execute("query { test }", None)

    auth.refresh.assert_awaited_once()


async def test_graphql_execute_does_not_retry_on_non_auth_error() -> None:
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


async def test_graphql_execute_no_retry_without_errors_list() -> None:
    auth = _make_auth_mock(can_refresh=True)
    client = GraphQLClient("http://localhost:8080", auth)

    exc = TransportQueryError("bare error", errors=None)
    with patch.object(client._http_client, "execute_async", side_effect=exc):
        with pytest.raises(OperationUserError):
            await client._execute("query { test }", None)

    auth.refresh.assert_not_awaited()
