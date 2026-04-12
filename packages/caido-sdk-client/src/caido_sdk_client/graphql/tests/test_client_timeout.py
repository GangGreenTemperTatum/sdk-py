"""Tests for GraphQLClient default timeouts."""

from __future__ import annotations

from unittest.mock import MagicMock

from caido_sdk_client.graphql.client import GraphQLClient


def _make_auth_mock() -> MagicMock:
    auth = MagicMock()
    auth.get_access_token.return_value = None
    auth.on_token_refresh.return_value = lambda: None
    return auth


def test_graphql_client_default_timeout_is_30_seconds() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock())
    assert client._timeout_seconds == 30


def test_graphql_client_custom_timeout_ms() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock(), timeout_ms=10000)
    assert client._timeout_seconds == 10


def test_graphql_client_http_transport_uses_timeout() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock(), timeout_ms=5000)
    assert client._http_transport.timeout == 5


def test_graphql_client_http_transport_uses_default_timeout() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock())
    assert client._http_transport.timeout == 30


def test_graphql_client_ws_transport_uses_connect_timeout() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock(), timeout_ms=15000)
    assert client._ws_transport.connect_timeout == 15


def test_graphql_client_ws_transport_default_connect_timeout() -> None:
    client = GraphQLClient("http://localhost:8080", _make_auth_mock())
    assert client._ws_transport.connect_timeout == 30
