# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MultyCapture (Windows + Linux).

Run from the repo root:  pyinstaller --noconfirm packaging/multycapture.spec
Produces a one-folder bundle in dist/MultyCapture/. The installers (Inno Setup /
dpkg-deb) package that folder.
"""

import sys
import os

# Paths in a .spec are resolved relative to the spec's own directory (SPECPATH),
# not the current working directory. Anchor everything to it explicitly.
ROOT = os.path.dirname(SPECPATH)  # repo root (SPECPATH == <root>/packaging)

# pynput and mss import their OS backend dynamically, so PyInstaller can't see it.
if sys.platform.startswith("win"):
    hiddenimports = ["pynput.keyboard._win32", "pynput.mouse._win32", "mss.windows"]
    icon = os.path.join(SPECPATH, "assets", "multycapture.ico")
elif sys.platform.startswith("linux"):
    hiddenimports = [
        "pynput.keyboard._xorg", "pynput.mouse._xorg", "mss.linux",
        "Xlib", "Xlib.display", "ewmh",
    ]
    icon = None
else:
    hiddenimports = []
    icon = None

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        # The AI backends speak HTTP directly and need none of these. The
        # excludes are insurance: PyInstaller follows imports inside functions,
        # so a client library merely present on the build machine gets pulled
        # in — measured at +16 MB for anthropic alone, dragging pydantic_core,
        # jiter and its own copy of libssl into the installer. keyring is here
        # because its backends are found through entry-point metadata that does
        # not survive freezing; ai.credentials falls back to a private file.
        "anthropic", "openai", "google.genai", "keyring",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MultyCapture",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # tray GUI: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MultyCapture",
)
