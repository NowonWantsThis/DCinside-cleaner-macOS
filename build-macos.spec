# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


block_cipher = None
project_root = Path.cwd()
app_name = "DCInside Cleaner"
version_values = {}
exec(
    (project_root / "dcinside_cleaner" / "version.py").read_text(encoding="utf-8"),
    version_values,
)
app_version = version_values["APP_VERSION"]

resource_root = project_root / "dcinside_cleaner" / "gui" / "resources"
datas = [
    (str(resource_root / "ui" / "ui_main_window.ui"), "resources/ui"),
    (str(resource_root / "ui" / "ui_proxies_input_window.ui"), "resources/ui"),
    (str(resource_root / "ui" / "ui_proxies_check_window.ui"), "resources/ui"),
    (str(resource_root / "ui" / "ui_about_dialog.ui"), "resources/ui"),
    (str(resource_root / "icon" / "logo_icon.ico"), "resources/icon"),
    (str(resource_root / "icon" / "logo_icon.icns"), "resources/icon"),
    (str(resource_root / "icon" / "chevron_down_dark.png"), "resources/icon"),
    (str(resource_root / "icon" / "chevron_down_light.png"), "resources/icon"),
    (str(resource_root / "img" / "logo_wide.png"), "resources/img"),
]

a = Analysis(
    ["execute.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["PyQt5.sip"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=app_name,
)

app = BUNDLE(
    coll,
    name=f"{app_name}.app",
    icon=str(resource_root / "icon" / "logo_icon.icns"),
    bundle_identifier="com.dlcjsdltlq.dcinside-cleaner",
    info_plist={
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "NSHighResolutionCapable": "True",
    },
)
