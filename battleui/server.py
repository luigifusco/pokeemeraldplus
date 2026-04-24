"""FastAPI app + background TCP listener for the Lua bridge."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .names import get_names
from .router import Router

log = logging.getLogger("battleui.server")

STATIC_DIR = Path(__file__).parent / "static"


async def handle_tcp_client(reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter,
                            router: Router,
                            token: str = "") -> None:
    peer = writer.get_extra_info("peername")
    log.info("tcp client connected: %s", peer)
    if token:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        except asyncio.TimeoutError:
            log.warning("tcp client %s timed out waiting for hello", peer)
            writer.close()
            return
        try:
            hello = json.loads(line.decode("utf-8", errors="replace").strip())
        except (json.JSONDecodeError, UnicodeDecodeError):
            hello = None
        if (not isinstance(hello, dict)
                or hello.get("type") != "hello"
                or not hmac.compare_digest(str(hello.get("token", "")), token)):
            log.warning("tcp client %s failed auth", peer)
            writer.close()
            return
    router.set_tcp_writer(writer)
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8", errors="replace").strip())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                log.warning("bad json from tcp: %s", exc)
                continue
            await router.on_tcp_message(msg)
    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        log.info("tcp client disconnected: %s", peer)
        router.set_tcp_writer(None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def start_tcp_listener(router: Router, host: str, port: int,
                             token: str = "") -> asyncio.AbstractServer:
    async def on_client(r, w):
        await handle_tcp_client(r, w, router, token=token)
    server = await asyncio.start_server(on_client, host=host, port=port)
    log.info("TCP listener on %s:%d (auth=%s)",
             host, port, "on" if token else "off")
    return server


def create_app(tcp_host: str = "127.0.0.1", tcp_port: int = 9877,
               token: str = "") -> FastAPI:
    app = FastAPI(title="battleui")
    router = Router()
    app.state.router = router
    app.state.tcp_host = tcp_host
    app.state.tcp_port = tcp_port
    app.state.token = token

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        srv = await start_tcp_listener(router, tcp_host, tcp_port, token=token)
        app.state.tcp_server = srv

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        srv: Optional[asyncio.AbstractServer] = getattr(app.state, "tcp_server", None)
        if srv is not None:
            srv.close()
            await srv.wait_closed()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            str(STATIC_DIR / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/names.json")
    async def names() -> dict:
        # Cached in names.get_names(); parsed on first call.
        return get_names()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        if token:
            provided = ws.query_params.get("token", "")
            if not hmac.compare_digest(provided, token):
                await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        await ws.accept()
        router.add_ws(ws)
        try:
            pending = router.current_pending()
            if pending is not None:
                await ws.send_json(pending)
            while True:
                msg = await ws.receive_json()
                await router.on_ws_message(msg)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("ws error: %s", exc)
        finally:
            router.remove_ws(ws)

    return app
