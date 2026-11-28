"""Releases beheren op de updateserver (m365admin.justsecure.nl) via SSH.

    python release.py status                       wat staat er online, wat ligt er lokaal klaar
    python release.py publiceren [opties]          zet de gebouwde release(s) online

Opties bij publiceren:
    --platform windows|mac|alle   (standaard: alles wat in de uitvoermap (zie uitvoer_map) klaarligt voor de huidige versie)
    --notities "punt 1; punt 2"   wat is er nieuw (zichtbaar in de updatemelding)
    --verplicht                   gebruikers moeten bijwerken voordat ze verder kunnen
    --ja                          niet om bevestiging vragen

De SSH-gegevens komen uit ../.env (SSH_HOST, SSH_USER, SSH_PORT, SSH_KEY). Dat bestand staat niet in git.
Volgorde bij publiceren: eerst het zip-bestand, daarna pas latest.json (zo ziet niemand een half geüploade versie).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import date
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

DOMEIN = 'm365admin.justsecure.nl'
WEBROOT = f'htdocs/{DOMEIN}'        # relatief aan de thuismap van de SSH-gebruiker
INSTALLER = HIER / 'installer'
INSTALLER_BESTANDEN = ['index.html', 'install-windows.ps1', 'install-mac.sh',
                       'Installeer-Microsoft-365-beheer.cmd', 'Installeer-Microsoft-365-beheer.command',
                       'mac-bouwen.md']


def versie() -> str:
    tekst = (HIER / 'backend' / 'm365beheer' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r"__version__\s*=\s*'([^']+)'", tekst).group(1)


def env() -> dict[str, str]:
    pad = HIER.parent / '.env'
    if not pad.is_file():
        sys.exit(f'Geen .env gevonden op {pad}')
    d = {}
    for regel in pad.read_text(encoding='utf-8').splitlines():
        regel = regel.strip()
        if regel and not regel.startswith('#') and '=' in regel:
            k, v = regel.split('=', 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    for k in ('SSH_HOST', 'SSH_USER'):
        if not d.get(k):
            sys.exit(f'{k} ontbreekt in .env')
    return d


class Server:
    def __init__(self) -> None:
        e = env()
        self.doel = f"{e['SSH_USER']}@{e['SSH_HOST']}"
        self.opties = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-p', e.get('SSH_PORT') or '22']
        if e.get('SSH_KEY'):
            self.opties += ['-i', os.path.expanduser(e['SSH_KEY'])]
        self.ssh_bin = shutil.which('ssh') or sys.exit('ssh niet gevonden')
        self.scp_bin = shutil.which('scp') or sys.exit('scp niet gevonden')

    def ssh(self, cmd: str, check: bool = True) -> str:
        r = subprocess.run([self.ssh_bin, *self.opties, self.doel, cmd], capture_output=True, text=True)
        if check and r.returncode != 0:
            sys.exit(f'SSH-fout: {r.stderr.strip() or r.stdout.strip()}')
        return r.stdout

    def upload(self, lokaal: Path, remote: str) -> None:
        opties = ['-P' if o == '-p' else o for o in self.opties]
        r = subprocess.run([self.scp_bin, '-q', *opties, str(lokaal), f'{self.doel}:{remote}'], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f'Upload mislukt ({lokaal.name}): {r.stderr.strip()}')

    def lees_json(self, remote: str) -> dict:
        try:
            return json.loads(self.ssh(f'cat {shlex.quote(remote)} 2>/dev/null', check=False) or '{}')
        except ValueError:
            return {}

    def controleer(self, pad: str) -> str:
        """Via de server zelf ophalen (Cloudflare kan ons IP blokkeren)."""
        return self.ssh(f"curl -sk -o /dev/null -w '%{{http_code}}' --resolve {DOMEIN}:443:127.0.0.1 "
                        f"https://{DOMEIN}/{pad}?t=$(date +%s)", check=False).strip()


def klaarliggend(v: str, platform: str | None) -> list[dict]:
    uit = []
    for p in sorted((uitvoer_map() / 'release').glob('*/*.json')):
        info = json.loads(p.read_text(encoding='utf-8'))
        if info.get('version') == v and (platform in (None, 'alle') or info.get('platform') == platform):
            info['_zip'] = p.with_suffix('.zip')
            if info['_zip'].is_file():
                uit.append(info)
    return uit


def status(args) -> None:
    s = Server()
    print(f'Lokale versie: {versie()}')
    for plat in ('windows', 'mac'):
        m = s.lees_json(f'{WEBROOT}/updates/{plat}/latest.json')
        if m:
            archs = ', '.join(m.get('files', {}))
            print(f'Online {plat:8}: {m.get("version")} ({m.get("date", "")}) [{archs}]{" VERPLICHT" if m.get("required") else ""}')
        else:
            print(f'Online {plat:8}: nog niets')
    klaar = klaarliggend(versie(), None)
    print('Klaar om te publiceren: ' + (', '.join(f"{i['platform']}-{i['arch']}" for i in klaar) or 'niets (eerst bouwen)'))


def publiceren(args) -> None:
    v = versie()
    klaar = klaarliggend(v, args.platform)
    if not klaar:
        sys.exit(f'Geen gebouwde release voor versie {v} gevonden in de uitvoermap (zie uitvoer_map). Draai eerst bouwen.py.')
    notities = [n.strip() for n in (args.notities or '').split(';') if n.strip()]
    print(f'Publiceren van versie {v} naar https://{DOMEIN}:')
    for i in klaar:
        print(f"  - {i['platform']}/{i['arch']}: {i['file']} ({i['size'] / 1048576:.1f} MB)")
    if notities:
        print('  Nieuw: ' + '; '.join(notities))
    if args.verplicht:
        print('  LET OP: verplichte update')
    if not args.ja and input('Typ ONLINE om door te gaan: ').strip() != 'ONLINE':
        sys.exit('Afgebroken.')

    s = Server()
    s.ssh(f'mkdir -p {WEBROOT}/updates/windows {WEBROOT}/updates/mac {WEBROOT}/download')
    # 1. Zip-bestanden
    for i in klaar:
        remote = f"{WEBROOT}/updates/{i['platform']}/{i['file']}"
        print(f"Uploaden: {i['file']}...")
        s.upload(i['_zip'], remote + '.tmp')
        s.ssh(f'mv -f {shlex.quote(remote + ".tmp")} {shlex.quote(remote)} && chmod 664 {shlex.quote(remote)}')
        uit = s.ssh(f'sha256sum {shlex.quote(remote)}').split()[0]
        if uit != i['sha256']:
            sys.exit(f"Controlegetal na upload klopt niet voor {i['file']}!")
    # 2. latest.json per platform (andere architecturen van dezelfde versie blijven staan)
    for plat in sorted({i['platform'] for i in klaar}):
        pad = f'{WEBROOT}/updates/{plat}/latest.json'
        oud = s.lees_json(pad)
        files = oud.get('files', {}) if oud.get('version') == v else {}
        for i in (x for x in klaar if x['platform'] == plat):
            files[i['arch']] = {'url': i['file'], 'sha256': i['sha256'], 'size': i['size']}
        m = {'version': v, 'date': date.today().isoformat(), 'required': bool(args.verplicht),
             'notes': notities or oud.get('notes', []) if oud.get('version') == v else notities, 'files': files}
        for soort in ('setup', 'msi', 'dmg'):   # downloadpagina linkt naar het bestand met versienummer (de vaste naam kan in de Cloudflare-cache blijven hangen)
            st = next((x[soort] for x in klaar if x['platform'] == plat and x.get(soort)), None) or (oud.get(soort) if oud.get('version') == v else None)
            if st:
                m[soort] = {'file': st['file'], 'sha256': st['sha256'], 'size': st['size']}
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(m, f, indent=1, ensure_ascii=False)
        s.upload(Path(f.name), pad + '.tmp')
        os.unlink(f.name)
        s.ssh(f'mv -f {pad}.tmp {pad} && chmod 664 {pad}')
        print(f'latest.json voor {plat} bijgewerkt naar {v}.')
    # 2b. Windows-installers (Setup.exe en MSI voor Intune): naam met versie en een vaste naam die altijd de nieuwste is
    for i in klaar:
        for soort, vaste_naam in (('setup', 'Microsoft-365-beheer-Setup.exe'), ('msi', 'Microsoft-365-beheer.msi'), ('dmg', 'Microsoft-365-beheer.dmg')):
            st = i.get(soort)
            if not st or not (i['_zip'].parent / st['file']).is_file():
                continue
            lokaal = i['_zip'].parent / st['file']
            print(f"Uploaden: {st['file']}...")
            doel = f"{WEBROOT}/download/{st['file']}"
            s.upload(lokaal, doel + '.tmp')
            s.ssh(f'mv -f {shlex.quote(doel + ".tmp")} {shlex.quote(doel)}')
            if s.ssh(f'sha256sum {shlex.quote(doel)}').split()[0] != st['sha256']:
                sys.exit(f"Controlegetal na upload klopt niet voor {st['file']}!")
            vast = f'{WEBROOT}/download/{vaste_naam}'
            s.ssh(f'cp -f {shlex.quote(doel)} {shlex.quote(vast + ".tmp")} && mv -f {shlex.quote(vast + ".tmp")} {shlex.quote(vast)}')
            print(f'{st["file"]} gepubliceerd (ook als download/{vaste_naam}).')
    # 3. Installers en downloadpagina
    for naam in INSTALLER_BESTANDEN:
        s.upload(INSTALLER / naam, f'{WEBROOT}/download/{naam}')
    s.upload(HIER / 'frontend' / 'src' / 'assets' / 'logo.png', f'{WEBROOT}/download/logo.png')
    s.ssh(f'chmod 775 {WEBROOT}/updates {WEBROOT}/updates/* {WEBROOT}/download && chmod 664 {WEBROOT}/download/*')
    print('Installers en downloadpagina bijgewerkt.')
    # 4. Controle via de webserver
    for pad in ['download/', *(f"updates/{p}/latest.json" for p in sorted({i['platform'] for i in klaar}))]:
        print(f'  https://{DOMEIN}/{pad} -> HTTP {s.controleer(pad)}')
    # 5. Git-tag
    # (git kan op deze pc vastlopen: dan niet blijven wachten; de release staat al online, de tag kan later)
    try:
        if subprocess.run(['git', 'rev-parse', '-q', '--verify', f'refs/tags/v{v}'], cwd=HIER, capture_output=True, timeout=30).returncode != 0:
            subprocess.run(['git', 'tag', '-a', f'v{v}', '-m', f'Release {v}'], cwd=HIER, check=False, timeout=30)
            print(f'Git-tag v{v} gemaakt.')
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f'Git-tag v{v} niet gemaakt ({type(e).__name__}); maak die later handmatig.')
    print(f'\nKlaar. Downloadpagina: https://{DOMEIN}/download/')


def main() -> None:
    ap = argparse.ArgumentParser(description='Releases van Microsoft 365 beheer')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status').set_defaults(fn=status)
    p = sub.add_parser('publiceren')
    p.add_argument('--platform', choices=['windows', 'mac', 'alle'])
    p.add_argument('--notities', default='')
    p.add_argument('--verplicht', action='store_true')
    p.add_argument('--ja', action='store_true')
    p.set_defaults(fn=publiceren)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
