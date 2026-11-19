"""PyInstaller entry point.

In a frozen bundle the ``app`` package is inside the archive; from a source
checkout we add ``backend/`` to ``sys.path`` so the same command works both ways.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_path() -> None:
    if getattr(sys, "frozen", False):
        return
    backend = Path(__file__).resolve().parents[1] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def main() -> int:
    _bootstrap_path()
    from app.desktop import main as desktop_main

    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())