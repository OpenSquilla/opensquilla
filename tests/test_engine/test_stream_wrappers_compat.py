from __future__ import annotations

from opensquilla.engine import stream_wrappers as engine_stream_wrappers
from opensquilla.runtime import stream_wrappers


def test_engine_stream_wrappers_reexport_runtime_functions() -> None:
    assert engine_stream_wrappers.wrap_stream is stream_wrappers.wrap_stream
    assert engine_stream_wrappers.heartbeat_stream is stream_wrappers.heartbeat_stream
    assert engine_stream_wrappers.idle_timeout_stream is stream_wrappers.idle_timeout_stream
