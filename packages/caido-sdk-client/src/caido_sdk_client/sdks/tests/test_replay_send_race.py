"""Regression tests for the replay.send() finishedTask subscription race.

`replay.send()` used to open the `finishedTask` subscription only *after*
`startReplayTask` had been issued. A replay that completed inside that window
emitted its finished event before anyone was listening, so the `async for`
blocked forever. Against a localhost target this reproduced every time.

These tests model the ordering with a fake transport: the subscription records
when it becomes live, and the mutation only emits its finished event to
subscribers that were already listening — exactly how a real broadcast works.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from caido_sdk_client.sdks.replay import ReplaySDK
from caido_sdk_client.types.network import ConnectionInfoInput
from caido_sdk_client.types.replay_session import ReplaySendOptions
from caido_sdk_client.types.versioned import TransportVersion
from caido_sdk_client.version import Version

TASK_ID = "42"
ENTRY_ID = "7"


class FakeBroadcast:
    """A finishedTask feed that only reaches listeners already subscribed."""

    def __init__(self) -> None:
        self.subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self.subscribe_calls = 0

    def emit(self, event: dict[str, Any]) -> None:
        # Events are dropped if nobody is listening yet — this is the bug.
        for queue in self.subscribers:
            queue.put_nowait(event)

    async def subscribe(self, *_args: Any, **_kwargs: Any):
        self.subscribe_calls += 1
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self.subscribers:
                self.subscribers.remove(queue)


def _finished_event() -> dict[str, Any]:
    return {
        "finishedTask": {
            "status": "DONE",
            "error": None,
            "task": {
                "__typename": "ReplayTask",
                "id": TASK_ID,
                "createdAt": "2026-01-01T00:00:00Z",
                "replayEntry": {"__typename": "ReplayEntryHttp", "id": ENTRY_ID},
            },
        }
    }


class FakeGraphQL:
    """Minimal GraphQLClient stand-in driving the ordering under test."""

    def __init__(self, broadcast: FakeBroadcast, *, instant: bool) -> None:
        self._broadcast = broadcast
        self._instant = instant

    async def query(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "replaySession": {
                "__typename": "ReplaySessionHttp",
                "id": "1",
                "name": "s",
                "collection": {"__typename": "ReplaySessionCollection", "id": "1"},
                "activeEntry": {"id": ENTRY_ID, "__typename": "ReplayEntryHttp"},
                "entries": {"edges": []},
            }
        }

    async def mutation(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if self._instant:
            # Target answered before the mutation even returned.
            self._broadcast.emit(_finished_event())
        else:
            loop = asyncio.get_running_loop()
            loop.call_later(0.05, self._broadcast.emit, _finished_event())
        return {
            "startReplayTask": {
                "error": None,
                "task": {
                    "__typename": "ReplayTask",
                    "id": TASK_ID,
                    "createdAt": "2026-01-01T00:00:00Z",
                    "replayEntry": {"__typename": "ReplayEntryHttp", "id": ENTRY_ID},
                },
            }
        }

    def subscribe(self, *args: Any, **kwargs: Any):
        return self._broadcast.subscribe(*args, **kwargs)


def _build_sdk(*, instant: bool) -> tuple[ReplaySDK, FakeBroadcast]:
    broadcast = FakeBroadcast()
    graphql = FakeGraphQL(broadcast, instant=instant)
    sdk = ReplaySDK(graphql, Version.of(TransportVersion.V0_57.value))

    async def fake_get(_entry_id: Any) -> Any:
        class _Entry:
            id = ENTRY_ID
            request = None
            response = None

        return _Entry()

    sdk.entries.get = fake_get  # type: ignore[method-assign]
    return sdk, broadcast


def _options() -> ReplaySendOptions:
    return ReplaySendOptions(
        raw=b"GET / HTTP/1.1\r\nHost: h\r\n\r\n",
        connection=ConnectionInfoInput(host="h", port=80, is_tls=False),
    )


async def test_send_returns_when_task_finishes_instantly() -> None:
    """The regression: a task finishing during the mutation must still resolve.

    Before the fix this hung forever, because the subscription was opened after
    the finished event had already been broadcast.
    """
    sdk, _ = _build_sdk(instant=True)

    result = await asyncio.wait_for(sdk.send("1", _options()), timeout=5)

    assert result.status == "DONE"
    assert result.entry.id == ENTRY_ID


async def test_send_returns_for_a_slow_task() -> None:
    """The path that already worked keeps working."""
    sdk, _ = _build_sdk(instant=False)

    result = await asyncio.wait_for(sdk.send("1", _options()), timeout=5)

    assert result.status == "DONE"


async def test_subscription_is_open_before_the_mutation_runs() -> None:
    """Ordering guard: subscribe must happen before startReplayTask."""
    sdk, broadcast = _build_sdk(instant=True)
    subscribers_at_start: list[int] = []

    original = sdk._graphql.mutation  # type: ignore[attr-defined]

    async def spy(document: Any, *args: Any, **kwargs: Any) -> Any:
        # Only startReplayTask matters; the draft update legitimately runs
        # before the subscription is opened.
        if "startReplayTask" in str(document):
            subscribers_at_start.append(len(broadcast.subscribers))
        return await original(document, *args, **kwargs)

    sdk._graphql.mutation = spy  # type: ignore[attr-defined]

    await asyncio.wait_for(sdk.send("1", _options()), timeout=5)

    assert subscribers_at_start == [1], (
        "startReplayTask must run with the subscription already live, "
        f"saw {subscribers_at_start}"
    )


async def test_subscription_is_closed_after_send() -> None:
    """The websocket must be torn down once the result is in.

    Teardown unwinds the subscription generator through the event loop, so
    allow it a turn to finish rather than asserting on the same tick.
    """
    sdk, broadcast = _build_sdk(instant=True)

    await asyncio.wait_for(sdk.send("1", _options()), timeout=5)
    for _ in range(100):
        if not broadcast.subscribers:
            break
        await asyncio.sleep(0.01)

    assert broadcast.subscribers == [], "finishedTask subscription was leaked"


async def test_unrelated_task_events_are_ignored() -> None:
    """Now that the stream is unfiltered, foreign task ids must be skipped."""
    sdk, broadcast = _build_sdk(instant=False)

    async def noise() -> None:
        await asyncio.sleep(0.01)
        broadcast.emit(
            {
                "finishedTask": {
                    "status": "DONE",
                    "error": None,
                    "task": {
                        "__typename": "ReplayTask",
                        "id": "999",
                        "createdAt": "2026-01-01T00:00:00Z",
                        "replayEntry": {"__typename": "ReplayEntryHttp", "id": "999"},
                    },
                }
            }
        )

    asyncio.ensure_future(noise())
    result = await asyncio.wait_for(sdk.send("1", _options()), timeout=5)

    assert result.entry.id == ENTRY_ID


@pytest.mark.parametrize("instant", [True, False])
async def test_send_opens_exactly_one_subscription(instant: bool) -> None:
    """One send, one websocket — no per-attempt subscription churn."""
    sdk, broadcast = _build_sdk(instant=instant)

    await asyncio.wait_for(sdk.send("1", _options()), timeout=5)

    assert broadcast.subscribe_calls == 1
