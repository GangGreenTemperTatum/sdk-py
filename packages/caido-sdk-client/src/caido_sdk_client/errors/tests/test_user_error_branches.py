"""Tests for error constructor default branches (unknown enum variants)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from caido_sdk_client.errors.cloud import CloudUserError
from caido_sdk_client.errors.plugin import PluginUserError, StoreUserError
from caido_sdk_client.errors.project import ProjectUserError
from caido_sdk_client.graphql.__generated__.schema import (
    CloudErrorReason,
    CloudUserErrorFull,
    PluginErrorReason,
    PluginUserErrorFull,
    ProjectErrorReason,
    StoreErrorReason,
    StoreUserErrorFull,
)


def test_cloud_user_error_known_unavailable() -> None:
    fragment = CloudUserErrorFull(
        cloudReason=CloudErrorReason.UNAVAILABLE, code="CLOUD"
    )
    error = CloudUserError(fragment)
    assert error.reason == CloudErrorReason.UNAVAILABLE
    assert "communicate" in str(error)


def test_cloud_user_error_known_unexpected() -> None:
    fragment = CloudUserErrorFull(cloudReason=CloudErrorReason.UNEXPECTED, code="CLOUD")
    error = CloudUserError(fragment)
    assert error.reason == CloudErrorReason.UNEXPECTED
    assert "unknown error" in str(error)


def test_cloud_user_error_unknown_variant() -> None:
    fragment = MagicMock()
    fragment.cloudReason = "NEW_VARIANT"
    error = CloudUserError(fragment)
    assert error.reason == "NEW_VARIANT"
    assert "Cloud error" in str(error)
    assert "NEW_VARIANT" in str(error)


def test_plugin_user_error_known_variant() -> None:
    fragment = MagicMock(spec=PluginUserErrorFull)
    fragment.reason = PluginErrorReason.INVALID_MANIFEST
    error = PluginUserError(fragment)
    assert error.reason == PluginErrorReason.INVALID_MANIFEST
    assert "manifest" in str(error)


def test_plugin_user_error_unknown_variant() -> None:
    fragment = MagicMock(spec=PluginUserErrorFull)
    fragment.reason = "NEW_PLUGIN_REASON"
    error = PluginUserError(fragment)
    assert error.reason == "NEW_PLUGIN_REASON"
    assert "Plugin error" in str(error)


def test_store_user_error_known_variant() -> None:
    fragment = MagicMock(spec=StoreUserErrorFull)
    fragment.storeReason = StoreErrorReason.PACKAGE_TOO_LARGE
    error = StoreUserError(fragment)
    assert "too large" in str(error)


def test_store_user_error_unknown_variant() -> None:
    fragment = MagicMock(spec=StoreUserErrorFull)
    fragment.storeReason = "NEW_STORE_REASON"
    error = StoreUserError(fragment)
    assert "Store error" in str(error)
    assert "NEW_STORE_REASON" in str(error)


def test_project_user_error_known_variant() -> None:
    error = ProjectUserError(ProjectErrorReason.DELETING)
    assert error.reason == ProjectErrorReason.DELETING
    assert "deleted" in str(error)


@pytest.mark.parametrize("reason", list(ProjectErrorReason))
def test_project_user_error_all_known_variants(reason: ProjectErrorReason) -> None:
    error = ProjectUserError(reason)
    assert error.reason == reason
    assert str(error)


def test_project_user_error_unknown_variant() -> None:
    error = ProjectUserError("FUTURE_REASON")  # type: ignore[arg-type]
    assert error.reason == "FUTURE_REASON"
    assert "Project error" in str(error)
