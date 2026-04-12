"""Filter preset-related user-facing types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from caido_sdk_client.types.strings import Id


class FilterClauseKind(StrEnum):
    """Kind of filter clause (HTTPQL vs StreamQL)."""

    HTTPQL = "HTTPQL"
    StreamQL = "StreamQL"


@dataclass(frozen=True)
class FilterPreset:
    """Filter preset information."""

    id: Id
    name: str
    alias: str
    clause: str
    kind: FilterClauseKind


@dataclass(frozen=True)
class CreateFilterPresetOptions:
    """Options for creating a filter preset."""

    name: str
    """The name of the filter preset."""

    alias: str
    """The alias of the filter preset."""

    clause: str
    """The HTTPQL or StreamQL clause (accepts str or Httpql)."""

    kind: FilterClauseKind | None = None
    """The kind of the filter preset. Defaults to HTTPQL."""


@dataclass(frozen=True)
class UpdateFilterPresetOptions:
    """Options for updating a filter preset."""

    name: str
    """The name of the filter preset."""

    alias: str
    """The alias of the filter preset."""

    clause: str
    """The HTTPQL or StreamQL clause (accepts str or Httpql)."""

    kind: FilterClauseKind | None = None
    """The kind of the filter preset. Defaults to HTTPQL."""
