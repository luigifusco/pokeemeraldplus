"""Entry point: python -m battleui [--http-port N] [--tcp-port N]"""
from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from .server import create_app


def main() -> None:
    ap = argparse.ArgumentParser(prog="battleui")
    ap.add_argument("--http-port", type=int, default=9876)
    ap.add_argument("--tcp-port", type=int, default=9877)
    ap.add_argument("--host", default="127.0.0.1",
                    help="(deprecated) sets both --http-host and --tcp-host")
    ap.add_argument("--http-host", default=None,
                    help="HTTP/WS bind address (default: same as --host). "
                         "Use 0.0.0.0 to expose the UI publicly.")
    ap.add_argument("--tcp-host", default=None,
                    help="TCP bind address for the mGBA Lua bridge "
                         "(default: 127.0.0.1 when --http-host is set, "
                         "otherwise same as --host). Use 0.0.0.0 when you want "
                         "the bridge to be reachable over the internet; "
                         "pair with --token.")
    ap.add_argument("--token", default=os.environ.get("BATTLEUI_TOKEN", ""),
                    help="Shared secret. When set, the TCP bridge must send "
                         "{'type':'hello','token':...} as its first line and "
                         "the WebSocket must include ?token=... in its URL. "
                         "Falls back to $BATTLEUI_TOKEN.")
    args = ap.parse_args()

    http_host = args.http_host or args.host
    tcp_host = args.tcp_host or ("127.0.0.1" if args.http_host else args.host)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.token and (http_host == "0.0.0.0" or tcp_host == "0.0.0.0"):
        logging.getLogger("battleui").warning(
            "binding publicly with no --token set; anyone who reaches these "
            "ports can control the battle or impersonate the ROM."
        )

    app = create_app(tcp_host=tcp_host, tcp_port=args.tcp_port, token=args.token)
    uvicorn.run(app, host=http_host, port=args.http_port, log_level="info")


if __name__ == "__main__":
    main()
