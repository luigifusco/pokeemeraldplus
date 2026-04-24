"""Router unit tests using a fake WebSocket and fake TCP StreamWriter."""
from __future__ import annotations

import asyncio
import json

import pytest

from battleui.router import Router


class FakeWS:
    def __init__(self) -> None:
        self.sent: list = []
        self.closed = False

    async def send_json(self, msg: dict) -> None:
        if self.closed:
            raise RuntimeError("closed")
        self.sent.append(msg)


class FakeWriter:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.drained = 0

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        self.drained += 1

    def lines(self) -> list:
        out = []
        for ln in bytes(self.buf).splitlines():
            if ln.strip():
                out.append(json.loads(ln.decode()))
        return out


@pytest.mark.asyncio
async def test_tcp_request_broadcasts_to_ws() -> None:
    r = Router()
    ws = FakeWS()
    r.add_ws(ws)
    req = {"type": "request", "seq": 1, "battlerId": 1}
    await r.on_tcp_message(req)
    assert ws.sent == [req]
    assert r.pending is not None and r.pending.seq == 1


@pytest.mark.asyncio
async def test_ws_response_routes_to_tcp() -> None:
    r = Router()
    w = FakeWriter()
    r.set_tcp_writer(w)
    ws = FakeWS()
    r.add_ws(ws)
    await r.on_tcp_message({"type": "request", "seq": 5, "battlerId": 1})
    await r.on_ws_message({"type": "response", "seq": 5, "action": 0, "param1": 2, "param2": 3})
    msgs = w.lines()
    assert len(msgs) == 1
    assert msgs[0]["seq"] == 5 and msgs[0]["action"] == 0
    assert r.pending is None


@pytest.mark.asyncio
async def test_stale_response_dropped() -> None:
    r = Router()
    w = FakeWriter()
    r.set_tcp_writer(w)
    ws = FakeWS()
    r.add_ws(ws)
    await r.on_tcp_message({"type": "request", "seq": 10, "battlerId": 1})
    await r.on_ws_message({"type": "response", "seq": 9, "action": 0, "param1": 0, "param2": 0})
    assert w.lines() == []
    assert r.pending is not None and r.pending.seq == 10


@pytest.mark.asyncio
async def test_seq_regression_clears_pending() -> None:
    r = Router()
    ws = FakeWS()
    r.add_ws(ws)
    await r.on_tcp_message({"type": "request", "seq": 50, "battlerId": 1})
    assert r.pending.seq == 50
    # savestate rewinds
    await r.on_tcp_message({"type": "request", "seq": 3, "battlerId": 1})
    assert r.pending.seq == 3
    # stale response at old seq is dropped
    w = FakeWriter()
    r.set_tcp_writer(w)
    await r.on_ws_message({"type": "response", "seq": 50, "action": 0, "param1": 0, "param2": 0})
    assert w.lines() == []
