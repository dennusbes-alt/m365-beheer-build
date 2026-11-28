"""Startpunt: Microsoft 365 beheer (Justdata)."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import (__version__, h_administratie, h_afwezig, h_apparaten, h_compliance, h_readiness, h_retentie, h_rapport, h_backup, h_autotask, h_dmarc, h_intune, h_spmappen, h_ca, h_management, h_klantrapport, h_itglue, h_servicedesk, h_sdniveau, h_facturatie, h_timesheet, h_sales, h_projecten, h_rmm, h_voorraad, h_contracten, h_servicecall, h_prijzen, h_advies, h_auto_blokken, rechten, h_authenticatie, h_bedreiging, h_exchange, h_gebruikers,  # noqa: F401  (registreert de API)
               h_domeinen, h_gebruikers_bulk, h_groepen, h_automatisering, h_health, h_huisstijl, h_migratie, h_sessie, h_sharepoint, klussen, voorkeuren)
from .server import App, bewaak_browser
from .updater import UPDATER

TITEL = 'Microsoft 365 beheer'


def bron_pad() -> Path:
    """Map met de gebouwde interface (ook binnen een PyInstaller-bundel)."""
    basis = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent.parent))
    for kandidaat in (basis / 'web', basis / 'frontend' / 'dist'):
        if (kandidaat / 'index.html').is_file():
            return kandidaat
    raise SystemExit('De interface is niet gevonden. Bouw eerst de frontend (npm run build).')


def logging_instellen() -> None:
    """Logboek in de gebruikersmap (of anders de tijdelijke map). Bevat nooit tokens of wachtwoorden."""
    lg = logging.getLogger('m365beheer')
    lg.setLevel(logging.INFO)
    logging.getLogger('msal').setLevel(logging.WARNING)
    for map_ in (Path(os.path.expanduser('~')), Path(tempfile.gettempdir())):
        try:
            h = RotatingFileHandler(map_ / 'm365-beheer-app-log.txt', maxBytes=1_000_000, backupCount=1, encoding='utf-8')
        except OSError:
            continue
        h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        lg.addHandler(h)
        return
    lg.addHandler(logging.NullHandler())


def venster_stand() -> dict:
    """Laatst gebruikte venstergrootte en -positie (alleen weergave-instellingen, geen accountgegevens)."""
    from . import lokaal
    st = {'w': 1440, 'h': 920}
    try:
        d = lokaal.lees('venster.json', {}) or {}
        if int(d.get('w', 0)) >= 1024 and int(d.get('h', 0)) >= 680:
            st.update(w=int(d['w']), h=int(d['h']))
        # Positie alleen als die zinnig is (bijv. niet op een inmiddels losgekoppeld scherm ver buiten beeld)
        if d.get('x') is not None and -200 < int(d['x']) < 6000 and -50 < int(d.get('y', 0)) < 4000:
            st.update(x=int(d['x']), y=int(d['y']))
        st['max'] = bool(d.get('max'))
    except (TypeError, ValueError):
        pass
    return st


_venster_timer = None


def venster_stand_bewaren(st: dict) -> None:
    """Bewaren met een korte vertraging (tijdens slepen komen er veel gebeurtenissen)."""
    import threading
    from . import lokaal
    global _venster_timer
    if _venster_timer:
        _venster_timer.cancel()
    _venster_timer = threading.Timer(0.8, lambda: lokaal.schrijf('venster.json', dict(st)))
    _venster_timer.daemon = True
    _venster_timer.start()


def snelkoppelingen_herstellen() -> None:
    """Windows: snelkoppelingen naar deze app die nog argumenten van de oude PowerShell-versie bevatten (Start.vbs)
    op de achtergrond opschonen. Zo werkt starten vanuit het Startmenu en bureaublad weer zoals het hoort."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    import subprocess
    import threading
    exe = str(Path(sys.executable).resolve()).replace("'", "''")
    ps = ("$sh = New-Object -ComObject WScript.Shell; "
          "foreach ($m in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { "
          "Get-ChildItem -LiteralPath $m -Filter '*.lnk' -ErrorAction SilentlyContinue | ForEach-Object { "
          "$l = $sh.CreateShortcut($_.FullName); "
          f"if ($l.TargetPath -eq '{exe}' -and $l.Arguments) {{ $l.Arguments = ''; $l.Save() }} }} }}")

    def run() -> None:
        try:
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps], timeout=60,
                           capture_output=True, creationflags=0x08000000)   # CREATE_NO_WINDOW
        except Exception as e:  # noqa: BLE001 - nooit fataal
            logging.getLogger('m365beheer').info('Snelkoppelingen controleren niet gelukt: %s', e)
    threading.Thread(target=run, daemon=True, name='snelkoppelingen').start()


