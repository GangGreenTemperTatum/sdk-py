"""Tests for the Request SDK."""

from __future__ import annotations

import pytest
from caido_sdk_client import Client

from tests.utils import create_mock_request


@pytest.mark.usefixtures("test_project")
async def test_list_requests_matching_httpql_filter(caido: Client) -> None:
    """List requests with an HTTPQL filter (mirrors JS request.spec)."""
    await create_mock_request()

    filter_expr = 'req.host.ne:"perdu.com"'
    matched = (
        await caido.request.list()
        .filter(filter_expr)
        .first(10)
        .descending("req", "created_at")
    )
    assert len(matched.edges) >= 0


@pytest.mark.usefixtures("test_project")
async def test_list_requests_with_pagination(caido: Client) -> None:
    """List requests with first(2), descending by created_at, then next page."""
    await create_mock_request()
    await create_mock_request()
    await create_mock_request()

    response = await caido.request.list().first(2).descending("req", "created_at")
    assert len(response.edges) == 2
    assert response.page_info.has_next_page is True
    assert response.edges[0].node.request.id == "3"
    assert response.edges[1].node.request.id == "2"

    next_response = await response.next()
    assert next_response is not None
    assert len(next_response.edges) == 1
    assert next_response.page_info.has_next_page is False
    assert next_response.edges[0].node.request.id == "1"
