# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file recipe for the os-visualizer desktop launcher.

Build order (both local and CI):
    cd frontend && npm ci && npm run build
    python -m PyInstaller --clean --noconfirm packaging/os_visualizer.spec

The resulting executable bundles the FastAPI backend (as bytecode + data) and the
built frontend. At run time it picks a free loopback port, serves the SPA and the
API from one process and opens the default browser. See backend/app/desktop.py.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit(
        f"frontend build not found at {FRONTEND_DIST}; run `cd frontend && npm ci && npm run build` first"
    )

# uvicorn resolves protocol/loop implementations dynamically, so static analysis misses them.
hiddenimports = collect_submodules("uvicorn") + collect_submodules("app")

datas = [(str(FRONTEND_DIST), "frontend")]

name = "os-visualizer-1.0.0-win64" if sys.platform == "win32" else "os-visualizer-1.0.0"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "app.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
