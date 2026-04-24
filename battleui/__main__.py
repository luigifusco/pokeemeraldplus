"""Entry point: python -m battleui [--http-port N] [--tcp-port N]"""
from __future__ import annotations

import argparse
import logging

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
                         "Use 0.0.0.0 to expose the UI to a tunnel or LAN.")
    ap.add_argument("--tcp-host", default=None,
                    help="TCP bind address for the mGBA Lua bridge "
                         "(default: 127.0.0.1 — keep it local).")
    args = ap.parse_args()

    http_host = args.http_host or args.host
    # The mGBA Lua bridge should stay loopback even when the HTTP UI is
    # exposed publicly — the bridge speaks unauthenticated line-JSON and must
    # not be reachable from outside.
    tcp_host = args.tcp_host or ("127.0.0.1" if args.http_host else args.host)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app(tcp_host=tcp_host, tcp_port=args.tcp_port)
    uvicorn.run(app, host=http_host, port=args.http_port, log_level="info")


if __name__ == "__main__":
    main()
