"""One-click desktop launcher.

PyInstaller bundles this module together with the FastAPI backend and the built
frontend (``frontend/dist``). At runtime it:

1. redirects the SQLite/JWT/model-cache directories to a per-user location so the
   data survives the one-file extraction directory being wiped on exit;
2. serves the SPA and the API from one process on a free loopback port;
3. opens the default browser at the served URL.

The server binds ``127.0.0.1`` only: this is a local teaching app, not a network
service. Closing the console window (or Ctrl+C) stops the server.

Usage:
    python -m app.desktop [--port 0] [--no-browser] [--data-dir PATH]
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_TITLE = "os-visualizer"


def bundle_root() -> Path:
    """Root of the extracted bundle (PyInstaller) or the repository backend dir."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def default_static_dir() -> Path | None:
    """Locate the built frontend that ships next to the executable."""
    root = bundle_root()
    candidates = [root / "frontend", root / "dist", root / "static"]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def default_data_dir() -> Path:
    """Per-user writable directory, so one-file extraction stays disposable."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_TITLE


def free_port() -> int:
    """Ask the OS for an unused loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(port: int, timeout: float = 30.0) -> bool:
    """Block until the HTTP listener accepts connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_TITLE, description="Start os-visualizer locally.")
    parser.add_argument("--port", type=int, default=0, help="TCP port (0 = pick a free one)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument("--data-dir", default="", help="override the user data directory")
    return parser.parse_args(argv)


def configure_environment(args: argparse.Namespace) -> Path:
    """Set env vars *before* importing app.config, which reads them at import time."""
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("OSVIS_DATA_DIR", str(data_dir))
    os.environ.setdefault("OSVIS_MODELS_DIR", str(data_dir / "models_cache"))
    static_dir = default_static_dir()
    if static_dir is not None:
        os.environ.setdefault("OSVIS_STATIC_DIR", str(static_dir))
    return data_dir


def _configure_console() -> None:
    """Keep console output safe on Windows code pages (cp1252/cp936)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = parse_args(argv)
    data_dir = configure_environment(args)

    import uvicorn  # imported late: config must see the env above

    from app.main import app

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}/"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, name="osvis-server", daemon=True)
    server_thread.start()

    if not wait_until_ready(port):
        print(f"[{APP_TITLE}] Failed to start: port {port} was not ready within 30s.", file=sys.stderr)
        return 1

    print(f"[{APP_TITLE}] Serving at {url}")
    print(f"[{APP_TITLE}] Data directory: {data_dir}")
    print(f"[{APP_TITLE}] Close this window or press Ctrl+C to stop.")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - depends on desktop session
            print(f"[{APP_TITLE}] Could not open a browser ({exc}); open {url} manually.", file=sys.stderr)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print(f"\n[{APP_TITLE}] Shutting down...")
        server.should_exit = True
        server_thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())