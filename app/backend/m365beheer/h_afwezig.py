"""Automatisch antwoord (afwezigheid) per gebruiker of postvak.

Zoals Get/Set-MailboxAutoReplyConfiguration: aan, uit of gepland (van-tot), met een bericht voor collega's en een voor
externen (iedereen, alleen bekende afzenders of niemand). Vereist bij de klant de rol Exchange Administrator.
"""
from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .clients import ApiFout
from .context import Ctx, api


def _tekst(h: str) -> str:
    """HTML van Exchange naar leesbare tekst (voor het tekstvak)."""
    t = re.sub(r'(?i)<br\s*/?>|</p>|</div>', '\n', h or '')
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def _html(t: str) -> str:
    """Tekst uit het tekstvak naar eenvoudige HTML (regeleinden blijven staan)."""
    return '<html><body>' + '<br>'.join(html.escape(r) for r in (t or '').splitlines()) + '</body></html>' if t else ''


def _iso(v) -> str:
    s = str(v or '')
    m = re.search(r'/Date\((\d+)', s)   # Exchange geeft soms /Date(1700000000000)/
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).isoformat()
    return s


def _config(r: dict) -> dict:
    return {'state': str(r.get('AutoReplyState') or 'Disabled'), 'start': _iso(r.get('StartTime')), 'end': _iso(r.get('EndTime')),
            'internal': _tekst(str(r.get('InternalMessage') or '')), 'external': _tekst(str(r.get('ExternalMessage') or '')),
            'audience': str(r.get('ExternalAudience') or 'All')}


@api('ar.get')
def ar_get(c: Ctx, b: dict) -> dict:
    r = c.x.een('Get-MailboxAutoReplyConfiguration', Identity=str(b['mailbox'])) or {}
    return _config(r)


@api('ar.set')
def ar_set(c: Ctx, b: dict) -> dict:
    mb = str(b['mailbox'])
    staat = {'aan': 'Enabled', 'uit': 'Disabled', 'gepland': 'Scheduled'}.get(b.get('state'), b.get('state') or 'Disabled')
    if staat not in ('Enabled', 'Disabled', 'Scheduled'):
        raise ApiFout('Onbekende stand.')
    p: dict = {'Identity': mb, 'AutoReplyState': staat}
    if staat != 'Disabled':
        intern = str(b.get('internal') or '').strip()
        if not intern:
            raise ApiFout('Vul een bericht in.')
        extern = str(b.get('external') or '').strip() or intern
        p.update(InternalMessage=_html(intern), ExternalMessage=_html(extern),
                 ExternalAudience=b.get('audience') if b.get('audience') in ('None', 'Known', 'All') else 'All')
    if staat == 'Scheduled':
        if not b.get('start') or not b.get('end'):
            raise ApiFout('Kies een begin- en einddatum.')
        begin, eind = datetime.fromisoformat(str(b['start'])), datetime.fromisoformat(str(b['end']))
        if eind <= begin:
            raise ApiFout('De einddatum moet na de begindatum liggen.')
        # Lokale tijd van deze computer meegeven als UTC (Exchange rekent zelf om naar de tijdzone van het postvak)
        p.update(StartTime=begin.astimezone().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                 EndTime=eind.astimezone().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    c.x.run('Set-MailboxAutoReplyConfiguration', **p)
    c.L({'Enabled': f'Automatisch antwoord staat aan voor {mb}.', 'Disabled': f'Automatisch antwoord staat uit voor {mb}.',
         'Scheduled': f"Automatisch antwoord gepland voor {mb} ({str(b['start'])[:16].replace('T', ' ')} tot {str(b['end'])[:16].replace('T', ' ')})."}[staat])
    return {}


@api('ar.overzicht')
def ar_overzicht(c: Ctx, b: dict) -> dict:
    """Welke postvakken hebben nu een automatisch antwoord aan of gepland (alle postvakken nagelopen, 8 tegelijk)."""
    x = c.x
    pv = x.run('Get-Mailbox', ResultSize='Unlimited', RecipientTypeDetails=['UserMailbox', 'SharedMailbox'])

    def een(m: dict):
        adres = str(m.get('PrimarySmtpAddress') or '')
        try:
            r = x.een('Get-MailboxAutoReplyConfiguration', Identity=adres) or {}
        except ApiFout:
            return None
        if str(r.get('AutoReplyState')) in ('Enabled', 'Scheduled'):
            return {'mailbox': adres, 'name': str(m.get('DisplayName') or adres), 'shared': str(m.get('RecipientTypeDetails')) == 'SharedMailbox', **_config(r)}
        return None
    with ThreadPoolExecutor(max_workers=8) as ex:
        uit = [r for r in ex.map(een, pv) if r]
    uit.sort(key=lambda r: r['name'].lower())
    return {'active': uit, 'checked': len(pv)}


# ---------------------------------------------------------------- Doorsturen per postvak
@api('fwd.get')
def fwd_get(c: Ctx, b: dict) -> dict:
    x = c.x
    m = x.een('Get-Mailbox', Identity=str(b['mailbox'])) or {}
    smtp = re.sub(r'(?i)^smtp:', '', str(m.get('ForwardingSmtpAddress') or ''))
    intern = str(m.get('ForwardingAddress') or '')
    try:
        modus = str((x.een('Get-HostedOutboundSpamFilterPolicy', Identity='Default') or {}).get('AutoForwardingMode') or '')
    except ApiFout:
        modus = ''
    eigen = {d['id'].lower() for d in c.t.domeinen}
    return {'on': bool(smtp or intern), 'to': smtp or intern, 'keep': bool(m.get('DeliverToMailboxAndForward')),
            'external': bool(smtp) and smtp.rsplit('@', 1)[-1].lower() not in eigen, 'mode': modus, 'domains': sorted(eigen)}


@api('fwd.set')
def fwd_set(c: Ctx, b: dict) -> dict:
    from .clients import NULL
    mb = str(b['mailbox'])
    if not b.get('on'):
        c.x.run('Set-Mailbox', Identity=mb, ForwardingSmtpAddress=NULL, ForwardingAddress=NULL, DeliverToMailboxAndForward=False)
        c.L(f'Doorsturen uitgezet voor {mb}.')
        return {}
    naar = str(b.get('to') or '').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[A-Za-z]{2,}', naar):
        raise ApiFout('Vul een geldig e-mailadres in.')
    if naar.lower() == mb.lower():
        raise ApiFout('Een postvak kan niet naar zichzelf doorsturen.')
    c.x.run('Set-Mailbox', Identity=mb, ForwardingAddress=NULL, ForwardingSmtpAddress=f'smtp:{naar}', DeliverToMailboxAndForward=bool(b.get('keep', True)))
    c.L(f"Doorsturen aangezet voor {mb} naar {naar} ({'kopie blijft in het postvak' if b.get('keep', True) else 'zonder kopie in het postvak'}).")
    c.t.weg('compliance-gebruikers')
    return {}
