"""Bridge between a single mGBA TCP client (the Lua script) and any number
of browser WebSocket clients.

The router owns one "pending request" slot at a time. When the emulator
requests a decision, it arrives over TCP as a line-delimited JSON object and is
broadcast to all connected WebSockets. The first browser to answer wins; the
response is forwarded back to TCP and the slot is cleared.

Seq rules:
- A new request with `seq == pending.seq` replaces fields in place (ROM may
  re-post while waiting; treat as idempotent).
- Responses whose seq does not match `pending.seq` are dropped.
- If a savestate rewinds the emulator and seq regresses, the pending slot is
  cleared (`reset_pending`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Set

log = logging.getLogger("battleui.router")


@dataclass
class PendingRequest:
    seq: int
    payload: dict


class Router:
    """Broker between one TCP writer (Lua/mGBA) and N WebSocket clients."""

    def __init__(self) -> None:
        self._tcp_writer: Optional[asyncio.StreamWriter] = None
        self._ws_clients: Set[Any] = set()
        self.pending: Optional[PendingRequest] = None
        self._last_seq: Optional[int] = None
        self._lock = asyncio.Lock()

    # ---- TCP side (Lua) -------------------------------------------------
    def set_tcp_writer(self, writer: Optional[asyncio.StreamWriter]) -> None:
        self._tcp_writer = writer

    async def on_tcp_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "request":
            seq = int(msg.get("seq", -1))
            if self._last_seq is not None and seq < self._last_seq:
                log.info("seq regression %s -> %s; clearing pending", self._last_seq, seq)
                self.reset_pending()
            self._last_seq = seq
            self.pending = PendingRequest(seq=seq, payload=msg)
            log.info("request seq=%d battler=%s", seq, msg.get("battlerId"))
            await self._broadcast_ws(msg)
        elif mtype == "heartbeat":
            await self._broadcast_ws({"type": "heartbeat"})
        elif mtype == "hello":
            log.info("hello from lua: %s", msg)
            self.reset_pending()
            await self._broadcast_ws(msg)
        else:
            log.warning("unknown tcp msg type=%r", mtype)

    # ---- WebSocket side (browser) --------------------------------------
    def add_ws(self, ws: Any) -> None:
        self._ws_clients.add(ws)
        log.info("ws client connected (%d total)", len(self._ws_clients))

    def remove_ws(self, ws: Any) -> None:
        self._ws_clients.discard(ws)
        log.info("ws client disconnected (%d total)", len(self._ws_clients))

    def current_pending(self) -> Optional[dict]:
        return self.pending.payload if self.pending else None

    async def on_ws_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype != "response":
            log.warning("ignoring non-response ws message: %r", mtype)
            return
        seq = int(msg.get("seq", -1))
        if self.pending is None or self.pending.seq != seq:
            log.info("dropping stale response seq=%d (pending=%s)", seq,
                     self.pending.seq if self.pending else None)
            return
        log.info("response seq=%d action=%s p1=%s p2=%s", seq,
                 msg.get("action"), msg.get("param1"), msg.get("param2"))
        await self._send_tcp(msg)
        self.pending = None

    # ---- helpers --------------------------------------------------------
    def reset_pending(self) -> None:
        self.pending = None

    async def _broadcast_ws(self, msg: dict) -> None:
        dead = []
        for ws in list(self._ws_clients):
            try:
                await ws.send_json(msg)
            except Exception as exc:  # noqa: BLE001
                log.warning("ws send failed: %s", exc)
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    async def _send_tcp(self, msg: dict) -> None:
        if self._tcp_writer is None:
            log.warning("no tcp writer; dropping response")
            return
        line = (json.dumps(msg) + "\n").encode("utf-8")
        try:
            self._tcp_writer.write(line)
            await self._tcp_writer.drain()
        except Exception as exc:  # noqa: BLE001
            log.warning("tcp send failed: %s", exc)
