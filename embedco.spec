# PyInstaller spec for EmbedCo editor.
# Build with: pyinstaller embedco.spec

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "ui"), "ui"),
    (str(root / "blocks"), "blocks"),
    (str(root / "boards.yaml"), "."),
    (str(root / "examples"), "examples"),
]

plugins_dir = root / "plugins"
if plugins_dir.exists():
    datas.append((str(plugins_dir), "plugins"))

a = Analysis(
    [str(root / "server.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "serial.tools.list_ports",
        "serial.tools",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="EmbedCo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
