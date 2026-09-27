"""Optional operational events, separate from graph state and model reasoning."""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

EventSink = Callable[[dict[str, Any]], None]
sink: ContextVar[EventSink | None] = ContextVar("progress_sink", default=None)
active_node: ContextVar[str] = ContextVar("progress_node", default="")


def emit(event: str, **data: Any) -> None:
    callback = sink.get()
    if callback is not None:
        callback({"event": event, "node": active_node.get(), **data})
