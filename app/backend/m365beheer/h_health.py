"""Servicestatus (Microsoft 365 Service health) en het Berichtencentrum, in begrijpelijke taal.

Graph: /admin/serviceAnnouncement/healthOverviews, /issues en /messages (zoals Get-MgServiceAnnouncementIssue).
Vereist de rechten ServiceHealth.Read.All en ServiceMessage.Read.All, en bij de klant een rol als Global Reader,
Service Support Administrator of Message Center Reader.

Microsoft schrijft de meldingen in het Engels. De app vertaalt alles wat vastligt (diensten, status, soort, categorie)
naar Nederlands en haalt uit de tekst de vaste onderdelen (wat merken gebruikers, huidige stand, volgende update),
zodat je in één oogopslag ziet wat er speelt. De originele tekst blijft beschikbaar.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from .clients import ApiFout, parallel
from .context import Ctx, api

SA = '/admin/serviceAnnouncement'
FOUT_ROL = ('Servicestatus is bij deze klant niet op te vragen. Nodig: in de GDAP-relatie een rol als Global Reader of '
            'Service Support Administrator. Is de app net bijgewerkt, open de klant dan opnieuw zodat de nieuwe rechten worden toegevoegd.')

STATUS = {
    'serviceOperational': ('Werkt normaal', 'g'), 'investigating': ('Wordt onderzocht', 'o'), 'restoringService': ('Wordt hersteld', 'o'),
    'verifyingService': ('Herstel wordt gecontroleerd', 'o'), 'serviceRestored': ('Hersteld', 'g'), 'postIncidentReviewPublished': ('Hersteld, analyse gepubliceerd', 'g'),
    'serviceDegradation': ('Verminderde werking', 'o'), 'serviceInterruption': ('Storing', 'r'), 'extendedRecovery': ('Herstel duurt langer', 'o'),
    'falsePositive': ('Vals alarm, geen storing', 'g'), 'investigationSuspended': ('Onderzoek stopgezet', 'mu'), 'resolved': ('Opgelost', 'g'),
    'mitigatedExternal': ('Opgelost (buiten Microsoft)', 'g'), 'mitigated': ('Verholpen', 'g'), 'resolvedExternal': ('Opgelost (buiten Microsoft)', 'g'),
    'confirmed': ('Bevestigd', 'o'), 'reported': ('Gemeld', 'o'),
}
SOORT = {'incident': ('Storing', 'Gebruikers merken er direct iets van.'), 'advisory': ('Melding', 'Beperkt of voor een deel van de gebruikers merkbaar.')}
CATEGORIE = {'planForChange': ('Wijziging gepland', 'o'), 'stayInformed': ('Ter info', 'mu'), 'preventOrFixIssue': ('Actie nodig', 'r')}
DIENST = {
    'Exchange Online': 'Exchange Online (e-mail en agenda)', 'Microsoft Teams': 'Teams', 'SharePoint Online': 'SharePoint',
    'OneDrive for Business': 'OneDrive', 'Microsoft 365 suite': 'Microsoft 365 (algemeen)', 'Microsoft Entra': 'Microsoft Entra ID (aanmelden)',
    'Microsoft Intune': 'Intune (apparaatbeheer)', 'Microsoft 365 apps': 'Office-apps (Word, Excel, Outlook)', 'Microsoft Defender XDR': 'Defender XDR (beveiliging)',
    'Microsoft Defender for Office 365': 'Defender voor Office 365 (e-mailbeveiliging)', 'Microsoft Defender for Endpoint': 'Defender voor Endpoint',
    'Planner': 'Planner', 'Microsoft Forms': 'Forms', 'Power BI': 'Power BI', 'Power Apps': 'Power Apps', 'Power Automate': 'Power Automate',
    'Microsoft Purview': 'Purview (compliance)', 'Windows Autopatch': 'Windows Autopatch', 'Mobile Device Management for Office 365': 'Basisbeheer van mobiele apparaten',
    'Microsoft Bookings': 'Bookings', 'Microsoft Copilot (Microsoft 365)': 'Copilot', 'Microsoft Viva': 'Viva', 'Sway': 'Sway', 'Project for the web': 'Project',
    'Microsoft Stream': 'Stream', 'Dynamics 365 Apps': 'Dynamics 365', 'Microsoft Clipchamp': 'Clipchamp', 'Microsoft To Do': 'To Do', 'Yammer Enterprise': 'Viva Engage',
}
# Vaste kopjes in de berichten van Microsoft -> Nederlands
KOPJES = [('User impact', 'Wat merken gebruikers'), ('Current status', 'Huidige stand'), ('Next update by', 'Volgende update'),
          ('Root cause', 'Oorzaak'), ('Scope of impact', 'Wie heeft er last van'), ('Start time', 'Begonnen'), ('End time', 'Opgelost om'),
          ('Estimated time to resolve', 'Verwachte oplossing'), ('Preliminary root cause', 'Voorlopige oorzaak'), ('Final status', 'Eindstand'),
          ('Title', 'Titel'), ('Next steps', 'Volgende stappen')]


def _tekst(h: str) -> str:
    """HTML van Microsoft naar platte tekst met regeleinden."""
    t = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</div>', '\n', h or '')
    t = re.sub(r'(?i)<li[^>]*>', '• ', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    return re.sub(r'\n\s*\n+', '\n\n', t).strip()


DAGEN = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
MAANDEN = ['januari', 'februari', 'maart', 'april', 'mei', 'juni', 'juli', 'augustus', 'september', 'oktober', 'november', 'december']


def _nl_datum(t: str) -> str:
    """'Tuesday, November 25, 2026, at 6:00 PM UTC' -> 'dinsdag 25 november 2026 om 19:00' (Nederlandse tijd)."""
    m = re.search(r'(?:[A-Za-z]+,\s*)?([A-Za-z]+ \d{1,2}, \d{4}),?\s*(?:at\s*)?(\d{1,2}:\d{2}\s*[AP]M)\s*UTC', t)
    if not m:
        return t
    try:
        d = datetime.strptime(f'{m.group(1)} {m.group(2).replace(" ", "")}', '%B %d, %Y %I:%M%p').replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return t
    return t.replace(m.group(0), f'{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]} {d.year} om {d:%H:%M}')


def _onderdelen(tekst: str) -> list[dict]:
    """De vaste kopjes ('User impact: ...') uit een update halen, in het Nederlands gelabeld."""
    uit = []
    patroon = '|'.join(re.escape(k) for k, _ in KOPJES)
    stukken = re.split(rf'(?im)^\s*({patroon})\s*:\s*', tekst)
    for i in range(1, len(stukken) - 1, 2):
        en = stukken[i].strip()
        nl = next((n for k, n in KOPJES if k.lower() == en.lower()), en)
        waarde = stukken[i + 1].strip()
        if waarde:
            if nl in ('Volgende update', 'Begonnen', 'Opgelost om', 'Verwachte oplossing'):
                waarde = _nl_datum(waarde)
            uit.append({'label': nl, 'text': waarde[:1500]})
    return uit


def _dienst(naam: str) -> str:
    return DIENST.get(naam, naam)


def _status(s: str) -> dict:
    t, k = STATUS.get(s or '', (s or 'Onbekend', 'mu'))
    return {'code': s, 'text': t, 'kind': k}


def _issue(i: dict, volledig: bool = False) -> dict:
    posts = sorted(i.get('posts') or [], key=lambda p: p.get('createdDateTime') or '')
    laatste = _tekst((posts[-1].get('description') or {}).get('content', '')) if posts else ''
    soort = SOORT.get(i.get('classification') or '', (i.get('classification') or '', ''))
    uit = {'id': i.get('id'), 'title': i.get('title') or '', 'service': _dienst(i.get('service') or ''), 'feature': i.get('feature') or '',
           'group': i.get('featureGroup') or '', 'kind': i.get('classification') or '', 'kindText': soort[0], 'kindHint': soort[1],
           'status': _status(i.get('status')), 'resolved': bool(i.get('isResolved')), 'impact': i.get('impactDescription') or '',
           'start': i.get('startDateTime') or '', 'end': i.get('endDateTime') or '', 'updated': i.get('lastModifiedDateTime') or '',
           'latest': _onderdelen(laatste), 'latestRaw': laatste[:4000]}
    if volledig:
        uit['posts'] = [{'at': p.get('createdDateTime') or '', 'type': p.get('postType') or '',
                         'parts': _onderdelen(_tekst((p.get('description') or {}).get('content', ''))),
                         'raw': _tekst((p.get('description') or {}).get('content', ''))[:6000]} for p in reversed(posts)]
    return uit


def _rol(e: Exception) -> Exception:
    return ApiFout(FOUT_ROL, e.status) if isinstance(e, ApiFout) and e.status in (401, 403) else e


@api('health.overview')
def health_overview(c: Ctx, b: dict) -> dict:
    """Actuele stand: diensten, lopende storingen/meldingen en wat de afgelopen dagen is opgelost."""
    g = c.g
    r = parallel({'diensten': lambda: g.all(f'{SA}/healthOverviews'),
                  'issues': lambda: g.all(f'{SA}/issues?$top=100')})
    if isinstance(r['diensten'], Exception):
        raise _rol(r['diensten'])
    grens = (datetime.now(timezone.utc) - timedelta(days=int(b.get('days') or 7))).strftime('%Y-%m-%dT%H:%M:%S')
    alle = r['issues'] if isinstance(r['issues'], list) else []
    lopend = [_issue(i) for i in alle if not i.get('isResolved')]
    recent = [_issue(i) for i in alle if i.get('isResolved') and (i.get('endDateTime') or i.get('lastModifiedDateTime') or '') >= grens]
    lopend.sort(key=lambda x: (x['kind'] != 'incident', x['service'], x['start']))   # storingen eerst
    recent.sort(key=lambda x: x['end'] or x['updated'], reverse=True)
    per_dienst = {}
    for i in lopend:
        per_dienst.setdefault(i['service'], []).append(i['kind'])
    diensten = []
    for d in r['diensten']:
        naam = _dienst(d.get('service') or '')
        diensten.append({'name': naam, 'status': _status(d.get('status')), 'incidents': per_dienst.get(naam, []).count('incident'),
                         'advisories': per_dienst.get(naam, []).count('advisory')})
    diensten.sort(key=lambda d: (d['status']['code'] == 'serviceOperational', d['name'].lower()))
    return {'services': diensten, 'active': lopend, 'recent': recent,
            'issuesError': str(_rol(r['issues'])) if isinstance(r['issues'], Exception) else '',
            'at': datetime.now().strftime('%H:%M')}


@api('health.issue')
def health_issue(c: Ctx, b: dict) -> dict:
    """Eén storing of melding met alle updates (nieuwste eerst)."""
    try:
        return _issue(c.g.get(f"{SA}/issues/{b['id']}"), volledig=True)
    except ApiFout as e:
        raise _rol(e)


@api('health.messages')
def health_messages(c: Ctx, b: dict) -> dict:
    """Berichtencentrum: aangekondigde wijzigingen en acties (laatste 60 dagen)."""
    try:
        alle = c.g.all_of(f'{SA}/messages?$top=100&$orderby=lastModifiedDateTime desc', f'{SA}/messages?$top=100')
    except ApiFout as e:
        raise _rol(e)
    grens = (datetime.now(timezone.utc) - timedelta(days=int(b.get('days') or 60))).strftime('%Y-%m-%dT%H:%M:%S')
    uit = []
    for m in alle:
        if (m.get('lastModifiedDateTime') or '') < grens:
            continue
        cat = CATEGORIE.get(m.get('category') or '', (m.get('category') or '', 'mu'))
        tekst = _tekst((m.get('body') or {}).get('content', ''))
        uit.append({'id': m.get('id'), 'title': m.get('title') or '', 'category': m.get('category') or '', 'categoryText': cat[0], 'categoryKind': cat[1],
                    'services': [_dienst(s) for s in m.get('services') or []], 'major': bool(m.get('isMajorChange')),
                    'actionBy': m.get('actionRequiredByDateTime') or '', 'start': m.get('startDateTime') or '', 'end': m.get('endDateTime') or '',
                    'updated': m.get('lastModifiedDateTime') or '', 'text': tekst[:8000],
                    'tags': m.get('tags') or []})
    uit.sort(key=lambda m: m['updated'], reverse=True)
    return {'messages': uit}
