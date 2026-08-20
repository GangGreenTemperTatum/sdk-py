"""Top-level Replay SDK with version-aware transport routing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, cast

from caido_sdk_client.convert.blob import encode_blob
from caido_sdk_client.errors.all_errors import AllErrors
from caido_sdk_client.errors.misc import NotFoundUserError, OtherUserError
from caido_sdk_client.graphql import GraphQLClient
from caido_sdk_client.sdks.replay_collection import ReplayCollectionSDK
from caido_sdk_client.sdks.replay_entry import ReplayEntrySDK
from caido_sdk_client.sdks.replay_session import ReplaySessionSDK
from caido_sdk_client.sdks.task import ReplayTask, TaskSDK
from caido_sdk_client.transport.latest.__generated__ import schema as latest
from caido_sdk_client.transport.v0_56.__generated__ import schema as v0_56
from caido_sdk_client.types.replay_session import ReplaySendOptions, ReplaySendResult
from caido_sdk_client.types.strings import IdLike
from caido_sdk_client.types.task import TaskResult
from caido_sdk_client.types.versioned import TransportVersion
from caido_sdk_client.utils.errors import handle_graphql_error
from caido_sdk_client.version import Version


def _placeholders(options: ReplaySendOptions) -> list[dict[str, object]]:
    settings = options.settings
    if settings is None or settings.placeholders is None:
        return []
    return [
        {
            "inputRange": {
                "start": placeholder.input_range.start,
                "end": placeholder.input_range.end,
            },
            "outputRange": {
                "start": placeholder.output_range.start,
                "end": placeholder.output_range.end,
            },
            "preprocessors": placeholder.preprocessors or [],
        }
        for placeholder in settings.placeholders
    ]


class _PrimedTaskStream:
    """Wrap the finishedTask stream so the subscription is live before use.

    ``TaskSDK.finished()`` returns a lazy async generator: the websocket is only
    opened on the first ``__anext__``. Awaiting that first item would block
    until a task finishes, which is too late — the task has to be started
    first. So prime it in the background: kick off ``__anext__`` as a task, let
    the event loop run until the transport is connected, and buffer whatever
    that first pull yields.
    """

    def __init__(self, source: AsyncIterator[TaskResult]) -> None:
        self._source = source
        self._pending: asyncio.Task[TaskResult] | None = None
        self._closed = False

    async def prime(self) -> None:
        """Start the subscription so it is live before the caller acts.

        The pull is kicked off as a task and control is handed to the event
        loop, which runs the generator up to the point where it awaits the
        websocket. That is enough for the server to register the subscriber;
        we deliberately do NOT wait for an event, so the common path pays no
        added latency.
        """
        self._pending = asyncio.ensure_future(anext(self._source))
        await asyncio.sleep(0)

    def __aiter__(self) -> _PrimedTaskStream:
        return self

    async def __anext__(self) -> TaskResult:
        if self._pending is not None:
            pending, self._pending = self._pending, None
            return await pending
        return await anext(self._source)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        pending = self._pending
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            except Exception:  # noqa: BLE001 - teardown must not mask the result
                pass
            self._pending = None
        aclose = getattr(self._source, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - teardown must not mask the result
                pass
        # Cancelling the pending pull unwinds the generator via the event loop;
        # yield once so its `finally` (which detaches the transport) has run by
        # the time this returns.
        await asyncio.sleep(0)


class ReplaySDK:
    """Top-level Replay SDK: sessions, collections, entries, and send."""

    def __init__(self, graphql: GraphQLClient, version: Version | None = None) -> None:
        self._graphql = graphql
        self._version = version or Version.of(TransportVersion.V0_57.value)
        self.entries = ReplayEntrySDK(graphql, self._version)
        self.sessions = ReplaySessionSDK(graphql, self._version, self.entries)
        self.collections = ReplayCollectionSDK(graphql)
        self._tasks = TaskSDK(graphql)

    async def send(
        self, session_id: IdLike, options: ReplaySendOptions
    ) -> ReplaySendResult:
        if await self._version.gte(TransportVersion.V0_57.value):
            return await self._send_latest(session_id, options)
        return await self._send_v0_56(session_id, options)

    async def _send_latest(
        self, session_id: IdLike, options: ReplaySendOptions
    ) -> ReplaySendResult:
        raw_session = await self._graphql.query(
            latest.ReplaySession.Meta.document,
            variables={"id": str(session_id)},
        )
        model = latest.ReplaySession.model_validate(raw_session)
        if model.replaySession is None:
            raise NotFoundUserError()
        session = model.replaySession
        if not isinstance(session, latest.ReplaySessionHttpMeta):
            raise OtherUserError("INTERNAL", "SDK only supports HTTP sessions")

        target_entry_id = (
            session.activeEntry.id if session.activeEntry is not None else None
        )
        if target_entry_id is None:
            if not session.entries.edges:
                raise OtherUserError("INTERNAL", "Replay session has no entries")
            target_entry_id = session.entries.edges[-1].node.id

        await self._graphql.mutation(
            latest.UpdateReplayEntryDraft.Meta.document,
            variables={
                "id": target_entry_id,
                "input": {
                    "http": {
                        "connection": {
                            "host": options.connection.host,
                            "port": options.connection.port,
                            "isTLS": options.connection.is_tls,
                            "SNI": options.connection.sni,
                        },
                        "editorState": encode_blob(options.raw),
                        "raw": encode_blob(options.raw),
                        "settings": {"placeholders": _placeholders(options)},
                    }
                },
            },
        )

        requested = options.settings
        current_settings = session.settings
        connection_close = requested.connection_close if requested is not None else None
        update_content_length = (
            requested.update_content_length if requested is not None else None
        )
        if (
            connection_close is not None
            and (
                current_settings is None
                or connection_close != current_settings.connectionClose
            )
        ) or (
            update_content_length is not None
            and (
                current_settings is None
                or update_content_length != current_settings.updateContentLength
            )
        ):
            await self._graphql.mutation(
                latest.UpdateReplaySessionSettings.Meta.document,
                variables={
                    "id": str(session_id),
                    "input": {
                        "http": {
                            "connectionClose": connection_close
                            if connection_close is not None
                            else (
                                current_settings.connectionClose
                                if current_settings is not None
                                else False
                            ),
                            "updateContentLength": update_content_length
                            if update_content_length is not None
                            else (
                                current_settings.updateContentLength
                                if current_settings is not None
                                else True
                            ),
                        }
                    },
                },
            )

        # Subscribe BEFORE starting the task so a fast-completing replay cannot
        # finish inside the gap between mutation and subscription.
        async with self._finished_tasks() as finished:
            raw = await self._graphql.mutation(
                latest.StartReplayTask.Meta.document,
                variables={"sessionId": str(session_id)},
            )
            payload = latest.StartReplayTask.model_validate(raw).startReplayTask
            if payload.error is not None:
                handle_graphql_error(cast(AllErrors, payload.error))
            if payload.task is None:
                raise OtherUserError("INTERNAL", "startReplayTask returned no task")
            task = ReplayTask(self._graphql, payload.task)
            return await self._wait_for_task(task, finished)

    async def _send_v0_56(
        self, session_id: IdLike, options: ReplaySendOptions
    ) -> ReplaySendResult:
        async with self._finished_tasks() as finished:
            return await self._start_and_wait_v0_56(session_id, options, finished)

    async def _start_and_wait_v0_56(
        self,
        session_id: IdLike,
        options: ReplaySendOptions,
        finished: AsyncIterator[TaskResult],
    ) -> ReplaySendResult:
        settings = options.settings
        raw = await self._graphql.mutation(
            v0_56.StartReplayTask.Meta.document,
            variables={
                "sessionId": str(session_id),
                "input": {
                    "connection": {
                        "host": options.connection.host,
                        "port": options.connection.port,
                        "isTLS": options.connection.is_tls,
                        "SNI": options.connection.sni,
                    },
                    "raw": encode_blob(options.raw),
                    "settings": {
                        "connectionClose": (
                            settings.connection_close
                            if settings is not None
                            and settings.connection_close is not None
                            else False
                        ),
                        "updateContentLength": (
                            settings.update_content_length
                            if settings is not None
                            and settings.update_content_length is not None
                            else True
                        ),
                        "placeholders": _placeholders(options),
                    },
                },
            },
        )
        payload = v0_56.StartReplayTask.model_validate(raw).startReplayTask
        if payload.error is not None:
            handle_graphql_error(cast(AllErrors, payload.error))
        if payload.task is None:
            raise OtherUserError("INTERNAL", "startReplayTask returned no task")
        task = ReplayTask(self._graphql, payload.task)
        return await self._wait_for_task(task, finished)

    @asynccontextmanager
    async def _finished_tasks(self) -> AsyncIterator[AsyncIterator[TaskResult]]:
        """Open the finishedTask subscription and keep it live for the caller.

        The underlying subscription is lazy: it only connects on first
        iteration. Priming it here means the websocket is established *before*
        the caller starts a task, so a task that completes immediately still
        produces an observable event.
        """
        stream = self._tasks.finished(lambda _: True)
        primed = _PrimedTaskStream(stream)
        await primed.prime()
        try:
            yield primed
        finally:
            await primed.aclose()

    async def _wait_for_task(
        self,
        task: ReplayTask,
        finished: AsyncIterator[TaskResult] | None = None,
    ) -> ReplaySendResult:
        source = (
            finished
            if finished is not None
            else self._tasks.finished(lambda item: item.task.id == task.id)
        )
        async for result in source:
            if result.task.id != task.id:
                continue
            entry = await self.entries.get(task.replay_entry_id)
            if entry is None:
                raise OtherUserError("INTERNAL", "Replay entry not found")
            return ReplaySendResult(
                entry=entry,
                status=cast(Literal["DONE", "CANCELLED", "ERROR"], result.status),
                error=result.error,
            )
        raise OtherUserError(
            "INTERNAL",
            "Replay task subscription ended without finished event",
        )