def main() -> None:
    ap = argparse.ArgumentParser(description=TITEL)
    ap.add_argument('--browser', action='store_true', help='Open in de standaardbrowser in plaats van een eigen venster')
    ap.add_argument('--dev', action='store_true', help='Ontwikkelmodus: vaste poort 8765, geen venster')
    ap.add_argument('--mock', action='store_true', help='Testgegevens gebruiken (geen Microsoft-verbinding)')
    # Onbekende argumenten negeren: een oude snelkoppeling kan nog argumenten meegeven, en dan mag de app niet stilletjes stoppen
    args, onbekend = ap.parse_known_args()

    logging_instellen()
    if onbekend:
        logging.getLogger('m365beheer').info('Onbekende startargumenten genegeerd: %s', onbekend)
    snelkoppelingen_herstellen()
    # Updatecontrole meteen starten: loopt parallel aan het opstarten en blokkeert nooit
    if not os.environ.get('M365_GEEN_UPDATE'):
        UPDATER.start()
    else:
        UPDATER.klaar.set()
    if args.mock or os.environ.get('M365_MOCK'):
        from . import mock  # noqa: F401  (vervangt de API door testgegevens)

    app = App(bron_pad(), token=os.environ.get('M365_TOKEN') if args.dev else None)
    url = app.start(8765 if args.dev else 0)
    logging.getLogger('m365beheer').info('Versie %s gestart op poort %s', __version__, app.port)
    UPDATER.stoppen = app.afsluiten

    if args.dev:
        print(url, flush=True)
        bewaak_browser(app) if not os.environ.get('M365_GEEN_STOP') else app.stop.wait()
        return

    if not args.browser:
        try:
            # Snelheid web remote (Datto) in het meekijkvenster: GPU-rendering altijd aan (ook als de driver op de
            # blokkadelijst van Chromium staat) en geen afremmen van vensters die niet vooraan staan. WebView2 leest dit
            # bij het starten; de opties van pywebview zelf staan er ook in (mocht de omgevingsvariabele voorgaan).
            os.environ.setdefault('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', ' '.join([
                '--disable-features=ElasticOverscroll,CalculateNativeWinOcclusion', '--allow-file-access-from-files',
                '--enable-gpu-rasterization', '--enable-zero-copy', '--ignore-gpu-blocklist', '--enable-accelerated-video-decode',
                '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows']))
            import webview
            webview.settings['ALLOW_DOWNLOADS'] = True
            # Venster zoals de gebruiker het de vorige keer had (grootte, positie, gemaximaliseerd)
            st = venster_stand()
            venster = webview.create_window(TITEL, url, width=st['w'], height=st['h'], x=st.get('x'), y=st.get('y'),
                                            maximized=bool(st.get('max')), min_size=(1024, 680), background_color='#f2f6f9')
            stand = {'min': False, 'max': bool(st.get('max'))}

            def bewaar(**kw) -> None:
                st.update(kw)
                venster_stand_bewaren(st)
            venster.events.maximized += lambda: (stand.update(max=True, min=False), bewaar(max=True))
            venster.events.minimized += lambda: stand.update(min=True)
            venster.events.restored += lambda: (stand.update(min=False, max=False), bewaar(max=False))
            venster.events.resized += lambda w, h: (not stand['max'] and not stand['min']) and bewaar(w=int(w), h=int(h))
            # Bij maximaliseren meldt Windows kort een positie als -7,-7: die is geen echte vensterpositie
            venster.events.moved += lambda x, y: (not stand['max'] and not stand['min'] and not (x < 0 and y < 0)) and bewaar(x=int(x), y=int(y))

            def naar_voren() -> None:
                # Alleen naar voren halen; grootte en (gemaximaliseerde) stand blijven zoals de gebruiker ze heeft ingesteld
                try:
                    if stand['min']:
                        venster.restore()
                        if stand['max']:
                            venster.maximize()
                    venster.on_top = True
                    venster.on_top = False
                except Exception:
                    pass
            app.naar_voren = naar_voren

            def meekijkvenster(url: str, titel: str, bij_sluiten):
                # Web remote (Datto RMM) in een eigen venster: sluiten = sessie klaar (tijd wordt geboekt).
                # Datto vraagt eerst om in te loggen en stuurt daarna naar de algemene startpagina: dan zelf terug naar
                # web remote van dit apparaat (tot de web remote-pagina één keer geladen is, max. 4 keer).
                import re as _re
                from urllib.parse import urlsplit
                w = webview.create_window(titel, url, width=1366, height=860, min_size=(900, 600), background_color='#ffffff')
                doel = urlsplit(url)
                stand = {'ok': False, 'n': 0}

                def geladen() -> None:
                    try:
                        nu = urlsplit(w.get_current_url() or '')
                    except Exception:
                        return
                    if nu.netloc == doel.netloc and nu.path.rstrip('/') == doel.path.rstrip('/'):
                        stand['ok'] = True   # web remote van dit apparaat is open
                        return
                    if stand['ok'] or stand['n'] >= 4 or not nu.netloc:
                        return
                    if _re.search(r'login|signin|sso|oauth|auth|idp|microsoftonline|okta|mfa|2fa|verify', nu.netloc + nu.path, _re.I):
                        return   # nog aan het inloggen
                    if nu.netloc.endswith(('centrastage.net', 'datto.com', 'rmm.datto.com')):
                        stand['n'] += 1
                        logging.getLogger('m365beheer').info('Meekijken: na inloggen terug naar web remote (%s)', nu.netloc)
                        w.load_url(url)
                w.events.loaded += geladen
                w.events.closed += lambda: bij_sluiten()
                return w
            from . import h_rmm
            h_rmm.VENSTER = meekijkvenster

            def stoppen() -> None:   # na het starten van een update: afmelden en venster sluiten
                app.afsluiten()
                try:
                    venster.destroy()
                except Exception:
                    os._exit(0)
            UPDATER.stoppen = stoppen
            # Keuze Justdata (v2.40): de Datto RMM-login in het meekijkvenster blijft bewaard, zodat niemand steeds opnieuw
            # inlogt. Daarvoor een vast webview-profiel buiten OneDrive. Microsoft-tokens blijven alleen in het geheugen
            # van de Python-kant; in het profiel staan alleen websitecookies (Datto) en weergave-instellingen.
            if sys.platform == 'win32':
                profiel = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Justdata' / 'M365Beheer-webview'
            else:
                from . import lokaal
                profiel = lokaal.app_map() / 'webview'
            try:
                profiel.mkdir(parents=True, exist_ok=True)
                webview.start(private_mode=False, storage_path=str(profiel))
            except TypeError:   # oudere pywebview zonder storage_path
                webview.start(private_mode=False)
            app.afsluiten()      # venster dicht = afmelden
            return
        except Exception as e:  # geen WebView beschikbaar: dan de browser
            logging.getLogger('m365beheer').warning('Eigen venster niet beschikbaar (%s), browser wordt gebruikt.', e)

    webbrowser.open(url)
    bewaak_browser(app)


if __name__ == '__main__':
    main()
