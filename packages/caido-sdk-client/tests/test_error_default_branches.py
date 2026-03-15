"""Tests for error constructor default branches.

Verifies that error classes handle unknown enum variants gracefully
instead of producing half-constructed objects.
"""

from __future__ import annotations

from enum import Enum
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


class TestCloudUserErrorDefaultBranch:
    """CloudUserError should handle unknown enum variants."""

    def test_known_unavailable(self) -> None:
        fragment = CloudUserErrorFull(
            cloudReason=CloudErrorReason.UNAVAILABLE, code="CLOUD"
        )
        error = CloudUserError(fragment)
        assert error.reason == CloudErrorReason.UNAVAILABLE
        assert "communicate" in str(error)

    def test_known_unexpected(self) -> None:
        fragment = CloudUserErrorFull(
            cloudReason=CloudErrorReason.UNEXPECTED, code="CLOUD"
        )
        error = CloudUserError(fragment)
        assert error.reason == CloudErrorReason.UNEXPECTED
        assert "unknown error" in str(error)

    def test_unknown_variant_does_not_crash(self) -> None:
        """Simulate a new server-side enum variant the SDK doesn't know about."""
        fragment = MagicMock()
        fragment.cloudReason = "NEW_VARIANT"
        error = CloudUserError(fragment)
        assert error.reason == "NEW_VARIANT"
        assert "Cloud error" in str(error)
        assert "NEW_VARIANT" in str(error)


class TestPluginUserErrorDefaultBranch:
    """PluginUserError should handle unknown enum variants."""

    def test_known_variant(self) -> None:
        fragment = MagicMock(spec=PluginUserErrorFull)
        fragment.reason = PluginErrorReason.INVALID_MANIFEST
        error = PluginUserError(fragment)
        assert error.reason == PluginErrorReason.INVALID_MANIFEST
        assert "manifest" in str(error)

    def test_unknown_variant_does_not_crash(self) -> None:
        fragment = MagicMock(spec=PluginUserErrorFull)
        fragment.reason = "NEW_PLUGIN_REASON"
        error = PluginUserError(fragment)
        assert error.reason == "NEW_PLUGIN_REASON"
        assert "Plugin error" in str(error)


class TestStoreUserErrorDefaultBranch:
    """StoreUserError should handle unknown enum variants."""

    def test_known_variant(self) -> None:
        fragment = MagicMock(spec=StoreUserErrorFull)
        fragment.storeReason = StoreErrorReason.PACKAGE_TOO_LARGE
        error = StoreUserError(fragment)
        assert "too large" in str(error)

    def test_unknown_variant_does_not_crash(self) -> None:
        fragment = MagicMock(spec=StoreUserErrorFull)
        fragment.storeReason = "NEW_STORE_REASON"
        error = StoreUserError(fragment)
        assert "Store error" in str(error)
        assert "NEW_STORE_REASON" in str(error)


class TestProjectUserErrorDefaultBranch:
    """ProjectUserError should handle unknown enum variants."""

    def test_known_variant(self) -> None:
        error = ProjectUserError(ProjectErrorReason.DELETING)
        assert error.reason == ProjectErrorReason.DELETING
        assert "deleted" in str(error)

    def test_all_known_variants(self) -> None:
        """Every existing enum variant should produce a valid error."""
        for reason in ProjectErrorReason:
            error = ProjectUserError(reason)
            assert error.reason == reason
            assert str(error)  # Has a message

    def test_unknown_variant_does_not_crash(self) -> None:
        error = ProjectUserError("FUTURE_REASON")  # type: ignore[arg-type]
        assert error.reason == "FUTURE_REASON"
        assert "Project error" in str(error)
