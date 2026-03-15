"""Tests for GraphQL client default timeouts.

Verifies that the GraphQL client sets sensible default timeouts
instead of None (which causes indefinite hangs).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from caido_sdk_client.graphql.client import GraphQLClient


def _make_auth_mock() -> MagicMock:
    auth = MagicMock()
    auth.get_access_token.return_value = None
    auth.on_token_refresh.return_value = lambda: None
    return auth


class TestGraphQLTimeout:
    """GraphQL client timeout configuration."""

    def test_default_timeout_is_30_seconds(self) -> None:
        """When no timeout_ms is specified, default to 30 seconds."""
        client = GraphQLClient("http://localhost:8080", _make_auth_mock())
        assert client._timeout_seconds == 30

    def test_custom_timeout_ms(self) -> None:
        """When timeout_ms is specified, convert to seconds."""
        client = GraphQLClient(
            "http://localhost:8080", _make_auth_mock(), timeout_ms=10000
        )
        assert client._timeout_seconds == 10.0

    def test_sub_second_timeout_not_truncated(self) -> None:
        """Sub-second timeouts should not be truncated to 0."""
        client = GraphQLClient(
            "http://localhost:8080", _make_auth_mock(), timeout_ms=500
        )
        assert client._timeout_seconds == 0.5

    def test_http_transport_uses_timeout(self) -> None:
        """HTTP transport should be created with the timeout."""
        client = GraphQLClient(
            "http://localhost:8080", _make_auth_mock(), timeout_ms=5000
        )
        assert client._http_transport.timeout == 5.0

    def test_http_transport_uses_default_timeout(self) -> None:
        """HTTP transport should use default 30s when not specified."""
        client = GraphQLClient("http://localhost:8080", _make_auth_mock())
        assert client._http_transport.timeout == 30

    def test_ws_transport_uses_connect_timeout(self) -> None:
        """WebSocket transport should have connect_timeout set."""
        client = GraphQLClient(
            "http://localhost:8080", _make_auth_mock(), timeout_ms=15000
        )
        assert client._ws_transport.connect_timeout == 15.0

    def test_ws_transport_uses_default_connect_timeout(self) -> None:
        """WebSocket transport should use default 30s connect timeout."""
        client = GraphQLClient("http://localhost:8080", _make_auth_mock())
        assert client._ws_transport.connect_timeout == 30
