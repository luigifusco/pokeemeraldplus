"""Launcher for the randomizer web UI.

Starts uvicorn on 127.0.0.1:8765 by default and opens the browser.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser


def _open_browser_later(url: str, delay: float = 0.6) -> None:
    def _open() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m randomizer.webui",
        description="Launch the pokeemeraldplus randomizer web UI.",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind host (default: 127.0.0.1). Use 0.0.0.0 for LAN access.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser on startup.")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload (development).")
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "uvicorn is required. Install with:\n"
            "    pip install -r randomizer/requirements.txt\n"
        )
        return 2

    url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}/"
    if not args.no_browser:
        _open_browser_later(url)

    print(f"[randomizer] Serving at {url}  (Ctrl+C to stop)")
    uvicorn.run(
        "randomizer.webui.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
