"""Bouwt een release voor het huidige besturingssysteem.

    Windows:  .venv\\Scripts\\python.exe bouwen.py
    Mac:      ./bouwen-mac.sh   (gebruikt dit script)

Resultaat in de uitvoermap (zie uitvoer_map)/<windows|mac>/:
    Microsoft-365-beheer-<versie>-<platform>-<arch>.zip   (wat de installer en de updater downloaden)
    Microsoft-365-beheer-<versie>-<platform>-<arch>.json  (versie, controlegetal en grootte, voor release.py)

PyInstaller kan niet kruiselings bouwen: de Mac-versie moet op een Mac gebouwd worden.
Publiceren gebeurt apart met release.py (pas als het online mag).
"""
from __future__ import annotations

import hashlib
import os
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent

def uitvoer_map() -> Path:
    """Bouwuitvoer buiten OneDrive (anders synchroniseert OneDrive steeds honderden MB's en wordt de pc traag).
    Windows: %LOCALAPPDATA%\\Justdata\\M365Beheer-uitvoer. Op de bouwserver (CI) of Mac: de map uitvoer naast dit script.
    Overschrijven kan met de omgevingsvariabele M365_UITVOER."""
    eigen = os.environ.get('M365_UITVOER')
    if eigen:
        return Path(eigen)
    if sys.platform == 'win32' and os.environ.get('LOCALAPPDATA') and not os.environ.get('CI'):
        return Path(os.environ['LOCALAPPDATA']) / 'Justdata' / 'M365Beheer-uitvoer'
    return HIER / 'uitvoer'

NAAM = 'Microsoft 365 beheer'
sys.path.insert(0, str(HIER / 'backend'))


def versie() -> str:
    tekst = (HIER / 'backend' / 'm365beheer' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r"__version__\s*=\s*'([^']+)'", tekst).group(1)


def stap(t: str) -> None:
    print(f'\n=== {t}', flush=True)


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, shell=sys.platform == 'win32' and cmd[0] in ('npm', 'npx'))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for blok in iter(lambda: f.read(1024 * 1024), b''):
            h.update(blok)
    return h.hexdigest()


