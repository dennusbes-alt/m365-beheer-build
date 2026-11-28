# PyInstaller-specificatie. Bouwen: python bouwen.py
#   Windows -> dist/Microsoft 365 beheer/ (map met .exe; start sneller dan een losse onefile-.exe)
#   Mac     -> dist/Microsoft 365 beheer.app
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

NAAM = 'Microsoft 365 beheer'
VERSIE = re.search(r"__version__\s*=\s*'([^']+)'", Path('backend/m365beheer/__init__.py').read_text(encoding='utf-8')).group(1)
V4 = tuple(int(x) for x in (VERSIE.split('.') + ['0', '0', '0'])[:4])

verborgen = [m for m in collect_submodules('m365beheer') if not m.endswith('.mock')]
# Kluis voor API-sleutels (back-up): keyring kiest zijn backend dynamisch; win32ctypes laadt zijn kern ook dynamisch
verborgen += collect_submodules('keyring.backends') + (collect_submodules('win32ctypes') if sys.platform == 'win32' else [])

a = Analysis(
    ['backend/run.py'],
    pathex=['backend'],
    datas=[('frontend/dist', 'web'), ('backend/m365beheer/rapport', 'm365beheer/rapport')],
    hiddenimports=verborgen,
    excludes=['tkinter', 'pydoc', 'lib2to3', 'xmlrpc', 'm365beheer.mock'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='M365-Beheer', console=False,
              icon='assets/AppIcon.icns', argv_emulation=False, codesign_identity=None)
    coll = COLLECT(exe, a.binaries, a.datas, name='M365-Beheer', upx=False)
    app = BUNDLE(
        coll,
        name=NAAM + '.app',
        icon='assets/AppIcon.icns',
        bundle_identifier='nl.justdata.m365beheer',
        version=VERSIE,
        info_plist={
            'CFBundleDisplayName': NAAM,
            'CFBundleShortVersionString': VERSIE,
            'CFBundleVersion': VERSIE,
            'LSMinimumSystemVersion': '11.0',
            'NSHighResolutionCapable': True,
        },
    )
else:
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    versie_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=V4, prodvers=V4),
        kids=[StringFileInfo([StringTable('041304B0', [
            StringStruct('CompanyName', 'Justdata BV'), StringStruct('FileDescription', NAAM),
            StringStruct('FileVersion', VERSIE), StringStruct('InternalName', 'M365Beheer'),
            StringStruct('OriginalFilename', NAAM + '.exe'), StringStruct('ProductName', NAAM),
            StringStruct('ProductVersion', VERSIE)])]),
            VarFileInfo([VarStruct('Translation', [0x0413, 1200])])],
    )
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAAM, console=False,
              icon='assets/icoon.ico', version=versie_info, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAAM, upx=False)
