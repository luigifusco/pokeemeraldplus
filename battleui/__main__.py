"""Entry point: python -m battleui [--http-port N] [--tcp-port N]"""
from __future__ import annotations

import argparse
import logging

import uvicorn

from .server import create_app


def main() -> None:
    ap = argparse.ArgumentParser(prog="battleui")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--tcp-port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app(tcp_host=args.host, tcp_port=args.tcp_port)
    uvicorn.run(app, host=args.host, port=args.http_port, log_level="info")


if __name__ == "__main__":
    main()