def zip_map(bron: Path, doel: Path) -> None:
    """Zip met de map zelf als bovenste niveau (zo verwachten installer en updater het)."""
    with zipfile.ZipFile(doel, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(bron.rglob('*')):
            z.write(p, Path(bron.name) / p.relative_to(bron))


def iscc() -> Path | None:
    """Inno Setup-compiler (voor de Windows-installer). Niet gevonden: dan alleen de zip."""
    import os
    kandidaten = [os.environ.get('ISCC', ''), shutil.which('ISCC') or '',
                  os.path.expandvars(r'%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe'),
                  r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe', r'C:\Program Files\Inno Setup 6\ISCC.exe']
    return next((Path(k) for k in kandidaten if k and Path(k).is_file()), None)


def wix_map() -> Path | None:
    """WiX Toolset 3 (voor de MSI). Niet gevonden: dan geen MSI."""
    import os
    kandidaten = [os.environ.get('WIX', ''), os.path.expandvars(r'%LOCALAPPDATA%\Programs\WiX314'),
                  r'C:\Program Files (x86)\WiX Toolset v3.14\bin', r'C:\Program Files (x86)\WiX Toolset v3.11\bin']
    for k in kandidaten:
        for p in (Path(k), Path(k) / 'bin'):
            if k and (p / 'candle.exe').is_file():
                return p
    return None


def maak_msi(app_map: Path, uit: Path, v: str, werk: Path) -> Path | None:
    """MSI per gebruiker (voor Intune) met heat (alle bestanden), candle en light."""
    wix = wix_map()
    if not wix:
        print('LET OP: WiX Toolset niet gevonden, er is geen MSI gemaakt.')
        return None
    stap('MSI maken (voor Intune)')
    w = werk / 'msi'
    shutil.rmtree(w, ignore_errors=True)
    w.mkdir(parents=True)
    run([str(wix / 'heat.exe'), 'dir', str(app_map), '-nologo', '-cg', 'AppBestanden', '-dr', 'INSTALLFOLDER', '-srd', '-sreg',
         '-scom', '-gg', '-var', 'var.Bron', '-out', str(w / 'bestanden.wxs')], HIER)
    run([str(wix / 'candle.exe'), '-nologo', '-arch', 'x64', '-ext', 'WixUtilExtension', f'-dVersie={v}', f'-dBron={app_map}',
         f'-dIcoon={HIER / "assets" / "icoon.ico"}', '-out', str(w) + '\\', str(HIER / 'installer' / 'M365Beheer.wxs'),
         str(w / 'bestanden.wxs')], HIER)
    msi = uit / f'Microsoft-365-beheer-{v}.msi'
    msi.unlink(missing_ok=True)
    # Per-gebruiker-installatie in AppData: deze ICE-controles gaan uit van Program Files en zijn hier niet van toepassing
    run([str(wix / 'light.exe'), '-nologo', '-ext', 'WixUtilExtension', '-spdb', '-sice:ICE38', '-sice:ICE64', '-sice:ICE91',
         '-sice:ICE43', '-sice:ICE57', '-out', str(msi), str(w / 'M365Beheer.wixobj'), str(w / 'bestanden.wixobj')], HIER)
    return msi


def main() -> None:
    from m365beheer.updater import architectuur, kanaal
    v, plat, arch = versie(), kanaal(), architectuur()
    print(f'Microsoft 365 beheer {v} bouwen voor {plat} ({arch})')

    fe = HIER / 'frontend'
    stap('Frontend bouwen (React)')
    if not (fe / 'node_modules').is_dir():
        run(['npm', 'ci', '--no-audit', '--no-fund'], fe)
    run(['npm', 'run', 'build'], fe)

    stap('Python-app bouwen (PyInstaller)')
    # Bouwen buiten OneDrive: sneller, en OneDrive kan geen bestanden vergrendelen tijdens het bouwen
    werk = Path(tempfile.gettempdir()) / 'm365beheer-bouw'
    dist = werk / 'dist'
    shutil.rmtree(dist, ignore_errors=True)
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--log-level', 'WARN',
         '--workpath', str(werk / 'build'), '--distpath', str(dist), 'M365Beheer.spec'], HIER)

    stap('Release-bestand maken')
    uit = uitvoer_map() / 'release' / plat
    uit.mkdir(parents=True, exist_ok=True)
    basis = f'Microsoft-365-beheer-{v}-{plat}-{arch}'
    zipnaam = uit / f'{basis}.zip'
    zipnaam.unlink(missing_ok=True)
    if plat == 'mac':
        app = dist / f'{NAAM}.app'
        # ditto behoudt rechten, symlinks en de ad-hoc handtekening van PyInstaller
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(zipnaam)], check=True)
    else:
        zip_map(dist / NAAM, zipnaam)
    info = {'version': v, 'platform': plat, 'arch': arch, 'file': zipnaam.name, 'sha256': sha256(zipnaam),
            'size': zipnaam.stat().st_size, 'built': datetime.now().strftime('%Y-%m-%d %H:%M')}
    if plat == 'mac':
        # DMG om te dubbelklikken: de app en een snelkoppeling naar Programma's, zodat je hem er zo naartoe sleept
        stap('DMG maken')
        staging = werk / 'dmg'
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        subprocess.run(['ditto', str(dist / f'{NAAM}.app'), str(staging / f'{NAAM}.app')], check=True)
        (staging / 'Programma\'s').symlink_to('/Applications')
        dmg = uit / f'Microsoft-365-beheer-{v}-mac-{arch}.dmg'
        dmg.unlink(missing_ok=True)
        subprocess.run(['hdiutil', 'create', '-volname', NAAM, '-srcfolder', str(staging), '-ov', '-format', 'UDZO', str(dmg)], check=True)
        info['dmg'] = {'file': dmg.name, 'sha256': sha256(dmg), 'size': dmg.stat().st_size}
    if plat == 'windows':
        compiler = iscc()
        if compiler:
            stap('Windows-installer maken (Setup.exe)')
            for oud in uit.glob(f'Microsoft-365-beheer-{v}-Setup.exe'):
                oud.unlink()
            run([str(compiler), '/Q', f'/DVersie={v}', f'/DBron={dist / NAAM}', f'/O{uit}', str(HIER / 'installer' / 'M365Beheer.iss')], HIER)
            setup = uit / f'Microsoft-365-beheer-{v}-Setup.exe'
            info['setup'] = {'file': setup.name, 'sha256': sha256(setup), 'size': setup.stat().st_size}
        else:
            print('LET OP: Inno Setup niet gevonden, er is geen Setup.exe gemaakt (alleen de zip).')
        msi = maak_msi(dist / NAAM, uit, v, werk)
        if msi:
            info['msi'] = {'file': msi.name, 'sha256': sha256(msi), 'size': msi.stat().st_size}
    (uit / f'{basis}.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    stap(f'Klaar: {zipnaam} ({info["size"] / 1048576:.1f} MB)')
    print('Online zetten: python release.py publiceren   (alleen als het online mag)')


if __name__ == '__main__':
    main()
