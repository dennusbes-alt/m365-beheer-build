"""Updates: bij het opstarten controleren of er een nieuwe versie klaarstaat, en die installeren.

- Windows en macOS hebben elk een eigen kanaal: <UPDATE_BASIS>/windows/latest.json en /mac/latest.json.
- Is de server niet bereikbaar (geen internet, firewall, Cloudflare-IP-beperking), dan gaat de app gewoon door.
- Een download wordt gecontroleerd met SHA-256 voordat er iets vervangen wordt.
- Installeren gebeurt na het afsluiten door een klein hulpscript, dat daarna de nieuwe versie start.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

from . import UPDATE_BASIS as _BASIS
from . import __version__

UPDATE_BASIS = os.environ.get('M365_UPDATE_BASIS', _BASIS).rstrip('/')   # alleen voor testen te overschrijven
from .context import Ctx, api

log = logging.getLogger('m365beheer')
APPNAAM = 'Microsoft 365 beheer'


def kanaal() -> str:
    return 'mac' if sys.platform == 'darwin' else 'windows'


def architectuur() -> str:
    m = platform.machine().lower()
    if sys.platform == 'darwin':
        return 'arm64' if m in ('arm64', 'aarch64') else 'x86_64'
    return 'arm64' if m in ('arm64', 'aarch64') else 'x64'


def versie_tuple(v: str) -> tuple[int, ...]:
    uit = []
    for deel in str(v).lstrip('vV').split('.'):
        num = ''.join(ch for ch in deel if ch.isdigit())
        uit.append(int(num) if num else 0)
    return tuple(uit + [0] * (3 - len(uit)))


def geinstalleerde_map() -> Path | None:
    """Map (Windows) of .app (Mac) van de draaiende, gecompileerde app. None tijdens ontwikkelen."""
    if not getattr(sys, 'frozen', False):
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == 'darwin':
        for p in exe.parents:
            if p.suffix == '.app':
                return p
        return None
    return exe.parent


class Updater:
    def __init__(self) -> None:
        self.klaar = threading.Event()
        self.resultaat: dict = {'current': __version__, 'available': False}
        self.stoppen = None  # wordt door main gezet: sluit de app af

    def start(self) -> None:
        threading.Thread(target=self._controleer, daemon=True, name='update').start()

    def _controleer(self) -> None:
        url = f'{UPDATE_BASIS}/{kanaal()}/latest.json'
        try:
            r = requests.get(url, params={'t': int(time.time())}, timeout=(2.5, 4),
                             headers={'User-Agent': f'M365Beheer/{__version__} ({kanaal()}; {architectuur()})', 'Cache-Control': 'no-cache'})
            r.raise_for_status()
            m = r.json()
            nieuw = str(m.get('version') or '')
            bestanden = m.get('files') or {}
            arch = architectuur()
            # Apple Silicon kan ook de Intel-versie draaien (Rosetta) als er geen arm64-build is
            bestand = bestanden.get(arch) or (bestanden.get('x86_64') if arch == 'arm64' else None)
            beschikbaar = bool(nieuw and bestand and versie_tuple(nieuw) > versie_tuple(__version__))
            self.resultaat = {
                'current': __version__, 'latest': nieuw, 'available': beschikbaar,
                'required': bool(m.get('required')) and beschikbaar, 'notes': m.get('notes') or [], 'date': m.get('date') or '',
                'canInstall': beschikbaar and geinstalleerde_map() is not None,
                '_bestand': ({**bestand, 'url': urljoin(url, bestand.get('url', ''))} if bestand else None),
            }
            log.info('Updatecontrole: huidig %s, server %s', __version__, nieuw)
        except Exception as e:  # server onbereikbaar of geblokkeerd: gewoon doorgaan
            self.resultaat = {'current': __version__, 'available': False, 'offline': True}
            log.info('Updatecontrole niet gelukt (%s), app gaat gewoon door.', e.__class__.__name__)
        finally:
            self.klaar.set()

    def status(self, wacht: float = 6) -> dict:
        self.klaar.wait(wacht)
        return {k: v for k, v in self.resultaat.items() if not k.startswith('_')}

    def installeren(self) -> None:
        b = self.resultaat.get('_bestand')
        doel = geinstalleerde_map()
        if not self.resultaat.get('available') or not b:
            raise RuntimeError('Er is geen update beschikbaar.')
        if not doel:
            raise RuntimeError('Automatisch bijwerken kan alleen in de geïnstalleerde app. Gebruik het installatiebestand.')
        if not os.access(doel.parent, os.W_OK):
            raise RuntimeError(f'Geen schrijfrechten op {doel.parent}. Installeer opnieuw met het installatiebestand.')
        tmp = Path(tempfile.mkdtemp(prefix='m365beheer-update-'))
        zip_ = tmp / 'update.zip'
        h = hashlib.sha256()
        with requests.get(b['url'], stream=True, timeout=(5, 60)) as r:
            r.raise_for_status()
            with open(zip_, 'wb') as f:
                for blok in r.iter_content(1024 * 256):
                    f.write(blok)
                    h.update(blok)
        if b.get('sha256') and h.hexdigest().lower() != str(b['sha256']).lower():
            raise RuntimeError('De download is beschadigd (controlegetal klopt niet). Probeer het later opnieuw.')
        log.info('Update %s gedownload, installeren na afsluiten.', self.resultaat.get('latest'))
        if sys.platform == 'darwin':
            self._mac(zip_, doel, tmp)
        else:
            self._windows(zip_, doel, tmp, str(self.resultaat.get('latest') or ''))
        if self.stoppen:
            threading.Timer(1.0, self.stoppen).start()

    @staticmethod
    def _windows(zip_: Path, doel: Path, tmp: Path, versie: str = '') -> None:
        q = lambda p: str(p).replace("'", "''")  # noqa: E731  (PowerShell-tekst tussen enkele aanhalingstekens)
        t, z, d, e = q(tmp), q(zip_), q(doel), q(doel / f'{APPNAAM}.exe')
        script = tmp / 'bijwerken.ps1'
        script.write_text(f'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {{ Start-Transcript -Path (Join-Path $env:TEMP 'm365beheer-update-log.txt') -Force | Out-Null }} catch {{ }}
try {{ Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{ }}
Start-Sleep -Milliseconds 500
$uit = Join-Path '{t}' 'nieuw'
New-Item -ItemType Directory -Force -Path $uit | Out-Null
$tar = Join-Path $env:SystemRoot 'System32\\tar.exe'
if (Test-Path $tar) {{ & $tar -xf '{z}' -C $uit }}
if (-not (Get-ChildItem -LiteralPath $uit -Directory)) {{ Expand-Archive -LiteralPath '{z}' -DestinationPath $uit -Force }}
$bron = Get-ChildItem -LiteralPath $uit -Directory | Select-Object -First 1
robocopy $bron.FullName '{d}' /MIR /XF unins*.* /R:10 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
foreach ($k in 'JustdataM365Beheer', 'JustdataM365Beheer_is1') {{
    try {{ Set-ItemProperty -Path ('HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + $k) -Name DisplayVersion -Value '{q(versie)}' -ErrorAction Stop }} catch {{ }}
}}
Start-Process -FilePath '{e}'
Remove-Item -LiteralPath '{t}' -Recurse -Force -ErrorAction SilentlyContinue
''', encoding='utf-8-sig')
        cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', str(script)]
        # Los van de app starten, zodat het script blijft draaien als de app afsluit.
        # Let op: géén DETACHED_PROCESS gebruiken; PowerShell stopt dan direct zonder iets te doen (geen console).
        # CREATE_NO_WINDOW geeft een verborgen console. BREAKAWAY_FROM_JOB: ook los van een eventuele taakgroep.
        basis = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        kw = dict(close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            subprocess.Popen(cmd, creationflags=basis | 0x01000000, **kw)
        except OSError:   # taakgroep staat losbreken niet toe
            subprocess.Popen(cmd, creationflags=basis, **kw)

    @staticmethod
    def _mac(zip_: Path, app: Path, tmp: Path) -> None:
        script = tmp / 'bijwerken.sh'
        script.write_text(f'''#!/bin/bash
while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done
set -e
ditto -x -k "{zip_}" "{tmp}/nieuw"
NIEUW=$(find "{tmp}/nieuw" -maxdepth 1 -name "*.app" | head -1)
rm -rf "{app}.oud"
mv "{app}" "{app}.oud"
mv "$NIEUW" "{app}"
rm -rf "{app}.oud"
xattr -dr com.apple.quarantine "{app}" 2>/dev/null || true
open "{app}"
rm -rf "{tmp}"
''', encoding='utf-8')
        script.chmod(0o755)
        subprocess.Popen(['/bin/bash', str(script)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


UPDATER = Updater()


@api('update.status')
def status(c: Ctx, b: dict) -> dict:
    return UPDATER.status()


@api('update.install')
def installeer(c: Ctx, b: dict) -> dict:
    UPDATER.installeren()
    return {'restarting': True}


DOWNLOADPAGINA = UPDATE_BASIS.rsplit('/', 1)[0] + '/download/'


@api('update.download')
def download(c: Ctx, b: dict) -> dict:
    """Downloadpagina openen in de standaardbrowser (niet in het app-venster)."""
    import webbrowser
    webbrowser.open(DOWNLOADPAGINA)
    return {}
