"""Testgegevens voor de interface (start met --mock). Maakt geen verbinding met Microsoft."""
from __future__ import annotations

import time
from types import SimpleNamespace

from .context import API, Ctx
from .h_sessie import AGENDA_ROLLEN

KLANTEN = [
    {'id': 'home-0000', 'name': 'Justdata BV', 'domain': 'justdata.nl', 'roles': [], 'end': '', 'days': None, 'missing': [], 'own': True},
    {'id': 't-1111', 'name': 'Bakkerij De Korenaar', 'domain': 'korenaar.nl', 'roles': ['Exchange Administrator', 'Intune Administrator', 'License Administrator', 'User Administrator', 'Authentication Administrator'], 'end': '2027-05-01', 'days': 157, 'missing': [], 'own': False},
    {'id': 't-2222', 'name': 'Incassobureau Noord', 'domain': 'incasso-noord.nl', 'roles': ['Global Administrator'], 'end': '2026-12-10', 'days': 15, 'missing': [], 'own': False},
    {'id': 't-3333', 'name': 'Tandartspraktijk Smit', 'domain': 'smit-tandarts.nl', 'roles': ['User Administrator', 'Global Reader'], 'end': '2027-09-30', 'days': 309, 'missing': ['Licenties', 'Exchange', 'Apparaten', 'MFA'], 'own': False},
    {'id': 't-4444', 'name': 'Advocatenkantoor De Wit', 'domain': 'dewit-advocaten.nl', 'roles': [], 'end': '', 'days': None, 'missing': [], 'own': False,
     'access': False, 'fixable': False, 'pending': {'status': 'approvalPending', 'text': 'wacht op goedkeuring door de klant', 'name': 'Justdata 2026',
                                                     'link': 'https://admin.microsoft.com/AdminPortal/Home#/partners/invitation/granularAdminRelationships/abc-123'}},
    {'id': 't-5555', 'name': 'Adviesbureau Meijer', 'domain': 'meijer-advies.nl', 'roles': [], 'end': '', 'days': None, 'missing': [], 'own': False, 'access': False, 'fixable': True},
]
SKUS = [
    {'id': 'sku-bp', 'part': 'SPB', 'name': 'Microsoft 365 Business Premium', 'desc': 'Business Standard plus beveiliging en apparaatbeheer (Intune, Defender).', 'kind': 'betaald', 'total': 25, 'used': 22, 'free': 3, 'status': 'Enabled'},
    {'id': 'sku-bs', 'part': 'O365_BUSINESS_PREMIUM', 'name': 'Microsoft 365 Business Standard', 'desc': "Mail, Teams, OneDrive en Office-programma's (Word, Excel) op de pc.", 'kind': 'betaald', 'total': 5, 'used': 5, 'free': 0, 'status': 'Enabled'},
    {'id': 'sku-ex', 'part': 'EXCHANGESTANDARD', 'name': 'Exchange Online (Plan 1)', 'desc': 'Alleen een mailbox van 50 GB.', 'kind': 'betaald', 'total': 2, 'used': 3, 'free': -1, 'status': 'Enabled'},
    {'id': 'sku-pa', 'part': 'FLOW_FREE', 'name': 'Power Automate (gratis)', 'desc': 'Gratis versie voor automatische werkstromen.', 'kind': 'gratis', 'total': 10000, 'used': 4, 'free': 9996, 'status': 'Enabled'},
]
NAMEN = ['Anna de Vries', 'Bram Jansen', 'Chantal Bakker', 'Daan Visser', 'Eva Smit', 'Finn Meijer', 'Gijs de Boer', 'Hanna Mulder',
         'Ilse de Groot', 'Jesse Bos', 'Kim Vos', 'Lars Peters', 'Mila Hendriks', 'Noah van Dijk', 'Olivia Dekker', 'Pim Brouwer']


def _users(dom: str) -> list[dict]:
    l = []
    for i, n in enumerate(NAMEN):
        v, *r = n.split(' ')
        upn = f"{v.lower()}.{r[-1].lower()}@{dom}"
        l.append({'id': f'u{i}', 'name': n, 'upn': upn, 'on': i != 5, 'lic': ['sku-bp'] if i % 4 else ['sku-bs'], 'title': 'Medewerker',
                  'dept': 'Kantoor', 'guest': False})
    l.append({'id': 'g1', 'name': 'Extern Adviseur', 'upn': 'adviseur_extern.nl#EXT#@x.onmicrosoft.com', 'on': True, 'lic': [], 'title': '', 'dept': '', 'guest': True})
    return l


STAAT = {'tenant': None}


def _dom() -> str:
    k = next((k for k in KLANTEN if k['id'] == STAAT['tenant']), KLANTEN[1])
    return k['domain']


def _info(tid: str) -> dict:
    k = next(k for k in KLANTEN if k['id'] == tid)
    return {'tenantId': tid, 'tenant': k['name'], 'account': 'beheerder@voorbeeld.nl', 'exo': tid != 't-3333',
            'exoError': '' if tid != 't-3333' else 'Geen toegang (rol Exchange Administrator ontbreekt).',
            'domains': [{'id': k['domain'], 'def': True, 'initial': False}, {'id': k['domain'].split('.')[0] + '.onmicrosoft.com', 'def': False, 'initial': True}],
            'defaultDomain': k['domain'], 'roles': [{'key': a, 'label': b} for a, b in AGENDA_ROLLEN]}


def m(naam: str):
    def deco(fn):
        API[naam] = fn
        return fn
    return deco


def ok(tekst: str):
    def fn(c: Ctx, b: dict) -> dict:
        time.sleep(0.4)
        c.L(tekst)
        return {}
    return fn


@m('auth.status')
def _s(c, b):
    return {'loggedIn': bool(c.staat.beheerder), 'user': c.staat.beheerder, 'tenant': STAAT['tenant']}


@m('auth.login')
def _l(c, b):
    time.sleep(1.2)
    c.staat.beheerder = {'name': 'Beheerder Test', 'upn': 'beheerder@voorbeeld.nl', 'tid': 'home-0000'}
    # Testlogin telt als Justdata-login (anders verbergt de app back-up, e-mailbeveiliging en Autotask)
    from .rechten import PARTNER_TENANT
    c.staat.auth.account = {'username': 'beheerder@voorbeeld.nl'}
    c.staat.auth.home_tenant = PARTNER_TENANT
    return {'user': c.staat.beheerder, 'exo': True}


@m('auth.logout')
def _lo(c, b):
    c.staat.auth.account = None
    c.staat.auth.home_tenant = ''
    c.staat.beheerder = {}
    STAAT['tenant'] = None
    return {}


@m('customers')
def _k(c, b):
    time.sleep(0.6)
    return {'customers': KLANTEN, 'home': 'home-0000'}


VOORTGANG: dict = {}


@m('tenant.progress')
def _tp(c, b):
    v = VOORTGANG.get(b.get('id'))
    return {'text': v[0], 'seconds': int(time.time() - v[1])} if v else {}


@m('tenant.select')
def _t(c, b):
    if b['id'] == 't-4444':
        from .gdap import GdapMelding, goedkeuringslink
        time.sleep(1)
        raise GdapMelding("De nieuwe GDAP-relatie 'Justdata 2026' wacht op goedkeuring door de klant. Stuur de klant de goedkeuringslink; "
                          'zodra de klant heeft goedgekeurd regelt de app de rest automatisch.', goedkeuringslink('abc-123'), 'approvalPending')
    if b['id'] == 't-5555':
        begin = time.time()
        for tekst, sec in [('GDAP-relaties van de klant controleren...', 2), ("GDAP-toewijzing aanmaken op relatie 'Justdata' (AdminAgents, 12 rollen)...", 2),
                           ('Wachten tot Microsoft de GDAP-toewijzing activeert (0 s, meestal 1 tot 3 minuten)...', 4), ('App koppelen via Partner Center...', 2)]:
            VOORTGANG[b['id']] = (tekst, begin)
            time.sleep(sec)
        VOORTGANG.pop(b['id'], None)
    time.sleep(0.8)
    STAAT['tenant'] = b['id']
    c.staat.tenants[b['id']] = SimpleNamespace(naam=next(k['name'] for k in KLANTEN if k['id'] == b['id']))
    return _info(b['id'])


@m('info')
def _i(c, b):
    return _info(c.tid)


@m('activity')
def _a(c, b):
    return {'items': list(reversed(c.staat.activiteit.regels))}


API['skus'] = lambda c, b: {'skus': SKUS}
API['users'] = lambda c, b: (time.sleep(0.3), {'users': _users(_dom())})[1]
API['shared.list'] = lambda c, b: {'shared': [{'name': 'Info', 'mail': 'info@' + _dom()}, {'name': 'Facturen', 'mail': 'facturen@' + _dom()},
                                               {'name': 'Planning', 'mail': 'planning@' + _dom()}, {'name': 'Sollicitaties', 'mail': 'hr@' + _dom()}]}


@m('user.get')
def _ug(c, b):
    u = next(x for x in _users(_dom()) if x['id'] == b['id'])
    v, *r = u['name'].split(' ')
    return {**u, 'given': v, 'sur': ' '.join(r), 'mail': u['upn'], 'office': 'Utrecht', 'mobile': '+31 6 12345678', 'loc': 'NL',
            'aliases': [{'addr': u['upn'], 'primary': True}, {'addr': v.lower() + '@' + _dom(), 'primary': False}],
            'licenses': [{'sku': s, 'direct': True} for s in u['lic']] + [{'sku': 'sku-pa', 'direct': False}]}


GROEPEN = [
    {'id': 'gr1', 'name': 'Alle medewerkers', 'mail': 'iedereen@x', 'type': 'M365', 'sync': False, 'edit': True},
    {'id': 'gr2', 'name': 'Intune - Laptops', 'mail': '', 'type': 'Beveiliging', 'sync': False, 'edit': True},
    {'id': 'gr3', 'name': 'Verkoop', 'mail': 'verkoop@x', 'type': 'Distributielijst', 'sync': False, 'edit': True},
    {'id': 'gr4', 'name': 'Alle gebruikers (dynamisch)', 'mail': '', 'type': 'Dynamisch', 'sync': False, 'edit': False},
    {'id': 'gr5', 'name': 'Directie', 'mail': 'directie@x', 'type': 'Mail-beveiliging', 'sync': True, 'edit': False},
]
API['user.groups'] = lambda c, b: {'groups': GROEPEN[:2] + GROEPEN[3:4], 'all': GROEPEN}
API['groups.list'] = lambda c, b: {'groups': GROEPEN + [{'id': s['mail'], 'name': s['name'], 'mail': s['mail'], 'type': 'Gedeeld postvak', 'sync': False, 'edit': True} for s in API['shared.list'](c, b)['shared']]}
API['group.members'] = lambda c, b: (time.sleep(0.3), {'members': [{'id': 'u1', 'key': 'bram.jansen@' + _dom(), 'name': 'Bram Jansen', 'info': 'Gebruiker', 'full': True, 'send': True},
                                                                   {'id': 'u2', 'key': 'chantal.bakker@' + _dom(), 'name': 'Chantal Bakker', 'info': 'Gebruiker', 'full': True, 'send': False}]})[1]
API['user.mfa'] = lambda c, b: {'methods': [{'id': 'm1', 'type': 'microsoftAuthenticatorAuthenticationMethod', 'name': 'Microsoft Authenticator-app (iPhone 15)', 'supported': True},
                                            {'id': 'm2', 'type': 'phoneAuthenticationMethod', 'name': 'Telefoon (sms/bellen): +31 6 12345678', 'supported': True}]}
API['user.sharedscan'] = lambda c, b: (time.sleep(0.5), {'results': [{'mail': x, 'full': x.startswith('info'), 'send': x.startswith('info')} for x in (b.get('mailboxes') or [s['mail'] for s in API['shared.list'](c, b)['shared']])]})[1]
API['user.create'] = lambda c, b: (time.sleep(1.5), c.L(f"Gebruiker {b['alias']}@{b['domain']} aangemaakt."), {'upn': f"{b['alias']}@{b['domain']}", 'id': 'nieuw', 'problems': []})[2]
API['offboard'] = lambda c, b: (time.sleep(1.2), c.L('Postvak is nu een gedeeld postvak.'), c.L('KLAAR: medewerker is uit dienst gemeld.'), {})[3]
API['cal.get'] = lambda c, b: {'rights': [{'name': 'Standaard', 'key': 'Standaard', 'rights': 'AvailabilityOnly', 'special': True},
                                          {'name': 'Anoniem', 'key': 'Anoniem', 'rights': 'None', 'special': True},
                                          {'name': 'Bram Jansen', 'key': 'bram.jansen@' + _dom(), 'rights': 'Editor (Delegate)', 'special': False}]}
API['inactive'] = lambda c, b: (time.sleep(0.8), {
    'licensed': [{'id': 'u5', 'name': 'Finn Meijer', 'upn': 'finn.meijer@' + _dom(), 'on': False, 'last': '2026-06-02', 'created': '2023-01-10', 'days': 176, 'never': False, 'lic': ['sku-bp'], 'guest': False, 'reason': '', 'pending': False}],
    'members': [{'id': 'x1', 'name': 'Test Account', 'upn': 'test@' + _dom(), 'on': True, 'last': '', 'created': '2025-02-01', 'days': 297, 'never': True, 'lic': [], 'guest': False, 'reason': '', 'pending': False},
                {'id': 'x2', 'name': 'Scanner', 'upn': 'scan@' + _dom(), 'on': True, 'last': '2025-11-01', 'created': '2021-02-01', 'days': 389, 'never': False, 'lic': [], 'guest': False, 'reason': 'Gedeeld postvak of ruimte/apparaat', 'pending': False}],
    'guests': [{'id': 'g1', 'name': 'Extern Adviseur', 'upn': 'adviseur_extern.nl#EXT#', 'on': True, 'last': '', 'created': '2025-08-01', 'days': 116, 'never': True, 'lic': [], 'guest': True, 'reason': '', 'pending': True}],
    'mbCheck': True, 'roleCheck': True, 'total': 17, 'days': b.get('days', 90)})[1]
DEVS = [{'id': f'd{i}', 'name': n, 'owner': 'company', 'os': os_, 'osv': v, 'comp': cp, 'upn': 'anna.devries@x', 'user': 'Anna de Vries',
         'sync': '2026-11-24T09:12:00Z', 'serial': f'SN{i}4X9', 'model': mo, 'man': ma, 'aad': f'aad-{i}'}
        for i, (n, os_, v, cp, mo, ma) in enumerate([('LT-ANNA', 'Windows', '10.0.26100', 'compliant', 'Latitude 7450', 'Dell'),
                                                    ('LT-BRAM', 'Windows', '10.0.22631', 'noncompliant', 'EliteBook 840', 'HP'),
                                                    ('iPhone van Eva', 'iOS', '18.1', 'compliant', 'iPhone 15', 'Apple'),
                                                    ('MB-DAAN', 'macOS', '15.1', 'ingraceperiod', 'MacBook Air', 'Apple')])]
API['dev.list'] = lambda c, b: (time.sleep(0.4), {'devices': DEVS})[1]
API['dev.get'] = lambda c, b: {**next(d for d in DEVS if d['id'] == b['id']), 'mgmt': 'mdm', 'last': '2026-11-24T09:12:00Z', 'enrolled': '2025-03-01T10:00:00Z',
                               'enc': True, 'free': 120e9, 'total': 512e9, 'mac': 'AA:BB:CC:DD:EE:FF', 'imei': '', 'phone': '', 'enrollType': 'windowsAzureADJoin',
                               'reg': 'registered', 'category': '', 'patch': '', 'jail': 'Unknown', 'entra': {'id': 'e1', 'name': 'LT-ANNA', 'trust': 'AzureAd', 'enabled': True, 'last': ''},
                               'autopilot': {'id': 'ap1', 'tag': 'Kantoor', 'profile': 'assignedInSync', 'state': 'enrolled', 'contact': '2026-11-20T08:00:00Z'} if b['id'] == 'd0' else None}
API['dev.bitlocker'] = lambda c, b: {'keys': [{'id': '6f1c2a9b-1234-4cde-9abc-0123456789ab', 'created': '2025-03-01T10:05:00Z', 'vol': 'operatingSystemVolume'}]}
API['dev.bitlockerkey'] = lambda c, b: (c.L('BitLocker-herstelsleutel opgevraagd (dit wordt vastgelegd in de auditlog van Entra).'), {'key': '123456-234567-345678-456789-567890-678901-789012-890123'})[1]
API['dev.groups'] = lambda c, b: {'groups': [{'id': 'gr2', 'name': 'Intune - Laptops', 'dynamic': False, 'sec': True}], 'all': [g for g in GROEPEN if g['type'] == 'Beveiliging']}

PREFS = {'fav': ['t-2222'], 'recent': ['t-1111']}
API['prefs.get'] = lambda c, b: PREFS
API['prefs.fav'] = lambda c, b: PREFS.update(fav=[i for i in PREFS['fav'] if i != b['id']] + ([b['id']] if b.get('on') else [])) or PREFS
API['prefs.recent'] = lambda c, b: PREFS.update(recent=[b['id']] + [i for i in PREFS['recent'] if i != b['id']]) or PREFS

for n, t in {'user.update': 'Gegevens opgeslagen.', 'user.block': 'Aanmelden gewijzigd.', 'user.revoke': 'Alle sessies afgemeld.',
             'user.alias': 'Alias bijgewerkt.', 'user.mfareset': 'MFA-methoden verwijderd.', 'user.license': 'Licenties bijgewerkt.',
             'user.group': 'Groepslidmaatschap bijgewerkt.', 'user.sharedset': 'Rechten bijgewerkt.', 'cal.set': 'Agendarechten ingesteld.',
             'cal.remove': 'Rechten verwijderd.', 'group.add': 'Toegevoegd.', 'group.remove': 'Verwijderd.', 'group.delete': 'Verwijderd.',
             'group.create': 'Aangemaakt.', 'inactive.delete': '1 verwijderd, 0 mislukt.', 'dev.group': 'Groep bijgewerkt.',
             'dev.sync': 'Synchronisatie gestart.', 'dev.delete': 'Apparaat verwijderd.', 'ap.tag': 'Group tag aangepast.',
             'ap.delete': 'Autopilot-registratie verwijderd.', 'ap.sync': 'Autopilot-synchronisatie gestart.',
             'dev.apreset': 'Autopilot Reset gestart.', 'dev.deletemany': 'Apparaten verwijderd.', 'dev.restartmany': 'Herstart gestuurd.'}.items():
    API[n] = ok(t)

AP = [{'id': f'ap{i}', 'serial': s, 'tag': t, 'man': m, 'model': mo, 'profile': p, 'state': st, 'contact': f'2026-11-2{i}T08:00:00Z',
       'upn': u, 'name': n, 'intune': f'd{i}' if st == 'enrolled' else '', 'order': ''}
      for i, (s, t, m, mo, p, st, u, n) in enumerate([
          ('SN04X9', 'Kantoor', 'Dell', 'Latitude 7450', 'assignedInSync', 'enrolled', 'anna.devries@x', 'LT-ANNA'),
          ('SN14X9', 'Kantoor', 'HP', 'EliteBook 840', 'assignedInSync', 'enrolled', '', 'LT-BRAM'),
          ('5CG3021ABC', '', 'HP', 'ProBook 450', 'notAssigned', 'notContacted', '', ''),
          ('7XKQ2Z3', 'Thuiswerk', 'Dell', 'Latitude 5440', 'pending', 'notContacted', '', '')])]
API['ap.list'] = lambda c, b: (time.sleep(0.4), {'items': AP, 'lastSync': '2026-11-25T07:30:00Z', 'syncStatus': 'completed', 'lastManualSync': ''})[1]

# Update-melding testen: start met M365_MOCK_UPDATE=1
if __import__('os').environ.get('M365_MOCK_UPDATE'):
    API['update.status'] = lambda c, b: {'current': '2.1.0', 'latest': '2.2.0', 'available': True, 'required': False, 'canInstall': True,
                                         'date': '2026-12-01', 'notes': ['Snellere klantwissel', 'Nieuwe rapportage licenties']}
    API['update.install'] = lambda c, b: (time.sleep(1.5), {'restarting': True})[1]

# Toegang (GDAP) in testmodus: Tandartspraktijk Smit regelbaar, plus een extra niet-regelbare klant
for _k in KLANTEN:
    _k.setdefault('access', _k['id'] != 't-3333')
    _k.setdefault('fixable', _k['id'] == 't-3333')
KLANTEN.append({'id': 't-4444', 'name': 'Autobedrijf Test', 'domain': 'autotest.nl', 'roles': [], 'end': '2027-02-01', 'days': 68,
                'missing': [], 'own': False, 'access': False, 'fixable': False})
_KLUS = {'bezig': False, 'totaal': 0, 'klaar': 0, 'ok': [], 'fouten': [], 'start': 0}


def _gdap_alles(c, b):
    _KLUS.update(bezig=True, totaal=1, klaar=0, ok=[], fouten=[], start=time.time())
    return dict(_KLUS)


def _gdap_status(c, b):
    if _KLUS['bezig'] and time.time() - _KLUS['start'] > 5:
        _KLUS.update(bezig=False, klaar=1, ok=['Tandartspraktijk Smit'])
        next(k for k in KLANTEN if k['id'] == 't-3333')['access'] = True
    return {**_KLUS, 'customers': None if _KLUS['bezig'] else KLANTEN}


API['gdap.alles'] = _gdap_alles
API['gdap.status'] = _gdap_status


# ---------- Domeinen en message trace (v2.6) ----------
DOMS = [{'id': 'korenaar.nl', 'default': True, 'initial': False, 'verified': True, 'auth': 'Managed', 'services': ['Email', 'Intune'],
         'pwdays': None, 'exoType': 'Authoritative', 'exoDefault': True, 'matchSub': False},
        {'id': 'bakkerij-korenaar.nl', 'default': False, 'initial': False, 'verified': False, 'auth': 'Managed', 'services': [],
         'pwdays': None, 'exoType': '', 'exoDefault': False, 'matchSub': False},
        {'id': 'korenaar.onmicrosoft.com', 'default': False, 'initial': True, 'verified': True, 'auth': 'Managed', 'services': ['Email'],
         'pwdays': None, 'exoType': 'Authoritative', 'exoDefault': False, 'matchSub': False}]
API['dom.list'] = lambda c, b: (time.sleep(0.3), {'domains': DOMS, 'exo': True})[1]
API['dom.get'] = lambda c, b: (time.sleep(0.6), {
    'id': b['id'], 'references': 12,
    'verification': [{'type': 'TXT', 'name': b['id'], 'value': 'MS=ms48213377', 'ttl': 3600}],
    'dns': [{'type': 'MX', 'name': b['id'], 'value': 'korenaar-nl.mail.protection.outlook.com', 'service': 'E-mail', 'extra': 'Prioriteit 0',
             'found': ['korenaar-nl.mail.protection.outlook.com'], 'status': 'ok'},
            {'type': 'TXT', 'name': b['id'], 'value': 'v=spf1 include:spf.protection.outlook.com -all', 'service': 'E-mail (SPF)',
             'found': ['v=spf1 include:spf.protection.outlook.com -all'], 'status': 'ok'},
            {'type': 'CNAME', 'name': 'autodiscover.' + b['id'], 'value': 'autodiscover.outlook.com', 'service': 'E-mail', 'found': [], 'status': 'ontbreekt'},
            {'type': 'TXT', 'name': '_dmarc.' + b['id'], 'value': 'v=DMARC1; p=quarantine', 'service': 'DMARC (aanbevolen)',
             'found': ['v=DMARC1; p=none'], 'status': 'ok'},
            {'type': 'CNAME', 'name': 'selector1._domainkey.' + b['id'], 'value': 'zie Bedreigingsbeheer > DKIM', 'service': 'DKIM', 'vrij': True,
             'found': [], 'status': 'ontbreekt'}]})[1]
for n, t in {'dom.add': 'Domein toegevoegd.', 'dom.verify': 'Domein geverifieerd.', 'dom.default': 'Standaarddomein ingesteld.',
             'dom.exotype': 'Exchange-domeintype opgeslagen.', 'dom.delete': 'Domein verwijderd.'}.items():
    API[n] = ok(t)


def _trace(c, b):
    time.sleep(0.8)
    from datetime import datetime, timedelta
    nu = datetime(2026, 11, 25, 12, 0)
    msgs = [{'received': (nu - timedelta(hours=i * 7)).strftime('%Y-%m-%dT%H:%M:%SZ'), 'sender': f'afzender{i % 7}@extern.nl',
             'recipient': 'anna.devries@korenaar.nl', 'subject': f'Offerte {1000 + i}', 'status': ['Delivered', 'FilteredAsSpam', 'Failed'][i % 3],
             'size': 20000 + i, 'traceId': f't{i}', 'messageId': f'<m{i}@extern.nl>', 'fromIp': '203.0.113.5', 'toIp': ''} for i in range(700)]
    return {'messages': msgs, 'start': b.get('start'), 'end': b.get('end'), 'blocks': 9, 'truncated': False}


API['trace.search'] = _trace


# ---------- Administratie (v2.7) ----------
_ADM = {'bezig': False, 'totaal': 0, 'klaar': 0, 'begin': '', 'eind': '', 'klanten': []}


def _adm_klant(k, i):
    import random
    rnd = random.Random(i)
    gebruik = ['actief'] * 6 + ['inactief', 'ongebruikt', 'uit', 'nieuw']
    def sku(sid, part, naam, n, betaald=True):
        users = [{'name': f'Medewerker {j}', 'upn': f'm{j}@{k["domain"] or "klant.nl"}', 'use': rnd.choice(gebruik),
                  'last': '2026-11-2%dT08:00:00+00:00' % (j % 5), 'days': rnd.randint(0, 200), 'guest': False} for j in range(n)]
        tel = {u: sum(1 for x in users if x['use'] == u) for u in ('actief', 'nieuw', 'inactief', 'ongebruikt', 'uit', 'onbekend')}
        gekocht = n + rnd.randint(0, 3) if betaald else 10000
        vrij = max(0, gekocht - n) if betaald else 0
        return {'sku': sid, 'part': part, 'name': naam, 'paid': betaald, 'bought': gekocht, 'assigned': n, 'free': vrij, 'short': 0,
                'suspended': 0, 'warning': 0, 'status': 'Enabled', **tel, 'saving': (vrij + tel['uit'] + tel['ongebruikt']) if betaald else 0,
                'renew': '2026-12-%02dT00:00:00+00:00' % (5 + i * 4), 'trial': False, 'subs': 1, 'users': users}
    skus = [sku('bp', 'SPB', 'Microsoft 365 Business Premium', 6 + i * 3), sku('bb', 'O365_BUSINESS_ESSENTIALS', 'Microsoft 365 Business Basic', 2 + i),
            sku('fl', 'FLOW_FREE', 'Power Automate (gratis)', 3, False)]
    b = [s for s in skus if s['paid']]
    return {'id': k['id'], 'name': k['name'], 'own': bool(k.get('own')), 'ok': True, 'signins': i != 2, 'skus': skus,
            'bought': sum(s['bought'] for s in b), 'assigned': sum(s['assigned'] for s in b), 'free': sum(s['free'] for s in b), 'short': 0,
            'disabled': sum(s['uit'] for s in b), 'unused': sum(s['ongebruikt'] for s in b), 'inactive': sum(s['inactief'] for s in b),
            'saving': sum(s['saving'] for s in b), 'warnings': 0, 'trials': 0, 'renew': b[0]['renew'], 'at': '2026-11-25 21:00'}


def _adm_start(c, b):
    doel = [k for k in KLANTEN if k.get('access') is not False]
    _ADM.update(bezig=False, totaal=len(doel), klaar=len(doel), begin='2026-11-25 21:00', eind='2026-11-25 21:01',
                klanten=[_adm_klant(k, i) for i, k in enumerate(doel)] + [{'id': f't-9{j}', 'name': n, 'ok': False, 'errorKind': ek, 'error': t}
                         for j, (n, ek, t) in enumerate([('Advocatenkantoor De Wit', 'koppeling', 'De app is bij deze klant nog niet gekoppeld. Klik op Koppeling regelen; de app doet het zelf.'),
                                                         ('Installatiebedrijf Bos', 'koppeling', 'De app is bij deze klant nog niet gekoppeld. Klik op Koppeling regelen; de app doet het zelf.'),
                                                         ('Stichting Zorgpunt', 'mfa', 'Deze klant vraagt om extra verificatie (MFA) voor je account. Open de klant om je aan te melden.')])])
    return _ADM


API['adm.start'] = _adm_start
API['adm.status'] = lambda c, b: _ADM


# ---------- Migratie (v2.8) ----------
MIG_EPS = [{'id': 'IMAP-oudehoster', 'type': 'imap', 'typeText': 'IMAP', 'server': 'imap.oudehoster.nl', 'port': '993', 'security': 'Ssl', 'max': '20', 'account': ''}]
MIG_BATCHES = [
    {'id': 'Verkoop-week-48', 'status': 'Syncing', 'type': 'imap', 'typeText': 'IMAP', 'total': 4, 'active': 2, 'synced': 1, 'finalized': 0, 'failed': 1,
     'stopped': 0, 'pending': 0, 'created': '2026-11-24T09:00:00Z', 'started': '2026-11-24T09:01:00Z', 'lastSync': '2026-11-25T08:30:00Z',
     'completeAfter': '', 'endpoint': 'IMAP-oudehoster', 'domain': '', 'notify': 'beheerder@voorbeeld.nl', 'message': ''},
    {'id': 'Google-directie', 'status': 'Synced', 'type': 'gmail', 'typeText': 'Google Workspace', 'total': 2, 'active': 0, 'synced': 2, 'finalized': 0,
     'failed': 0, 'stopped': 0, 'pending': 0, 'created': '2026-11-20T10:00:00Z', 'started': '2026-11-20T10:00:00Z', 'lastSync': '2026-11-25T06:00:00Z',
     'completeAfter': '', 'endpoint': 'Google', 'domain': 'korenaar.mail.onmicrosoft.com', 'notify': '', 'message': ''}]
API['mig.endpoints'] = lambda c, b: {'endpoints': MIG_EPS}
API['mig.batches'] = lambda c, b: (time.sleep(0.4), {'batches': MIG_BATCHES})[1]
API['mig.domains'] = lambda c, b: {'domains': ['korenaar.mail.onmicrosoft.com', 'korenaar.onmicrosoft.com', 'korenaar.nl']}
API['mig.users'] = lambda c, b: (time.sleep(0.5), {'users': [
    {'mail': 'anna@korenaar.nl', 'status': 'Synced', 'detail': '', 'synced': 18234, 'skipped': 2, 'total': 18240, 'size': '2.1 GB', 'percent': 100, 'lastSync': '2026-11-25T08:30:00Z', 'error': ''},
    {'mail': 'bram@korenaar.nl', 'status': 'Syncing', 'detail': 'Kopiëren van berichten', 'synced': 5210, 'skipped': 0, 'total': 9000, 'size': '640 MB', 'percent': 58, 'lastSync': '', 'error': ''},
    {'mail': 'eva@korenaar.nl', 'status': 'Failed', 'detail': '', 'synced': 0, 'skipped': 0, 'total': 0, 'size': '', 'percent': 0, 'lastSync': '',
     'error': 'Error: The connection to the server imap.oudehoster.nl could not be completed. Aanmelden mislukt: verkeerd wachtwoord.'}]})[1]
API['mig.check'] = lambda c, b: {'rows': [{'mail': r['mail'].strip().lower(), 'ok': not r['mail'].startswith('x'), 'type': 'UserMailbox',
                                           'reason': '' if not r['mail'].startswith('x') else 'Geen postvak met dit adres in Microsoft 365 (eerst aanmaken en licentie geven)'} for r in b.get('rows') or []]}
API['mig.endpoint.test'] = lambda c, b: (time.sleep(0.8), c.L('Verbinding gelukt.'), {'ok': True, 'message': '', 'server': ''})[2]
API['mig.endpoint.new'] = lambda c, b: (c.L(f"Verbinding {b.get('name')} aangemaakt."), {'endpoint': {'id': b.get('name')}})[1]
for n, t in {'mig.endpoint.remove': 'Verbinding verwijderd.', 'mig.batch.new': 'Migratie aangemaakt en gestart.', 'mig.batch.action': 'Gelukt.',
             'mig.batch.set': 'Migratie bijgewerkt.'}.items():
    API[n] = ok(t)


# ---------- Servicestatus (v2.9) ----------
def _h_issue(i, soort, dienst, status, opgelost=False):
    return {'id': ('EX' if 'Exchange' in dienst else 'TM') + f'9{i}1234',
            'title': ['Some users may be unable to send email from Outlook on the web', 'Users may experience delays when joining Teams meetings',
                      'Admins may not see updated license counts'][i % 3],
            'service': dienst, 'feature': ['E-Mail and calendar access', 'Teams Components', 'Portal'][i % 3], 'group': '', 'kind': soort,
            'kindText': 'Storing' if soort == 'incident' else 'Melding', 'kindHint': '',
            'status': {'code': status, 'text': {'serviceDegradation': 'Verminderde werking', 'investigating': 'Wordt onderzocht',
                                                'serviceRestored': 'Hersteld'}[status], 'kind': 'g' if opgelost else 'o'},
            'resolved': opgelost, 'impact': 'Users may be unable to send email from Outlook on the web.', 'start': '2026-11-25T07:12:00Z',
            'end': '2026-11-24T15:00:00Z' if opgelost else '', 'updated': '2026-11-25T10:40:00Z',
            'latest': [{'label': 'Wat merken gebruikers', 'text': 'Users may be unable to send email from Outlook on the web.'},
                       {'label': 'Huidige stand', 'text': 'We have identified a recent change and are reverting it to remediate impact.'},
                       {'label': 'Volgende update', 'text': 'dinsdag 25 november 2026 om 14:00'}], 'latestRaw': ''}


API['health.overview'] = lambda c, b: (time.sleep(0.5), {
    'services': [{'name': 'Exchange Online (e-mail en agenda)', 'status': {'code': 'serviceDegradation', 'text': 'Verminderde werking', 'kind': 'o'}, 'incidents': 1, 'advisories': 0},
                 {'name': 'Teams', 'status': {'code': 'investigating', 'text': 'Wordt onderzocht', 'kind': 'o'}, 'incidents': 0, 'advisories': 1}]
    + [{'name': n, 'status': {'code': 'serviceOperational', 'text': 'Werkt normaal', 'kind': 'g'}, 'incidents': 0, 'advisories': 0}
       for n in ['SharePoint', 'OneDrive', 'Microsoft Entra ID (aanmelden)', 'Intune (apparaatbeheer)', 'Office-apps (Word, Excel, Outlook)']],
    'active': [_h_issue(0, 'incident', 'Exchange Online (e-mail en agenda)', 'serviceDegradation'), _h_issue(1, 'advisory', 'Teams', 'investigating')],
    'recent': [_h_issue(2, 'advisory', 'Microsoft 365 (algemeen)', 'serviceRestored', True)], 'issuesError': '', 'at': '11:05'})[1]
API['health.issue'] = lambda c, b: {**_h_issue(0, 'incident', 'Exchange Online (e-mail en agenda)', 'serviceDegradation'),
                                    'posts': [{'at': '2026-11-25T10:40:00Z', 'type': 'regular', 'parts': _h_issue(0, 'incident', 'x', 'investigating')['latest'], 'raw': ''},
                                              {'at': '2026-11-25T07:30:00Z', 'type': 'regular', 'parts': [{'label': 'Huidige stand', 'text': 'We are investigating a potential issue.'}], 'raw': ''}]}
API['health.messages'] = lambda c, b: {'messages': [
    {'id': 'MC123456', 'title': 'Retirement of Exchange Web Services in Exchange Online', 'category': 'planForChange', 'categoryText': 'Wijziging gepland', 'categoryKind': 'o',
     'services': ['Exchange Online (e-mail en agenda)'], 'major': True, 'actionBy': '2026-10-01T00:00:00Z', 'start': '', 'end': '', 'updated': '2026-11-20T09:00:00Z',
     'text': 'We are retiring Exchange Web Services (EWS)...', 'tags': []},
    {'id': 'MC654321', 'title': 'Microsoft Teams: New meeting recap experience', 'category': 'stayInformed', 'categoryText': 'Ter info', 'categoryKind': 'mu',
     'services': ['Teams'], 'major': False, 'actionBy': '', 'start': '', 'end': '', 'updated': '2026-11-18T09:00:00Z', 'text': 'Coming soon...', 'tags': []}]}


# ---------- Huisstijl (v2.10) ----------
BRAND = {'exists': True, 'org': 'Bakkerij De Korenaar', 'backgroundColor': '#1B7EA9', 'signInPageText': 'Hulp nodig? Bel Justdata.',
         'usernameHintText': 'naam@korenaar.nl', 'customPrivacyAndCookiesText': '', 'customPrivacyAndCookiesUrl': '', 'customTermsOfUseText': '',
         'customTermsOfUseUrl': '', 'customCannotAccessYourAccountText': '', 'customCannotAccessYourAccountUrl': '', 'customForgotMyPasswordText': '',
         'customResetItNowText': '', 'customAccountResetCredentialsUrl': '',
         'visibility': {k: False for k in ['hideCannotAccessYourAccount', 'hideForgotMyPassword', 'hideResetItNow', 'hideKeepMeSignedIn',
                                           'hideAccountResetCredentials', 'hideTermsOfUse', 'hidePrivacyAndCookies']},
         'layout': 'default', 'header': False, 'footer': True, 'images': {k: '' for k in ['bannerLogo', 'squareLogo', 'squareLogoDark', 'backgroundImage', 'favicon']}}
API['brand.get'] = lambda c, b: (time.sleep(0.4), BRAND)[1]
for n, t in {'brand.save': 'Huisstijl van de aanmeldpagina opgeslagen.', 'brand.image': 'Afbeelding geplaatst.', 'brand.reset': 'Huisstijl verwijderd.'}.items():
    API[n] = ok(t)


API['shared.member.set'] = ok('Rechten bijgewerkt.')

API['cal.get'] = lambda c, b: {'rights': [
    {'name': 'Standaard', 'key': 'Standaard', 'rights': 'AvailabilityOnly', 'role': 'AvailabilityOnly', 'delegate': False, 'priv': False, 'flags': [], 'special': True},
    {'name': 'Anna de Vries', 'key': 'anna.devries@' + _dom(), 'rights': 'Editor', 'role': 'Editor', 'delegate': True, 'priv': True, 'flags': ['Delegate', 'CanViewPrivateItems'], 'special': False},
    {'name': 'Bram Jansen', 'key': 'bram.jansen@' + _dom(), 'rights': 'Reviewer', 'role': 'Reviewer', 'delegate': False, 'priv': False, 'flags': [], 'special': False}]}


# ---------- Automatisering (v2.11) ----------
def _auto_start(c, b):
    import threading
    import uuid as _uuid
    from . import h_automatisering as H
    d = b.get('process') or {}
    rid = _uuid.uuid4().hex[:12]
    items = []
    for k in b.get('customers') or []:
        for i, r in enumerate(b.get('rows') or [{}]):
            items.append({'klant': k['id'], 'klantnaam': k.get('name'), 'regel': i + 1, 'invoer': r, 'status': 'wachten', 'rapport': [], 'log': [],
                          'stappen': [{'id': s.get('id'), 'naam': H.BLOKKEN.get(s['block'], {}).get('name', s['block']), 'status': 'wachten', 'melding': ''}
                                      for s in d.get('steps') or []]})
    run = {'id': rid, 'naam': d.get('name'), 'bezig': True, 'items': items, 'start': '2026-11-26 12:00'}
    H._RUNS[rid] = run

    def loop():
        for it in items:
            it['status'] = 'bezig'
            vars_ = {**{k.lower(): v for k, v in it['invoer'].items()}, 'klant': it['klantnaam'], 'klantdomein': 'korenaar.nl'}
            for n, (s, st) in enumerate(zip(d.get('steps') or [], it['stappen']), 1):
                if not H.voorwaarde_ok(s.get('when'), vars_):
                    st['status'], st['melding'] = 'overgeslagen', 'Voorwaarde niet van toepassing'
                    continue
                st['status'] = 'bezig'
                time.sleep(0.35)
                p = {k: H.invullen(v, vars_) for k, v in (s.get('params') or {}).items()}
                if s['block'] == 'gebruiker.aanmaken':
                    upn = (H.FILTERS['alias'](str(p.get('alias') or 'test')) + '@korenaar.nl')
                    vars_[f'stap{n}'] = {'upn': upn, 'wachtwoord': 'Voorbeeld#2026', 'naam': p.get('voornaam', '') + ' ' + p.get('achternaam', '')}
                    st['melding'] = f'Gebruiker {upn} aangemaakt.'
                elif s['block'].startswith('controle.'):
                    it['rapport'].append({'Controle': H.BLOKKEN[s['block']]['name'], 'Resultaat': 'Voorbeeldregel uit de testmodus'})
                    st['melding'] = 'Controle uitgevoerd.'
                elif s['block'] == 'rapport.regel':
                    it['rapport'].append({'Melding': p.get('tekst')})
                    st['melding'] = p.get('tekst')
                else:
                    st['melding'] = 'Gelukt (testmodus).'
                st['status'] = 'ok'
            it['status'] = 'ok'
        run['bezig'] = False
    threading.Thread(target=loop, daemon=True).start()
    return H._run_status(rid)


API['auto.start'] = _auto_start


# ---------- Compliance (v2.12) en automatisch antwoord ----------
# De echte verwerking uit h_compliance draait op een nep-Graph/Exchange, zodat die logica ook getest wordt.
from . import h_compliance as _HC

_AR = {}
_EXO_STAND = {('Get-HostedOutboundSpamFilterPolicy', 'Default'): {'AutoForwardingMode': 'Automatic'},
              ('Get-OrganizationConfig', ''): {'MailTipsExternalRecipientsTipsEnabled': True, 'OAuth2ClientProfileEnabled': True, 'AuditDisabled': False},
              ('Get-HostedContentFilterPolicy', 'Default'): {'SpamZapEnabled': True, 'PhishZapEnabled': True, 'HighConfidenceSpamAction': 'MoveToJmf',
                                                             'HighConfidencePhishAction': 'Quarantine', 'PhishSpamAction': 'MoveToJmf', 'BulkThreshold': 7},
              ('Get-MalwareFilterPolicy', 'Default'): {'EnableFileFilter': False},
              ('Get-OwaMailboxPolicy', 'OwaMailboxPolicy-Default'): {'AdditionalStorageProvidersAvailable': True},
              ('Get-AntiPhishPolicy', 'Office365 AntiPhish Default'): {'PhishThresholdLevel': 1, 'EnableMailboxIntelligence': True, 'EnableSpoofIntelligence': True}}
_FWD = [{'PrimarySmtpAddress': 'daan.visser@', 'DisplayName': 'Daan Visser', 'ForwardingSmtpAddress': 'smtp:daan.visser@gmail.com', 'DeliverToMailboxAndForward': True},
        {'PrimarySmtpAddress': 'facturen@', 'DisplayName': 'Facturen', 'ForwardingSmtpAddress': 'smtp:administratie@boekhouder-voorbeeld.nl', 'DeliverToMailboxAndForward': False},
        {'PrimarySmtpAddress': 'eva.smit@', 'DisplayName': 'Eva Smit', 'ForwardingAddress': 'Anna de Vries', 'DeliverToMailboxAndForward': True}]


class _NepExo:
    def run(self, cmdlet, **p):
        dom = _dom()
        if cmdlet == 'Get-Mailbox' and p.get('Filter'):
            return [{**f, 'PrimarySmtpAddress': f['PrimarySmtpAddress'] + dom} for f in _FWD]
        if cmdlet == 'Get-Mailbox':
            return [{'ExternalDirectoryObjectId': 'u15'}]
        if cmdlet.startswith('Get-'):
            v = _EXO_STAND.get((cmdlet, p.get('Identity', '')))
            return [dict(v)] if v is not None else []
        return []


_ROLLEN = [('r1', 'Global Administrator', '62e90394-69f5-4237-9190-012177145e10', ['u0', 'u7']), ('r2', 'Exchange Administrator', 'x', ['u1']),
           ('r3', 'User Administrator', 'y', ['u3'])]
_REG = {'u0': ['microsoftAuthenticatorPush', 'softwareOneTimePasscode'], 'u1': ['microsoftAuthenticatorPush'], 'u2': ['mobilePhone'], 'u3': [],
        'u4': ['microsoftAuthenticatorPush', 'fido2'], 'u6': ['windowsHelloForBusiness', 'microsoftAuthenticatorPush'], 'u7': ['mobilePhone'],
        'u8': ['microsoftAuthenticatorPush'], 'u9': [], 'u10': ['microsoftAuthenticatorPush'], 'u11': ['email'], 'u12': ['microsoftAuthenticatorPush'],
        'u13': ['microsoftAuthenticatorPush'], 'u14': ['softwareOneTimePasscode']}


def _apparaten_nep():
    namen = [('LT-KANTOOR-01', 'Windows', '10.0.26100.7171', True), ('LT-KANTOOR-02', 'Windows', '10.0.26200.7171', True), ('LT-KANTOOR-03', 'Windows', '10.0.26200.6899', True),
             ('PC-RECEPTIE', 'Windows', '10.0.22631.5909', False), ('LT-DIRECTIE', 'Windows', '10.0.26200.7171', True), ('PC-MAGAZIJN', 'Windows', '10.0.19045.6456', False),
             ('iPhone van Anna', 'iOS', '26.1', True), ('iPhone van Bram', 'iOS', '18.7.2', True), ('MacBook Eva', 'macOS', '26.1', True), ('Galaxy Kim', 'Android', '15', True)]
    nu = time.time()
    uit = []
    for i, (n, os_, v, enc) in enumerate(namen):
        uit.append({'id': f'md{i}', 'deviceName': n, 'operatingSystem': os_, 'osVersion': v, 'complianceState': 'noncompliant' if i in (3, 5) else 'compliant',
                    'isEncrypted': enc, 'userPrincipalName': NAMEN[i].split()[0].lower() + '@' + _dom(), 'userDisplayName': NAMEN[i],
                    'lastSyncDateTime': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(nu - (45 if i == 5 else i % 3) * 86400)),
                    'azureADDeviceId': f'aad-{i}', 'manufacturer': 'Lenovo' if os_ == 'Windows' else 'Apple', 'model': 'ThinkPad T14' if os_ == 'Windows' else '',
                    'managedDeviceOwnerType': 'company'})
    return uit


class _NepGraph:
    def get(self, pad):
        if pad.startswith('/security/secureScores'):
            reeks = []
            for d in range(30):
                reeks.append({'createdDateTime': time.strftime('%Y-%m-%dT00:00:00Z', time.gmtime(time.time() - d * 86400)),
                              'currentScore': 41.5 - d * 0.25 if d < 20 else 36.5, 'maxScore': 82,
                              'averageComparativeScores': [{'basis': 'AllTenants', 'averageScore': 38.2}, {'basis': 'TotalSeats', 'averageScore': 43.0}],
                              'controlScores': [{'controlName': k, 'score': sc} for k, _, sc, *_ in _PROF]})
            return {'value': reeks}
        if pad.startswith('/directoryRoles?'):
            return {'value': [{'id': r[0], 'displayName': r[1], 'roleTemplateId': r[2]} for r in _ROLLEN]}
        if pad.startswith('/policies/identitySecurityDefaultsEnforcementPolicy'):
            return {'isEnabled': False}
        if pad.startswith('/policies/authorizationPolicy'):
            return {'allowInvitesFrom': 'adminsGuestInvitersAndAllMembers', 'defaultUserRolePermissions': {'allowedToCreateApps': True,
                    'permissionGrantPoliciesAssigned': ['ManagePermissionGrantsForSelf.microsoft-user-default-legacy', 'ManagePermissionGrantsForOwnedResource.microsoft-dynamically-managed-permissions-for-team']}}
        return {}

    def all(self, pad):
        if pad.startswith('/security/secureScoreControlProfiles'):
            return [{'id': k, 'title': t, 'maxScore': mx, 'controlCategory': cat, 'service': srv, 'userImpact': imp, 'implementationCost': kost, 'rank': i + 1,
                     'remediation': '<p>Go to the admin center and change the setting as described.</p><ul><li>Step one</li><li>Step two</li></ul>',
                     'remediationImpact': 'Users may notice a change.', 'actionUrl': 'https://security.microsoft.com/securescore',
                     'controlStateUpdates': [{'state': 'Ignored'}] if k == 'aad_sign_in_risk_policy' else []}
                    for i, (k, t, sc, mx, cat, srv, imp, kost) in enumerate(_PROF)]
        if pad.startswith('/deviceManagement/managedDevices'):
            return _apparaten_nep()
        if pad.startswith('/devices'):
            return [{'id': 'e-extra', 'deviceId': 'aad-99', 'displayName': 'PC-OUD-BOEKHOUDING', 'operatingSystem': 'Windows', 'operatingSystemVersion': '10.0.19044.5011',
                     'approximateLastSignInDateTime': '2026-07-01T10:00:00Z', 'trustType': 'AzureAd', 'accountEnabled': True}, {'deviceId': 'aad-0', 'id': 'e0'}]
        if pad.startswith('/informationProtection/bitlocker'):
            return [{'deviceId': f'aad-{i}'} for i in (0, 1, 4)]
        if pad.startswith('/users?'):
            l = [{'id': u['id'], 'displayName': u['name'], 'userPrincipalName': u['upn'], 'accountEnabled': u['on'], 'userType': 'Guest' if u['guest'] else 'Member',
                  'assignedLicenses': [{'skuId': 'x'}] if u['lic'] else [], 'createdDateTime': '2024-02-01T10:00:00Z',
                  'externalUserState': 'Accepted' if u['guest'] else None,
                  'signInActivity': {'lastSignInDateTime': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - (140 if u['guest'] else int(u['id'][1:] or 0)) * 86400))}}
                 for u in _users(_dom())]
            l.append({'id': 'g2', 'displayName': 'Leverancier Test', 'userPrincipalName': 'lev_test.nl#EXT#@x.onmicrosoft.com', 'accountEnabled': True, 'userType': 'Guest',
                      'assignedLicenses': [], 'createdDateTime': '2026-11-20T10:00:00Z', 'externalUserState': 'PendingAcceptance'})
            return l
        if pad.startswith('/reports/authenticationMethods'):
            return [{'id': k, 'methodsRegistered': v} for k, v in _REG.items()]
        if pad.startswith('/identity/conditionalAccess'):
            return [{'displayName': 'MFA voor beheerders', 'state': 'enabled', 'conditions': {'users': {'includeRoles': ['62e90394-69f5-4237-9190-012177145e10']},
                     'applications': {'includeApplications': ['All']}}, 'grantControls': {'builtInControls': ['mfa']}},
                    {'displayName': 'MFA voor iedereen (test)', 'state': 'enabledForReportingButNotEnforced', 'conditions': {'users': {'includeUsers': ['All'], 'excludeUsers': ['u3']},
                     'applications': {'includeApplications': ['All']}}, 'grantControls': {'builtInControls': ['mfa']}}]
        if pad.startswith('/directoryRoles/'):
            rid = pad.split('/')[2]
            r = next(x for x in _ROLLEN if x[0] == rid)
            return [{'id': u, 'displayName': NAMEN[int(u[1:])], '@odata.type': '#microsoft.graph.user'} for u in r[3]]
        return []


# controlName, titel, huidige score, max, categorie, dienst, gebruikersimpact, kosten
_PROF = [
    ('AdminMFAV2', 'Ensure multifactor authentication is enabled for all users in administrative roles', 10, 10, 'Identity', 'AzureAD', 'Low', 'Low'),
    ('MFARegistrationV2', 'Ensure multifactor authentication is enabled for all users', 4, 9, 'Identity', 'AzureAD', 'Moderate', 'Moderate'),
    ('BlockLegacyAuthentication', 'Enable Conditional Access policies to block legacy authentication', 0, 8, 'Identity', 'AzureAD', 'Moderate', 'Moderate'),
    ('mdo_autoforwardingmode', 'Set action to take on outbound spam: block automatic forwarding', 0, 8, 'Apps', 'MDO', 'Moderate', 'Low'),
    ('IntegratedApps', 'Do not allow users to grant consent to unreliable applications', 0, 4, 'Apps', 'AzureAD', 'Moderate', 'Low'),
    ('mdo_commonattachmentsfilter', 'Ensure the common attachment types filter is enabled', 0, 5, 'Apps', 'MDO', 'Low', 'Low'),
    ('exo_storageproviderrestricted', 'Ensure additional storage providers are restricted in Outlook on the web', 0, 3, 'Data', 'EXO', 'Moderate', 'Low'),
    ('mdo_highconfidencespamaction', 'Move messages detected as high confidence spam to quarantine', 0, 3, 'Apps', 'MDO', 'Low', 'Low'),
    ('mdo_phishspamaction', 'Quarantine messages detected as phishing', 0, 3, 'Apps', 'MDO', 'Low', 'Low'),
    ('mdo_phisthresholdlevel', 'Set the phishing email level threshold at 2 or higher', 0, 3, 'Apps', 'MDO', 'Low', 'Low'),
    ('mdo_bulkthreshold', 'Set the email bulk complaint level (BCL) threshold to be 6 or lower', 0, 2, 'Apps', 'MDO', 'Moderate', 'Low'),
    ('PWAgePolicyNew', 'Set the password expiration policy to never expire', 0, 8, 'Identity', 'AzureAD', 'Low', 'Low'),
    ('aad_sign_in_risk_policy', 'Ensure that sign-in risk policy is configured', 0, 7, 'Identity', 'AzureAD', 'Moderate', 'Moderate'),
    ('mdo_zapspam', 'Ensure that Zero-hour auto purge for spam is enabled', 3, 3, 'Apps', 'MDO', 'Low', 'Low'),
    ('exo_mailboxaudit', 'Ensure mailbox auditing for all users is enabled', 5, 5, 'Apps', 'EXO', 'Low', 'Low'),
    ('aad_admin_consent_workflow', 'Turn on admin consent workflow', 0, 1.5, 'Apps', 'AzureAD', 'Low', 'Low'),
]


def _nep_ctx(c):
    ns = SimpleNamespace(g=_NepGraph(), x=_NepExo(), exo_ok=STAAT['tenant'] != 't-3333', L=c.L,
                         t=SimpleNamespace(id=STAAT['tenant'] or 't', domeinen=[{'id': _dom()}, {'id': _dom().split('.')[0] + '.onmicrosoft.com'}]))
    return ns


def _ss_apply(c, b):
    k = str(b.get('id')).lower()
    time.sleep(0.6)
    if k == 'mdo_autoforwardingmode':
        _EXO_STAND[('Get-HostedOutboundSpamFilterPolicy', 'Default')]['AutoForwardingMode'] = 'Off'
    elif k == 'mdo_commonattachmentsfilter':
        _EXO_STAND[('Get-MalwareFilterPolicy', 'Default')]['EnableFileFilter'] = True
    elif k == 'exo_storageproviderrestricted':
        _EXO_STAND[('Get-OwaMailboxPolicy', 'OwaMailboxPolicy-Default')]['AdditionalStorageProvidersAvailable'] = False
    elif k == 'mdo_highconfidencespamaction':
        _EXO_STAND[('Get-HostedContentFilterPolicy', 'Default')]['HighConfidenceSpamAction'] = 'Quarantine'
    c.L(f"Secure Score-actie toegepast ({b.get('id')}): {_HC.OPLOSSINGEN[k]['wat']} Microsoft werkt de score binnen 24-48 uur bij.")
    return {}


API['ss.list'] = lambda c, b: (time.sleep(0.5), _HC._secure(_nep_ctx(c)))[1]
API['ss.apply'] = _ss_apply
API['cd.devices'] = lambda c, b: (time.sleep(0.5), _HC._apparaten(_nep_ctx(c)))[1]
API['cu.users'] = lambda c, b: (time.sleep(0.6), _HC._gebruikers(_nep_ctx(c)))[1]


def _cu_fwd_off(c, b):
    _FWD[:] = [f for f in _FWD if not b['mailbox'].startswith(f['PrimarySmtpAddress'])]
    c.L(f"Doorsturen uitgezet voor {b['mailbox']}.")
    return {}


API['cu.forward.off'] = _cu_fwd_off


def _ar_get(c, b):
    return dict(_AR.get(b['mailbox'], {'state': 'Disabled', 'start': '', 'end': '', 'internal': '', 'external': '', 'audience': 'All'}))


def _ar_set(c, b):
    if b.get('state') == 'Disabled':
        oud = _AR.get(b['mailbox'], {})
        _AR[b['mailbox']] = {**_ar_get(c, b), **{k: v for k, v in oud.items()}, 'state': 'Disabled'}
        c.L(f"Automatisch antwoord staat uit voor {b['mailbox']}.")
    else:
        _AR[b['mailbox']] = {'state': b['state'], 'start': b.get('start') or '', 'end': b.get('end') or '', 'internal': b.get('internal') or '',
                             'external': b.get('external') or '', 'audience': b.get('audience') or 'All'}
        c.L(f"Automatisch antwoord {'gepland' if b['state'] == 'Scheduled' else 'staat aan'} voor {b['mailbox']}.")
    return {}


def _ar_overzicht(c, b):
    time.sleep(0.6)
    namen = {u['upn']: u['name'] for u in _users(_dom())}
    namen.update({s['mail']: s['name'] for s in API['shared.list'](c, b)['shared']})
    l = [{'mailbox': k, 'name': namen.get(k, k), 'shared': not k.split('@')[0].count('.'), **v} for k, v in _AR.items() if v['state'] != 'Disabled']
    return {'active': sorted(l, key=lambda r: r['name']), 'checked': len(namen)}


_AR['bram.jansen@korenaar.nl'] = {'state': 'Scheduled', 'start': '2026-12-21T08:00:00', 'end': '2027-01-04T17:00:00',
                                  'internal': 'Ik ben met kerstvakantie tot en met 4 januari.\nVoor dringende zaken: Anna de Vries.', 'external': '', 'audience': 'Known'}
API['ar.get'] = _ar_get
API['ar.set'] = _ar_set
API['ar.overzicht'] = _ar_overzicht


# ---------- Team- en eigen processen (v2.12.1): nep-SharePoint-lijst, de echte Opslag-logica draait erop ----------
import json as _json
from . import h_automatisering as _HA

_IK = {'id': 'ik', 'displayName': 'Beheerder Test'}
_COLLEGA = {'id': 'collega', 'displayName': 'Collega Test'}
_SP_ITEMS = {
    '1': {'by': _COLLEGA, 'def': {'name': 'Nieuwe medewerker kantoor', 'description': 'Account, Business Premium, groep Kantoor en postvak Info.', 'scope': 'team',
                                  'inputs': [{'key': 'voornaam', 'label': 'Voornaam'}], 'steps': [{'id': 'a1', 'block': 'rapport.regel', 'params': {'tekst': 'Welkom {{voornaam}}'}}]}},
    '2': {'by': _COLLEGA, 'def': {'name': 'Eigen test van collega', 'description': 'Hoort niet zichtbaar te zijn.', 'scope': 'eigen', 'inputs': [], 'steps': []}},
    '3': {'by': _IK, 'def': {'name': 'Mijn proefproces', 'description': 'Nog aan het testen.', 'scope': 'eigen', 'inputs': [],
                             'steps': [{'id': 'b1', 'block': 'rapport.regel', 'params': {'tekst': 'Test'}}]}},
}


class _NepSP:
    def get(self, pad):
        if pad.startswith('/me'):
            return _IK
        if pad.startswith('/sites/root'):
            return {'id': 'site'}
        if '/lists?' in pad:
            return {'value': [{'id': 'lijst'}]}
        did = pad.split('/items/')[1].split('?')[0]
        it = _SP_ITEMS[did]
        return {'id': did, 'createdBy': {'user': it['by']}, 'fields': {'Definitie': _json.dumps(it['def'])}}

    def all(self, pad):
        return [{'id': k, 'createdBy': {'user': v['by']}, 'lastModifiedBy': {'user': v.get('mod', v['by'])}, 'lastModifiedDateTime': '2026-11-26T10:00:00Z',
                 'fields': {'Title': v['def']['name'], 'Definitie': _json.dumps(v['def'])}} for k, v in _SP_ITEMS.items()]

    def post(self, pad, body):
        did = str(max(int(k) for k in _SP_ITEMS) + 1)
        _SP_ITEMS[did] = {'by': _IK, 'def': _json.loads(body['fields']['Definitie'])}
        return {'id': did}

    def patch(self, pad, body):
        did = pad.split('/items/')[1].split('/')[0]
        _SP_ITEMS[did]['def'] = _json.loads(body['Definitie'])
        _SP_ITEMS[did]['mod'] = _IK
        return {}

    def delete(self, pad):
        _SP_ITEMS.pop(pad.split('/items/')[1], None)
        return {}


_HA.OPSLAG._g = lambda c: _NepSP()


# ---------- DNS bij Microsoft (v2.12.1) ----------
_dom_get_oud = API['dom.get']


def _dom_get_ms(c, b):
    d = _dom_get_oud(c, b)
    if b['id'] == 'korenaar.nl':
        d.update(nameservers=['ns1.bdm.microsoftonline.com', 'ns2.bdm.microsoftonline.com', 'ns3.bdm.microsoftonline.com', 'ns4.bdm.microsoftonline.com'],
                 msDns=True, links={'klant': 'https://admin.microsoft.com/Partner/BeginClientSession.aspx?CTID=t-1111&CSDEST=o365admincenter',
                                    'dns': 'https://admin.microsoft.com/?delegatedOrg=korenaar.onmicrosoft.com#/Domains/Details/korenaar.nl'},
                 zone=[{'type': 'A', 'name': 'korenaar.nl', 'value': '203.0.113.10', 'ttl': 3600},
                       {'type': 'MX', 'name': 'korenaar.nl', 'value': '0 korenaar-nl.mail.protection.outlook.com', 'ttl': 3600},
                       {'type': 'TXT', 'name': 'korenaar.nl', 'value': 'v=spf1 include:spf.protection.outlook.com -all', 'ttl': 3600},
                       {'type': 'CNAME', 'name': 'www.korenaar.nl', 'value': 'korenaar.voorbeeldhosting.nl', 'ttl': 3600},
                       {'type': 'CNAME', 'name': 'autodiscover.korenaar.nl', 'value': 'autodiscover.outlook.com', 'ttl': 3600},
                       {'type': 'CNAME', 'name': 'enterpriseregistration.korenaar.nl', 'value': 'enterpriseregistration.windows.net', 'ttl': 3600},
                       {'type': 'SRV', 'name': '_sip._tls.korenaar.nl', 'value': '100 1 443 sipdir.online.lync.com', 'ttl': 3600}])
    else:
        d.update(nameservers=['ns1.voorbeeld-dns.nl', 'ns2.voorbeeld-dns.nl'], msDns=False)
    return d


API['dom.get'] = _dom_get_ms


# ---------- Copilot-readiness en NEN 7510 (v2.13) ----------
from . import h_readiness as _HR


def _rd_ctx(c):
    ns = _nep_ctx(c)
    ns.t.cache = lambda k, fn, ttl=0, vers=False: fn()
    ns.t.weg = lambda *k: None
    return ns


def _rd_feiten(c):
    n = _rd_ctx(c)
    return {'users': _HC._gebruikers(n), 'devices': _HC._apparaten(n),
            'sp': {'SharingCapability': 2, 'DefaultSharingLinkType': 2, 'DefaultLinkPermission': 2, 'OneDriveSharingCapability': 1},
            'groups': [{'displayName': 'Kantoor', 'visibility': 'Public'}, {'displayName': 'Directie', 'visibility': 'Private'}, {'displayName': 'Projecten', 'visibility': 'Public'}],
            'skus': [{'part': 'SPB', 'name': 'Microsoft 365 Business Premium', 'total': 14, 'used': 13},
                     {'part': 'Microsoft_365_Copilot', 'name': 'Microsoft 365 Copilot', 'total': 2, 'used': 1}],
            'labels': None, 'cpol': [{'id': 'p1', 'displayName': 'Windows - basis'}],
            'exo': {'audit': {'UnifiedAuditLogIngestionEnabled': False}, 'org': {'AuditDisabled': False}, 'ext': [{'Enabled': False}],
                    'out': _EXO_STAND[('Get-HostedOutboundSpamFilterPolicy', 'Default')], 'mal': _EXO_STAND[('Get-MalwareFilterPolicy', 'Default')],
                    'dkim': [{'Domain': _dom(), 'Enabled': True}], 'dom': [{'DomainName': _dom()}, {'DomainName': _dom().split('.')[0] + '.onmicrosoft.com'}]},
            'mail': {_dom(): {'spf': ['v=spf1 include:spf.protection.outlook.com -all'], 'dmarc': ['v=DMARC1; p=none']}},
            'auth': {}, '_fout': {'labels': 'Forbidden (testmodus)'}}


_HR._feiten = _rd_feiten
API['rd.copilot'] = lambda c, b: (time.sleep(0.6), _HR._rapport(_rd_ctx(c), 'copilot'))[1]
API['rd.nen'] = lambda c, b: (time.sleep(0.6), _HR._rapport(_rd_ctx(c), 'nen'))[1]


def _rd_apply(c, b):
    k = b.get('key')
    time.sleep(0.5)
    if k == 'autoforward':
        _EXO_STAND[('Get-HostedOutboundSpamFilterPolicy', 'Default')]['AutoForwardingMode'] = 'Off'
    elif k == 'attachments':
        _EXO_STAND[('Get-MalwareFilterPolicy', 'Default')]['EnableFileFilter'] = True
    c.L(f"Toegepast: {_HR.FIXES[k]['what']}")
    return {}


API['rd.apply'] = _rd_apply
API['cd.cleanup'] = lambda c, b: (time.sleep(0.6), [c.L(f"{d.get('name')}: {'uitgeschakeld in Entra ID' if b['action'] == 'disable' else 'verwijderd'} (testmodus).") for d in b.get('items') or []],
                                  {'results': [f"{d.get('name')}: gelukt (testmodus)" for d in b.get('items') or []], 'failed': 0})[2]


# ---------- Archief en retentie (v2.13) ----------
from . import h_retentie as _HRT

_RT_TAGS = [
    {'Name': 'Default 2 year move to archive', 'Type': 'All', 'AgeLimitForRetention': '730.00:00:00', 'RetentionAction': 'MoveToArchive', 'RetentionEnabled': True, 'SystemTag': False},
    {'Name': 'Recoverable Items 14 days move to archive', 'Type': 'RecoverableItems', 'AgeLimitForRetention': '14.00:00:00', 'RetentionAction': 'MoveToArchive', 'RetentionEnabled': True},
    {'Name': 'Personal 1 year move to archive', 'Type': 'Personal', 'AgeLimitForRetention': '365.00:00:00', 'RetentionAction': 'MoveToArchive', 'RetentionEnabled': True},
    {'Name': 'Deleted Items', 'Type': 'DeletedItems', 'AgeLimitForRetention': '30.00:00:00', 'RetentionAction': 'DeleteAndAllowRecovery', 'RetentionEnabled': True},
    {'Name': 'Never Delete', 'Type': 'Personal', 'AgeLimitForRetention': None, 'RetentionAction': 'DeleteAndAllowRecovery', 'RetentionEnabled': False},
]
_RT_POL = [{'Name': 'Default MRM Policy', 'IsDefault': True, 'RetentionPolicyTagLinks': [t['Name'] for t in _RT_TAGS if t['Name'] != 'Deleted Items']},
           {'Name': 'Zorg 7 jaar', 'IsDefault': False, 'RetentionPolicyTagLinks': ['Default 2 year move to archive', 'Deleted Items']}]
_RT_MB = {}


class _NepRetExo:
    def _vul(self):
        dom = _dom()
        for i, u in enumerate(_users(dom)):
            if not u['guest']:
                _RT_MB[u['upn']] = {'DisplayName': u['name'], 'PrimarySmtpAddress': u['upn'], 'RecipientTypeDetails': 'UserMailbox',
                                    'RetentionPolicy': 'Zorg 7 jaar' if i % 5 == 0 else 'Default MRM Policy',
                                    'ArchiveGuid': '11111111-0000-0000-0000-%012d' % i if i % 3 == 0 else _HRT.LEGE_GUID,
                                    'AutoExpandingArchiveEnabled': i == 0, 'RetentionHoldEnabled': i == 4, 'ArchiveQuota': '100 GB (107,374,182,400 bytes)',
                                    'ProhibitSendReceiveQuota': '50 GB (53,687,091,200 bytes)'}
        for sh in [{'name': 'Info', 'mail': 'info@' + dom}, {'name': 'Facturen', 'mail': 'facturen@' + dom}]:
            _RT_MB[sh['mail']] = {'DisplayName': sh['name'], 'PrimarySmtpAddress': sh['mail'], 'RecipientTypeDetails': 'SharedMailbox',
                                  'RetentionPolicy': 'Default MRM Policy', 'ArchiveGuid': _HRT.LEGE_GUID}

    def run(self, cmdlet, **p):
        if not _RT_MB:
            self._vul()
        if cmdlet == 'Get-Mailbox':
            return [_RT_MB[p['Identity']]] if p.get('Identity') else list(_RT_MB.values())
        if cmdlet == 'Get-MailboxStatistics':
            return [{'TotalItemSize': '3.1 GB (3,328,599,654 bytes)' if p.get('Archive') else '12.48 GB (13,400,000,000 bytes)',
                     'ItemCount': 9120 if p.get('Archive') else 48211}]
        if cmdlet == 'Get-RetentionPolicy':
            return _RT_POL
        if cmdlet == 'Get-RetentionPolicyTag':
            return _RT_TAGS
        if cmdlet == 'Get-OrganizationConfig':
            return [{'AutoExpandingArchiveEnabled': False}]
        mb = _RT_MB.get(p.get('Identity'))
        if cmdlet == 'Enable-Mailbox' and p.get('Archive'):
            mb['ArchiveGuid'] = '22222222-0000-0000-0000-000000000000'
        elif cmdlet == 'Enable-Mailbox' and p.get('AutoExpandingArchive'):
            mb['AutoExpandingArchiveEnabled'] = True
        elif cmdlet == 'Disable-Mailbox':
            mb['ArchiveGuid'] = _HRT.LEGE_GUID
        elif cmdlet == 'Set-Mailbox':
            mb.update({k: v for k, v in p.items() if k in ('RetentionPolicy', 'RetentionHoldEnabled')})
        elif cmdlet == 'New-RetentionPolicy':
            _RT_POL.append({'Name': p['Name'], 'IsDefault': False, 'RetentionPolicyTagLinks': p.get('RetentionPolicyTagLinks') or []})
        elif cmdlet == 'Set-RetentionPolicy':
            pol = next(x for x in _RT_POL if x['Name'] == p['Identity'])
            if 'IsDefault' in p:
                for x in _RT_POL:
                    x['IsDefault'] = x is pol
            if 'RetentionPolicyTagLinks' in p:
                pol['RetentionPolicyTagLinks'] = p['RetentionPolicyTagLinks']
            if p.get('Name'):
                pol['Name'] = p['Name']
        elif cmdlet == 'Remove-RetentionPolicy':
            _RT_POL[:] = [x for x in _RT_POL if x['Name'] != p['Identity']]
        elif cmdlet == 'New-RetentionPolicyTag':
            _RT_TAGS.append({'Name': p['Name'], 'Type': p['Type'], 'AgeLimitForRetention': p['AgeLimitForRetention'], 'RetentionAction': p['RetentionAction'],
                             'RetentionEnabled': p['RetentionEnabled'], 'Comment': p.get('Comment')})
        elif cmdlet == 'Set-RetentionPolicyTag':
            t = next(x for x in _RT_TAGS if x['Name'] == p['Identity'])
            t.update({k: v for k, v in p.items() if k in ('AgeLimitForRetention', 'RetentionAction', 'RetentionEnabled', 'Comment')})
            if p.get('Name'):
                t['Name'] = p['Name']
        elif cmdlet == 'Remove-RetentionPolicyTag':
            _RT_TAGS[:] = [x for x in _RT_TAGS if x['Name'] != p['Identity']]
        return []

    def een(self, cmdlet, **p):
        r = self.run(cmdlet, **p)
        return r[0] if r else None


def _rt_ctx(c):
    ns = _rd_ctx(c)
    ns.x = _NepRetExo()
    return ns


def _rt_wrap(f):
    return lambda c, b: (time.sleep(0.3), f(_rt_ctx(c), b))[1]


for _n in ('ret.list', 'ret.mailbox', 'ret.mailbox.set', 'ret.policy.save', 'ret.policy.delete', 'ret.tag.save', 'ret.tag.delete'):
    API[_n] = _rt_wrap(getattr(_HRT, _n.replace('.', '_')))


# ---------- Doorsturen per postvak (v2.13) ----------
_FWD_MB = {}
API['fwd.get'] = lambda c, b: {**{'on': False, 'to': '', 'keep': True, 'external': False}, **_FWD_MB.get(b['mailbox'], {}),
                               'mode': _EXO_STAND[('Get-HostedOutboundSpamFilterPolicy', 'Default')]['AutoForwardingMode'], 'domains': [_dom()]}


def _fwd_set(c, b):
    if b.get('on'):
        _FWD_MB[b['mailbox']] = {'on': True, 'to': b['to'], 'keep': b.get('keep', True), 'external': not b['to'].endswith(_dom())}
        c.L(f"Doorsturen aangezet voor {b['mailbox']} naar {b['to']}.")
    else:
        _FWD_MB.pop(b['mailbox'], None)
        c.L(f"Doorsturen uitgezet voor {b['mailbox']}.")
    return {}


API['fwd.set'] = _fwd_set


# ---------- Back-up (v2.14) ----------
_BK_KEYS = {'datto': True, 'unitrends': False}
_BK_CHECKS = [{'id': '1', 'customer': 'Advocatenkantoor De Wit', 'result': 'OK', 'note': '', 'ticket': '', 'at': '2026-11-25T08:10:00Z', 'by': 'Collega Test'}]


def _bk_overzicht(c, b):
    from datetime import datetime, timedelta, timezone
    nu = datetime.now(timezone.utc)
    iso = lambda h: (nu - timedelta(hours=h)).isoformat()  # noqa: E731
    rij = lambda bron, klant, naam, soort, st, h, msg='': {'source': bron, 'customer': klant, 'name': naam, 'kind': soort, 'status': st,  # noqa: E731
                                                           'lastOk': iso(h) if h is not None else '', 'last': iso(min(h or 1, 2)), 'message': msg}
    items = [
        rij('Datto BCDR', 'Bakkerij De Korenaar', 'SIRIS-KORENAAR (appliance)', 'Appliance', 'ok', 0.2),
        rij('Datto BCDR', 'Bakkerij De Korenaar', 'SRV-DC01', 'Agent', 'ok', 3),
        rij('Datto BCDR', 'Bakkerij De Korenaar', 'SRV-APP01', 'Agent', 'err', 80, 'VSS writer failed: SqlServerWriter.'),
        rij('Datto SaaS Protection', 'Bakkerij De Korenaar', 'Microsoft 365 - Exchange', 'SaaS', 'ok', None),
        rij('Datto SaaS Protection', 'Bakkerij De Korenaar', 'Microsoft 365 - OneDrive', 'SaaS', 'warn', None, 'Laatste status: Partial'),
        rij('Datto Endpoint Backup', 'Advocatenkantoor De Wit', 'LT-DEWIT-01', 'Endpoint', 'ok', 5),
        rij('Datto Endpoint Backup', 'Advocatenkantoor De Wit', 'LT-DEWIT-02', 'Endpoint', 'warn', 40, 'Laatste geslaagde back-up 40 uur geleden.'),
        rij('Datto SaaS Protection', 'Advocatenkantoor De Wit', 'Microsoft 365 - Exchange', 'SaaS', 'ok', None),
        rij('Unitrends', 'Installatiebedrijf Bos', 'UEB-BOS (appliance)', 'Appliance', 'ok', None),
        rij('Unitrends', 'Installatiebedrijf Bos', 'FILESRV', 'Windows', 'ok', 9),
        rij('Datto SaaS Protection', 'Stichting Zorgpunt', 'Microsoft 365 - SharePoint', 'SaaS', 'ok', None),
        rij('Datto Endpoint Backup', 'Stichting Zorgpunt', 'PC-RECEPTIE', 'Endpoint', 'paused', None, 'Back-up staat op pauze.'),
    ] + [rij('Datto Endpoint Backup', 'Justdata', n, 'Endpoint', st, h) for n, st, h in (
        ('KOR-LT-01', 'ok', 4), ('KOR-LT-02', 'ok', 6), ('WIT-PC-03', 'ok', 2), ('BOS-WS-01', 'err', 90), ('ZORG-LT-07', 'ok', 8),
        ('MEIJER-PC-01', 'warn', 30), ('NOORD-LT-02', 'ok', 3))]
    from . import h_backup as _hb
    toew = _hb.toewijzingen()
    for it in items:
        if it['source'] == 'Datto SaaS Protection':
            it['saasId'] = 'saas-' + it['customer'].split()[-1].lower()
        it['key'] = _hb.item_sleutel(it)
        if toew.get(it['key']):
            it.update(origin=it['customer'], customer=toew[it['key']])
    volgorde = {'err': 0, 'warn': 1, 'unknown': 2, 'paused': 3, 'ok': 4}
    kl = {}
    for it in items:
        k = kl.setdefault(it['customer'], {'name': it['customer'], 'sources': set(), 'counts': {'ok': 0, 'warn': 0, 'err': 0, 'unknown': 0, 'paused': 0}, 'items': []})
        k['sources'].add(it['source']); k['counts'][it['status']] += 1; k['items'].append(it)
    uit = []
    for k in kl.values():
        k['items'].sort(key=lambda x: volgorde[x['status']])
        k['status'] = 'err' if k['counts']['err'] else 'warn' if k['counts']['warn'] else 'ok'
        k['sources'] = sorted(k['sources'])
        uit.append(k)
    uit.sort(key=lambda k: (volgorde[k['status']], k['name']))
    time.sleep(0.6)
    return {'customers': uit, 'errors': {}, 'sources': ['Datto BCDR', 'Datto Endpoint Backup', 'Datto SaaS Protection', 'Unitrends'], 'at': '12:00', 'configured': True,
            'busy': False, 'progress': {'Datto BCDR': {'status': 'klaar', 'count': 3, 'sec': 17}, 'Datto Endpoint Backup': {'status': 'klaar', 'count': 4, 'sec': 1}, 'Datto SaaS Protection': {'status': 'klaar', 'count': 4, 'sec': 29}}}


def _bk_afvinken(c, b):
    for k in b['customers']:
        _BK_CHECKS.append({'id': str(len(_BK_CHECKS) + 1), 'customer': k, 'result': b['result'], 'note': b.get('note', ''), 'ticket': b.get('ticket', ''),
                           'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'by': 'Beheerder Test'})
    c.L(f"Back-upcontrole afgevinkt voor {len(b['customers'])} klant(en): {b['result']}.")
    return {'storage': 'sharepoint'}


API['bk.keys.status'] = lambda c, b: {'sources': [{'key': k, 'name': n, 'fields': [{'key': 'a', 'label': 'Sleutel'}, {'key': 'b', 'label': 'Geheim'}],
                                                    'help': 'Testmodus.', 'set': _BK_KEYS[k]} for k, n in (('datto', 'Datto'), ('unitrends', 'Unitrends (UniView)'))]}
API['bk.keys.set'] = lambda c, b: (_BK_KEYS.__setitem__(b['source'], True), c.L('Sleutels opgeslagen (testmodus).'), {})[2]
API['bk.keys.delete'] = lambda c, b: (_BK_KEYS.__setitem__(b['source'], False), {})[1]
API['bk.overzicht'] = _bk_overzicht
from . import h_backup as _HBK
_BK_TOEW: dict = {}
_HBK.toewijzingen = lambda: dict(_BK_TOEW)
_HBK.toewijzingen_opslaan = lambda m: (_BK_TOEW.clear(), _BK_TOEW.update(m))
API['bk.controles'] = lambda c, b: {'checks': list(_BK_CHECKS), 'storage': 'sharepoint'}
API['bk.afvinken'] = _bk_afvinken


# SaaS Protection per onderdeel: nep-Datto voor /saas/{id}/seats, de echte verwerking (bk.saas.seats) draait erop
def _bk_seats(pad, params=None):
    import re as _re
    if not _re.search(r'/seats$', pad):
        return []
    from datetime import datetime, timedelta, timezone
    nu = datetime.now(timezone.utc)
    t = params.get('seatType')
    data = {
        'User': [('Anna de Vries', 'anna@korenaar.nl', 'Active', 'Success', 3), ('Bram Jansen', 'bram@korenaar.nl', 'Active', 'Failed', 50),
                 ('Chantal Smit', 'chantal@korenaar.nl', 'Paused', '', None), ('Dirk Bakker', 'dirk@korenaar.nl', 'Active', 'Partial', 30)],
        'SharedMailbox': [('Info', 'info@korenaar.nl', 'Active', 'Success', 2)],
        'Site': [('Intranet', 'https://korenaar.sharepoint.com/sites/intranet', 'Active', 'Success', 5)],
        'Team': [('Directie', 'directie@korenaar.nl', 'Active', 'Success', 4), ('Productie', 'productie@korenaar.nl', 'Unprotected', '', None)],
    }.get(t, [])
    return [{'name': n, 'mainId': m, 'seatState': s, 'backupStatus': b or None, 'remoteId': f'r{i}', 'seatType': t,
             'lastBackupDate': (nu - timedelta(hours=h)).isoformat() if h is not None else None} for i, (n, m, s, b, h) in enumerate(data)]


_HBK._datto_alle = _bk_seats


# ---------- Autotask (v2.15): echte werkregistratie in het geheugen, Autotask zelf nagebootst ----------
from . import h_autotask as _HAT
from .clients import ApiFout

_AT_KLANTEN = {'t-1111': {'companyId': 101, 'name': 'Bakkerij De Korenaar B.V.'}}
_AT_INST = dict(_HAT.STANDAARD_INSTELLINGEN, statusKlaar=5, status=1, priority=2, queueID=29682833)
_HAT._sleutel = lambda: ('api@voorbeeld.nl', 'x', 'y')
_HAT._klanten = lambda: _AT_KLANTEN
_HAT._instellingen = lambda: _AT_INST
_AT_TICKETS = [{'id': 9001, 'number': 'T20261126.0042', 'title': 'Nieuwe medewerker verkoop', 'status': 'Nieuw', 'mine': True, 'assignedResourceroleID': 1},
               {'id': 9002, 'number': 'T20261125.0013', 'title': 'Licenties controleren', 'status': 'In behandeling', 'mine': False, 'assignedResourceroleID': 1}]


def _at_boek(c, b):
    tid = str(b.get('tid') or c.tid)
    s = _HAT._SESSIES.get(tid)
    if not s or not s['items']:
        return {'booked': 0}
    items = [i for i in s['items'] if not i['skip']]
    if s['mode'] not in ('ticket', 'auto') or not items:
        raise ApiFout('Kies eerst een ticket of "automatisch nieuw ticket" in de ticketbalk.')
    time.sleep(0.6)
    if not s['ticket']:
        s['ticket'] = {'id': 9100, 'number': 'T20261126.0077', 'title': _HAT._titel(items, s['klant'])}
        ct = s.get('contact')
        c.L(f"(testmodus) Nieuw ticket met contactpersoon {ct['name']} (ID {ct['id']})." if ct else '(testmodus) Nieuw ticket zonder contactpersoon.')
    m = _HAT._afgerond(sum(float(i['minuten']) for i in items))
    nr = s['ticket']['number']
    _HAT._GEBOEKT.insert(0, {'at': time.strftime('%d-%m %H:%M'), 'klant': s['klant'], 'ticket': nr, 'titel': s['ticket']['title'], 'minuten': m, 'acties': len(items),
                             'wie': 'handmatig' if not b.get('wissel') else 'bij wisselen van klant'})
    s['items'] = []
    if s['mode'] == 'auto':
        s['ticket'] = None
    c.L(f"{len(items)} actie(s) geboekt op Autotask-ticket {nr} ({m} min).")
    return {'booked': len(items), 'minutes': m, 'ticket': nr}


def _at_boek_sluit(c, b):
    tid = str(b.get('tid') or c.tid)
    s = _HAT._SESSIES.get(tid) or {}
    t = s.get('ticket') or {'number': 'T20261126.0077'}
    r = _at_boek(c, b) if s.get('items') else {'booked': 0}
    if b.get('sluit') in ('complete', 'invoice') and s:
        s.update(ticket=None, vorig=None, licentie=False)
        if s.get('mode') == 'ticket':
            s['mode'] = None
        c.L(f"(testmodus) Ticket {t.get('number')} afgerond: {'Ready to Invoice' if b['sluit'] == 'invoice' else 'Complete'}. Oplossing: {b.get('resolution', '')}")
        r['closed'] = b['sluit']
    return r


API['at.boek'] = _at_boek_sluit


def _sd_afsluiten(c, b):
    items = b.get('items') or []
    for x in items:
        if len(str(x.get('text') or '').strip()) < 5 or x.get('end') not in ('complete', 'invoice'):
            raise ApiFout('Vul bij elk ticket de oplossing in en kies Afgerond of Klaar voor facturatie.')
    time.sleep(0.8)
    res = [{'id': x['id'], 'number': f"T20261127.{int(x['id']):04d}", 'ok': True, 'end': x['end']} for x in items]
    c.L(f"(testmodus) {len(res)} ticket(s) afgerond: " + ', '.join(f"{r['number']} {'Ready to Invoice' if r['end'] == 'invoice' else 'Complete'}" for r in res))
    return {'results': res, 'ok': len(res), 'failed': 0}


API['sd.afsluiten'] = _sd_afsluiten
API['sd.zoek'] = lambda c, b: (time.sleep(0.4), {
    'tickets': [t for t in [{'id': 9001, 'number': 'T20261126.0042', 'title': 'Nieuwe medewerker verkoop', 'status': 'New', 'company': 'Bakkerij De Korenaar B.V.', 'url': ''},
                            {'id': 9002, 'number': 'T20261125.0013', 'title': 'Licenties controleren', 'status': 'In Progress', 'company': 'Advocatenkantoor De Wit', 'url': ''}]
                if str(b.get('q') or '').lower() in (t['number'] + ' ' + t['title']).lower()],
    'companies': [x for x in [{'id': 101, 'name': 'Bakkerij De Korenaar B.V.'}, {'id': 102, 'name': 'Installatiebedrijf Bos'}] if str(b.get('q') or '').lower() in x['name'].lower()]})[1]
API['at.opties'] = lambda c, b: {'status': [{'value': 1, 'label': 'Nieuw'}, {'value': 5, 'label': 'Afgehandeld'}], 'priority': [{'value': 2, 'label': 'Normaal'}],
                                  'queueID': [{'value': 29682833, 'label': 'Servicedesk'}], 'issueType': [{'value': 7, 'label': 'Microsoft 365'}],
                                  'subIssueType': [{'value': 70, 'label': 'Gebruikersbeheer', 'parent': 7}], 'source': [{'value': 4, 'label': 'Intern'}],
                                  'ticketCategory': [{'value': 3, 'label': 'Standaard'}], 'noteType': [{'value': 1, 'label': 'Taakdetail'}],
                                  'publish': [{'value': 1, 'label': 'Alle Autotask-gebruikers'}, {'value': 2, 'label': 'Alleen intern'}],
                                  'billingCodes': [{'value': 29682801, 'label': 'Remote support'}]}
API['at.bedrijven'] = lambda c, b: {'companies': [{'id': 101, 'name': 'Bakkerij De Korenaar B.V.', 'web': 'korenaar.nl'}, {'id': 102, 'name': 'Advocatenkantoor De Wit', 'web': 'dewit.nl'}]}
API['at.tickets'] = lambda c, b: (time.sleep(0.4), {'tickets': [t for t in _AT_TICKETS if not b.get('q') or b['q'].upper() in t['number'] or b['q'].lower() in t['title'].lower()]})[1]
API['at.klant.set'] = lambda c, b: (_AT_KLANTEN.__setitem__(str(b.get('tid') or c.tid), {'companyId': b['companyId'], 'name': b.get('name')}) if b.get('companyId') is not None
                                    else _AT_KLANTEN.pop(str(b.get('tid') or c.tid), None), {})[1]
API['at.keys.set'] = lambda c, b: (c.L('Autotask gekoppeld (testmodus).'), {})[1]
API['at.settings.save'] = lambda c, b: (_AT_INST.update(b.get('settings') or {}), c.L('Autotask-instellingen opgeslagen (testmodus).'), {})[2]
_HAT._ik = lambda at: {'id': 30, 'name': 'Beheerder Test', 'role': 1, 'mail': 'beheerder@voorbeeld.nl'}


class _NepAutotask:
    """Alleen contactpersonen (v2.22) en PATCH op tickets; de echte code van h_autotask draait erop."""
    contacten = [{'id': 501, 'companyID': 101, 'firstName': 'Sanne', 'lastName': 'Voorbeeld', 'emailAddress': 'sanne@korenaar.nl', 'phone': '0201234567', 'isActive': 1},
                 {'id': 502, 'companyID': 101, 'firstName': 'Pieter', 'lastName': 'Test', 'emailAddress': 'pieter@korenaar.nl', 'title': 'Office manager', 'isActive': 1},
                 {'id': 503, 'companyID': 101, 'firstName': 'Oud', 'lastName': 'Contact', 'emailAddress': 'oud@korenaar.nl', 'isActive': 0}]

    projecten: list = []
    taken: list = []
    _STATUS = [{'value': 1, 'label': 'New'}, {'value': 2, 'label': 'In Progress'}, {'value': 5, 'label': 'Complete'}]

    def picklists(self, entiteit):
        return {'status': [dict(s, default=False, parent=None) for s in self._STATUS]} if entiteit in ('Projects', 'Tasks') else {}

    def query(self, entiteit, filters, velden=None, max_=500, limiet=2000):
        bron = {'Contacts': self.contacten, 'Projects': self.projecten, 'Tasks': self.taken}.get(entiteit)
        if bron is None:
            return []
        time.sleep(0.3)
        uit = bron
        for f in filters:
            w = f['value']
            if f['op'] == 'noteq':
                uit = [x for x in uit if str(x.get(f['field'], '')).lower() != str(w).lower()]
            elif f['op'] == 'in':
                uit = [x for x in uit if x.get(f['field']) in w]
            else:
                uit = [x for x in uit if str(x.get(f['field'], '')).lower() == str(w).lower()]
        return uit

    def req(self, methode, pad, body=None):
        time.sleep(0.3)
        if methode == 'POST' and pad.endswith('Contacts'):
            nid = 500 + len(self.contacten) + 1
            self.contacten.append({**body, 'id': nid})
            return {'itemId': nid}
        return {}


_NEP_AT = _NepAutotask()
_HAT._at = lambda: _NEP_AT

_AT_MW = {}
API['at.medewerkers'] = lambda c, b: {'resources': [{'id': 30, 'name': 'Beheerder Test', 'email': 'beheerder@voorbeeld.nl'}, {'id': 31, 'name': 'Servicedesk Medewerker', 'email': 'servicedesk@voorbeeld.nl'},
                                                    {'id': 32, 'name': 'Collega Test', 'email': ''}], 'mapping': _AT_MW}
API['at.medewerker.set'] = lambda c, b: ((_AT_MW.__setitem__(b['email'].lower(), {'id': b['resourceId'], 'name': b.get('name')}) if b.get('resourceId') is not None
                                          else _AT_MW.pop(b['email'].lower(), None)), {'mapping': _AT_MW})[1]


# ---------- App-beheer: in testmodus is de testbeheerder app-beheerder ----------
from . import rechten as _RCH
_RCH.BEHEERDERS.add(__import__('hashlib').sha256(b'beheerder@voorbeeld.nl').hexdigest())
_RCH.DIRECTIE.add(__import__('hashlib').sha256(b'beheerder@voorbeeld.nl').hexdigest())
_RCH.FACTURATIE.add(__import__('hashlib').sha256(b'beheerder@voorbeeld.nl').hexdigest())
_RCH.SALES_INZIEN.add(__import__('hashlib').sha256(b'beheerder@voorbeeld.nl').hexdigest())
_RCH.SALES_INVOEREN.add(__import__('hashlib').sha256(b'beheerder@voorbeeld.nl').hexdigest())
API['app.rol'] = lambda c, b: {'admin': True, 'justdata': True, 'directie': True, 'billing': True}
API['bk.keys.status'] = (lambda f: lambda c, b: {**f(c, b), 'admin': True})(API['bk.keys.status'])


# ---------- E-mailbeveiliging (DMARC, v2.16): echte beoordeling op nagebootste EasyDMARC-gegevens ----------
from . import h_dmarc as _HDM


def _dm_nep():
    ruw = {
        'Bakkerij De Korenaar': [{'domain': 'korenaar.nl', 'policy': 'quarantine', 'spf': 'valid', 'dkim': 'valid', 'dmarc': 'valid', 'volume': 4210, 'spf_pass_rate': 97.2,
                                  'dkim_pass_rate': 95.1, 'dmarc_compliance': {'overall_compliance': 96.4}, 'type': 'sending', 'domain_verified': True},
                                 {'domain': 'bakkerij-korenaar.nl', 'policy': 'none', 'spf': 'warning', 'dkim': 'no-record', 'dmarc': 'valid', 'volume': 310, 'spf_pass_rate': 70,
                                  'dkim_pass_rate': 0, 'dmarc_compliance': {'overall_compliance': 68.2}, 'type': 'sending', 'domain_verified': True}],
        'Advocatenkantoor De Wit': [{'domain': 'dewit-advocaten.nl', 'policy': 'reject', 'spf': 'valid', 'dkim': 'valid', 'dmarc': 'valid', 'volume': 12880,
                                     'spf_pass_rate': 99.6, 'dkim_pass_rate': 99.8, 'dmarc_compliance': {'overall_compliance': 99.7}, 'type': 'sending', 'domain_verified': True}],
        'Stichting Zorgpunt': [{'domain': 'zorgpunt.nl', 'policy': 'missing', 'spf': 'valid', 'dkim': 'warning', 'dmarc': 'no-record', 'volume': 0, 'type': 'sending', 'domain_verified': True}],
    }
    orgs = []
    for i, (naam, doms) in enumerate(ruw.items()):
        for x in doms:
            ov = (x.get('dmarc_compliance') or {}).get('overall_compliance')
            if ov is not None and x.get('volume'):
                g = round(x['volume'] * ov / 100)
                x['dmarc_compliance'].update(compliant={'value': g, 'percentage': ov}, none_compliant={'value': x['volume'] - g, 'percentage': round(100 - ov, 1)})
        d = [_HDM._domein(x) for x in doms]
        d.sort(key=lambda x: ({'err': 0, 'warn': 1, 'ok': 2}[x['status']], x['domain']))
        vol = sum(x['volume'] for x in d)
        orgs.append({'id': i + 1, 'name': naam, 'domains': d, 'volume': vol, 'passed': sum(x['passed'] for x in d), 'failed': sum(x['failed'] for x in d), 'compliance': round(sum((x['compliance'] or 0) * x['volume'] for x in d) / vol, 1) if vol else None,
                     'status': 'err' if any(x['status'] == 'err' for x in d) else 'warn' if any(x['status'] == 'warn' for x in d) else 'ok',
                     'counts': {k: len([x for x in d if x['status'] == k]) for k in ('ok', 'warn', 'err')}})
    return orgs


def _dm_overzicht(c, b):
    time.sleep(0.5)
    orgs = sorted(_dm_nep(), key=lambda o: ({'err': 0, 'warn': 1, 'ok': 2}[o['status']], o['name']))
    _HDM._JOB.update(orgs=orgs, dagen=int(b.get('days') or 30), eind=time.time())
    return {'configured': True, 'admin': True, 'busy': False, 'done': len(orgs), 'total': len(orgs), 'days': int(b.get('days') or 30), 'error': '', 'orgs': orgs, 'at': time.strftime('%H:%M')}


API['dm.overzicht'] = _dm_overzicht
API['dm.afzenders'] = lambda c, b: (time.sleep(0.5), {'domain': b['domain'], 'total': 99, 'senders': [
    {'name': 'Mailchimp (mcsv.net)', 'count': 64, 'reason': 'SPF faalt (deze server staat niet in het SPF-record); DKIM ontbreekt of klopt niet (de dienst ondertekent niet met jullie domein)',
     'ips': ['198.2.128.10'], 'from': ['bounce.mcsv.net'], 'countries': ['US'], 'advice': 'Is dit een eigen dienst? Voeg hem toe aan SPF en zet DKIM aan bij die dienst.'},
    {'name': 'onbekend (Rusland)', 'count': 35, 'reason': 'SPF faalt (deze server staat niet in het SPF-record)', 'ips': ['185.0.2.44'], 'from': [], 'countries': ['RU'],
     'advice': ''}]})[1]
API['dm.keys.set'] = lambda c, b: (c.L('EasyDMARC gekoppeld (testmodus).'), {})[1]

# ---------- Autotask projecttaken (v2.18)
_AT_TAKEN = [
    {'id': 701, 'soort': 'taak', 'number': 'P20261101.0003', 'title': 'Mailboxen migreren', 'project': 'Migratie naar Microsoft 365', 'projectNumber': 'P20261101.0003',
     'status': 'In Progress', 'assignedResourceroleID': 1, 'mine': True},
    {'id': 702, 'soort': 'taak', 'number': 'P20261101.0003', 'title': 'Intune-inschrijving laptops', 'project': 'Migratie naar Microsoft 365', 'projectNumber': 'P20261101.0003',
     'status': 'New', 'assignedResourceroleID': 1, 'mine': False},
    {'id': 690, 'soort': 'taak', 'number': 'P20260912.0001', 'title': 'MFA uitrollen', 'project': 'Beveiliging op orde', 'projectNumber': 'P20260912.0001',
     'status': 'In Progress', 'assignedResourceroleID': 1, 'mine': True}]
# Projecten en taken in de nep-Autotask: de echte h_autotask.at.taken draait erop (v2.22.1: eerst project, dan taak)
_NEP_AT.projecten = [
    {'id': 61, 'companyID': 101, 'projectName': 'Migratie naar Microsoft 365', 'projectNumber': 'P20261101.0003', 'status': 1, 'createDateTime': '2026-11-01T08:00:00Z'},
    {'id': 60, 'companyID': 101, 'projectName': 'Beveiliging op orde', 'projectNumber': 'P20260912.0001', 'status': 2, 'createDateTime': '2026-09-12T08:00:00Z'},
    {'id': 59, 'companyID': 101, 'projectName': 'Nieuwe kantoorlocatie', 'projectNumber': 'P20260801.0002', 'status': 1, 'createDateTime': '2026-08-01T08:00:00Z'},
    {'id': 58, 'companyID': 101, 'projectName': 'Oud project', 'projectNumber': 'P20250101.0001', 'status': 5, 'createDateTime': '2025-01-01T08:00:00Z'}]
_NEP_AT.taken = [
    {'id': 701, 'projectID': 61, 'title': 'Mailboxen migreren', 'status': 1, 'assignedResourceID': 30, 'assignedResourceRoleID': 1, 'createDateTime': '2026-11-02T08:00:00Z'},
    {'id': 702, 'projectID': 61, 'title': 'Intune-inschrijving laptops', 'status': 1, 'assignedResourceID': 31, 'assignedResourceRoleID': 1, 'createDateTime': '2026-11-03T08:00:00Z'},
    {'id': 703, 'projectID': 61, 'title': 'Gebruikers informeren', 'status': 5, 'assignedResourceID': 30, 'assignedResourceRoleID': 1, 'createDateTime': '2026-11-01T09:00:00Z'},
    {'id': 690, 'projectID': 60, 'title': 'MFA uitrollen', 'status': 2, 'assignedResourceID': 30, 'assignedResourceRoleID': 1, 'createDateTime': '2026-09-13T08:00:00Z'},
    {'id': 691, 'projectID': 60, 'title': 'Voorwaardelijke toegang inrichten', 'status': 1, 'assignedResourceID': 31, 'assignedResourceRoleID': 1, 'createDateTime': '2026-09-14T08:00:00Z'}]

# ---------- Intune-beheer (v2.18)
_IN_PROF = [
    {'id': 'p1', 'kind': 'dc', 'type': 'Sjabloon', 'template': 'Apparaatbeperkingen', 'odata': '', 'name': 'Windows - Basisbeveiliging', 'desc': 'Standaard voor alle laptops',
     'platform': 'Windows', 'modified': '2026-10-02T09:00:00Z', 'assignments': [{'kind': 'all_devices', 'groupId': None, 'name': 'Alle apparaten', 'intent': None}]},
    {'id': 'p2', 'kind': 'sc', 'type': 'Settings catalog', 'template': '42 instellingen', 'odata': '', 'name': 'Windows - OneDrive Known Folder Move', 'desc': '',
     'platform': 'Windows', 'modified': '2026-09-12T09:00:00Z', 'assignments': [{'kind': 'group', 'groupId': 'gr2', 'name': 'Intune - Laptops', 'intent': None}]},
    {'id': 'p3', 'kind': 'cp', 'type': 'Nalevingsbeleid', 'template': 'Naleving', 'odata': '', 'name': 'Android - Naleving', 'desc': '', 'platform': 'Android Enterprise',
     'modified': '2026-08-01T09:00:00Z', 'assignments': []}]
_IN_APPS = [
    {'id': 'a1', 'name': 'Microsoft 365 Apps voor Windows', 'publisher': 'Microsoft', 'type': 'Microsoft 365 Apps', 'odata': 'officeSuiteApp', 'platform': 'Windows',
     'created': '2025-03-01T09:00:00Z', 'state': 'published', 'assignments': [{'kind': 'all_devices', 'groupId': None, 'name': 'Alle apparaten', 'intent': 'required'}]},
    {'id': 'a2', 'name': 'Bedrijfsportal', 'publisher': 'Microsoft Corporation', 'type': 'Microsoft Store-app', 'odata': 'winGetApp', 'platform': 'Windows',
     'created': '2025-03-01T09:00:00Z', 'state': 'published', 'assignments': [{'kind': 'all_users', 'groupId': None, 'name': 'Alle gebruikers', 'intent': 'available'}]}]
_IN_ENROLL = {'restrictions': [
    {'id': 'r1', 'odata': '#microsoft.graph.deviceEnrollmentPlatformRestrictionsConfiguration', 'name': 'Standaard', 'priority': 0, 'default': True, 'assignments': [],
     'platform': p, 'field': f, 'blocked': b, 'personalBlocked': pb, 'min': '', 'max': ''}
    for p, f, b, pb in (('windows', 'windowsRestriction', False, True), ('android', 'androidRestriction', True, False),
                        ('androidForWork', 'androidForWorkRestriction', False, False), ('ios', 'iosRestriction', False, True), ('mac', 'macOSRestriction', True, False))],
    'limits': [{'id': 'l1', 'odata': '', 'name': 'Standaard', 'priority': 0, 'default': True, 'assignments': [], 'limit': 5}],
    'whfb': {'id': 'w1', 'state': 'enabled', 'pinMinimumLength': 6, 'pinMaximumLength': 127, 'pinUppercaseCharactersUsage': 'allowed', 'pinLowercaseCharactersUsage': 'allowed',
             'pinSpecialCharactersUsage': 'allowed', 'securityDeviceRequired': True, 'unlockWithBiometricsEnabled': True, 'enhancedBiometricsState': 'notConfigured',
             'pinExpirationInDays': 0, 'pinPreviousBlockCount': 0, 'remotePassportEnabled': False, 'securityKeyForSignIn': 'notConfigured'},
    'esp': [{'id': 'e1', 'name': 'Standaard', 'priority': 0, 'default': True, 'assignments': [], 'showInstallationProgress': True, 'installProgressTimeoutInMinutes': 60,
             'customErrorMessage': 'Neem contact op met de servicedesk.', 'blockDeviceSetupRetryByUser': False, 'allowDeviceResetOnInstallFailure': True}],
    'mdm': {'id': '0000000a-0000-0000-c000-000000000000', 'appliesTo': 'all', 'groups': []},
    'gplay': {'bound': True, 'status': 'boundAndValidated', 'owner': 'beheer@voorbeeld.nl', 'sync': '2026-11-20T08:00:00Z', 'fullyManaged': True},
    'androidProfiles': [{'id': 'ap1', 'name': 'Volledig beheerd', 'mode': 'corporateOwnedFullyManaged', 'devices': 4, 'token': True, 'expires': '2027-01-20T08:00:00Z', 'created': ''}],
    'errors': {}}
API['in.profiles'] = lambda c, b: (time.sleep(0.3), {'profiles': _IN_PROF, 'partial': []})[1]
API['in.profile.status'] = lambda c, b: {'overview': {'success': 12, 'error': 1, 'conflict': 0, 'pending': 2, 'na': 0} if b['kind'] in ('dc', 'cp') else None}
API['in.apps'] = lambda c, b: (time.sleep(0.3), {'apps': _IN_APPS})[1]
API['in.app.status'] = lambda c, b: {'summary': {'installed': 14, 'failed': 1, 'pending': 0, 'notInstalled': 2, 'na': 0}}
API['in.store.search'] = lambda c, b: {'results': [{'id': '9WZDNCRFJ3PZ', 'name': 'Bedrijfsportal', 'publisher': 'Microsoft Corporation'}, {'id': 'XP8LFCZM790F6B', 'name': '7-Zip', 'publisher': 'Igor Pavlov'}]}
API['in.enroll'] = lambda c, b: (time.sleep(0.3), _IN_ENROLL)[1]
for _k in ('in.profile.assign', 'in.profile.delete', 'in.app.assign', 'in.app.delete', 'in.app.add', 'in.whfb.set', 'in.esp.set', 'in.restrict.set', 'in.limit.set',
           'in.mdm.set', 'in.android.create', 'in.android.token', 'in.android.delete'):
    API[_k] = (lambda k: lambda c, b: (c.L(f'{k} uitgevoerd (testmodus).'), {})[1])(_k)
API['in.android.qr'] = lambda c, b: {'name': 'Volledig beheerd', 'token': 'ABCDEFGH', 'expires': '2027-01-20T08:00:00Z', 'qr': ''}

# ---------- Back-upcontrole als sessie (v2.19)
_BK_SES: dict = {}


def _bk_ses_uit():
    if not _BK_SES:
        return None
    m = int((time.time() - _BK_SES['t']) // 60)
    return {'ticket': 'T20261127.0007', 'titel': 'Back-upcontrole', 'sinds': time.strftime('%H:%M', time.localtime(_BK_SES['t'])), 'minuten': m,
            'afgerond': max(15, -(-max(m, 1) // 15) * 15), 'items': _BK_SES['items']}


API['at.bk.status'] = lambda c, b: {'configured': True, 'session': _bk_ses_uit()}
API['at.bk.start'] = lambda c, b: (_BK_SES.update(t=time.time(), items=[]), {'session': _bk_ses_uit()})[1]
API['at.bk.stop'] = lambda c, b: (_BK_SES.clear(), c.L('Back-upcontrole afgerond (testmodus).'), {'booked': 1})[2]
_bk_afv_oud = API['bk.afvinken']


def _bk_afv_ses(c, b):
    r = _bk_afv_oud(c, b)
    if _BK_SES:
        _BK_SES['items'] += [{'klant': k, 'uitkomst': b['result'], 'opmerking': b.get('note', ''), 'om': time.strftime('%H:%M')} for k in b['customers']]
    return r


API['bk.afvinken'] = _bk_afv_ses

# ---------- SharePoint-mapmachtigingen (v2.19)
_SPM_PERMS = {None: [{'id': 3, 'name': 'Data - Eigenaars', 'kind': 'SharePoint-groep', 'email': '', 'roles': ['Volledig beheer'], 'spGroup': True},
                     {'id': 4, 'name': 'Data - Leden', 'kind': 'SharePoint-groep', 'email': '', 'roles': ['Bewerken'], 'spGroup': True}],
              11: [{'id': 3, 'name': 'Data - Eigenaars', 'kind': 'SharePoint-groep', 'email': '', 'roles': ['Volledig beheer'], 'spGroup': True},
                   {'id': 21, 'name': 'Jan de Vries', 'kind': 'Gebruiker', 'email': 'jan@voorbeeld.nl', 'roles': ['Bewerken'], 'spGroup': False}]}
_SPM_LEVELS = [{'key': 'read', 'name': 'Lezen', 'help': 'Bestanden openen en downloaden, niets wijzigen.'},
               {'key': 'edit', 'name': 'Bewerken', 'help': 'Bestanden en mappen toevoegen, wijzigen en verwijderen.'},
               {'key': 'contribute', 'name': 'Bijdragen', 'help': ''}, {'key': 'full', 'name': 'Volledig beheer', 'help': 'Alles, ook machtigingen van anderen wijzigen.'}]
API['spm.sites'] = lambda c, b: {'sites': [{'url': 'https://voorbeeld.sharepoint.com/sites/Data', 'title': 'Data'}, {'url': 'https://voorbeeld.sharepoint.com', 'title': 'Communicatiesite'}]}
API['spm.libs'] = lambda c, b: {'libs': [{'id': 'lib1', 'title': 'Documenten', 'count': 5210, 'unique': False, 'path': '/sites/Data/Shared Documents'}]}
API['spm.folders'] = lambda c, b: {'folders': [] if b['path'].count('/') > 4 else [
    {'name': 'Directie', 'path': b['path'] + '/Directie', 'count': 120, 'itemId': 11, 'unique': True},
    {'name': 'Financieel', 'path': b['path'] + '/Financieel', 'count': 860, 'itemId': 12, 'unique': True},
    {'name': 'Projecten', 'path': b['path'] + '/Projecten', 'count': 3100, 'itemId': 13, 'unique': False}]}
API['spm.perms'] = lambda c, b: {'unique': b.get('itemId') in (11, 12), 'perms': _SPM_PERMS.get(b.get('itemId'), _SPM_PERMS[None]), 'levels': _SPM_LEVELS}
API['spm.groupusers'] = lambda c, b: {'users': [{'name': 'Piet Jansen', 'email': ''}, {'name': 'Klaas Bakker', 'email': ''}]}
for _k in ('spm.grant', 'spm.revoke', 'spm.inherit'):
    API[_k] = (lambda k: lambda c, b: (c.L(f'{k} uitgevoerd (testmodus).'), {})[1])(_k)
API['spm.zoals'] = lambda c, b: (c.L('Maptoegang gekopieerd (testmodus).'), {'folders': ['/Directie', '/Financieel'], 'checked': 2})[1]


# ---------------------------------------------------------------- Voorwaardelijke toegang (echte omzetting uit h_ca)
from . import h_ca as _hca  # noqa: E402

_CA_ROLLEN = [{'id': '62e90394-69f5-4237-9190-012177145e10', 'name': 'Global Administrator'}, {'id': 'fe930be7-5e62-47db-91af-98c3a49a38b1', 'name': 'User Administrator'},
              {'id': '194ae4cb-b126-40b2-bd5b-6091b380977d', 'name': 'Security Administrator'}, {'id': '29232cdf-9323-42fd-ade2-1d097af3e4de', 'name': 'Exchange Administrator'}]
_CA_LOC = [{'@odata.type': '#microsoft.graph.ipNamedLocation', 'id': 'loc-kantoor', 'displayName': 'Kantoor', 'isTrusted': True,
            'ipRanges': [{'cidrAddress': '203.0.113.10/32'}], 'modifiedDateTime': '2026-10-01T09:00:00Z'},
           {'@odata.type': '#microsoft.graph.countryNamedLocation', 'id': 'loc-landen', 'displayName': 'Toegestane landen', 'countriesAndRegions': ['NL', 'BE', 'DE'],
            'includeUnknownCountriesAndRegions': False, 'countryLookupMethod': 'clientIpAddress'}]
_CA_POL = [dict(_hca._naar_graph({'name': 'MFA voor alle gebruikers', 'state': 'enabled', 'users': {'include': 'all', 'excludeServiceProvider': True}, 'apps': {'include': 'all'},
                                   'grant': {'controls': ['mfa']}}), id='pol-1', modifiedDateTime='2026-11-01T10:00:00Z'),
           dict(_hca._naar_graph({'name': 'Blokkeren buiten toegestane landen', 'state': 'enabledForReportingButNotEnforced', 'users': {'include': 'all', 'excludeServiceProvider': True},
                                   'apps': {'include': 'all'}, 'locations': {'include': ['All'], 'exclude': ['loc-landen']}, 'grant': {'block': True}}), id='pol-2')]


@m('ca.list')
def _m_ca_list(c, b):
    time.sleep(0.3)
    namen = {r['id']: r['name'] for r in _CA_ROLLEN}
    namen.update({x['id']: x['displayName'] for x in _CA_LOC})
    namen.update({'All': 'Alle', 'AllTrusted': 'Alle vertrouwde locaties'})
    return {'policies': [dict(_hca._model(p), modified=p.get('modifiedDateTime', ''), summary=_hca._samenvatting(p, namen)) for p in _CA_POL],
            'locations': [_hca._lijst(x) for x in _CA_LOC], 'roles': _CA_ROLLEN, 'names': namen,
            'strengths': [{'id': '00000000-0000-0000-0000-000000000002', 'name': 'Meervoudige verificatie', 'builtIn': True},
                          {'id': '00000000-0000-0000-0000-000000000004', 'name': 'Phishingbestendige MFA', 'builtIn': True}],
            'portal': 'https://entra.microsoft.com/'}


@m('ca.apps')
def _m_ca_apps(c, b):
    return {'apps': [{'id': '00000003-0000-0ff1-ce00-000000000000', 'name': 'Office 365 SharePoint Online'}, {'id': '00000002-0000-0ff1-ce00-000000000000', 'name': 'Office 365 Exchange Online'}]}


@m('ca.save')
def _m_ca_save(c, b):
    p = b.get('policy') or {}
    oud = next((x for x in _CA_POL if x['id'] == p.get('id')), None)
    body = _hca._naar_graph(p, oud)
    if oud:
        oud.clear()
        oud.update(body, id=p['id'])
    else:
        _CA_POL.append(dict(body, id=f'pol-{len(_CA_POL) + 1}'))
    c.L(f"Beleid '{body['displayName']}' opgeslagen.")
    return {}


@m('ca.state')
def _m_ca_state(c, b):
    for x in _CA_POL:
        if x['id'] == b.get('id'):
            x['state'] = b['state']
    return {}


@m('ca.delete')
def _m_ca_delete(c, b):
    _CA_POL[:] = [x for x in _CA_POL if x['id'] != b.get('id')]
    return {}


@m('ca.loc.save')
def _m_ca_loc_save(c, b):
    if b.get('type') == 'ip':
        rng = [_hca._cidr(x) for x in b.get('ranges') or []]
        if not rng:
            raise ApiFout('Vul minstens één IP-adres in.')
        x = {'@odata.type': '#microsoft.graph.ipNamedLocation', 'displayName': b['name'], 'isTrusted': bool(b.get('trusted')), 'ipRanges': rng}
    else:
        x = {'@odata.type': '#microsoft.graph.countryNamedLocation', 'displayName': b['name'], 'countriesAndRegions': b.get('countries') or [],
             'includeUnknownCountriesAndRegions': bool(b.get('unknown')), 'countryLookupMethod': b.get('method') or 'clientIpAddress'}
    oud = next((l for l in _CA_LOC if l['id'] == b.get('id')), None)
    if oud:
        oud.update(x)
    else:
        _CA_LOC.append(dict(x, id=f'loc-{len(_CA_LOC) + 1}'))
    return {}


@m('ca.loc.delete')
def _m_ca_loc_delete(c, b):
    _CA_LOC[:] = [x for x in _CA_LOC if x['id'] != b.get('id')]
    return {}

# ---------- Management (v2.23): servicedeskcijfers nagebootst, de rest komt uit de bestaande (nep)overzichten ----------
from . import h_management as _HMG


def _mg_at(dagen):
    import random
    from datetime import datetime, timedelta
    rnd = random.Random(dagen)
    nu = datetime.now()
    klanten = ['Bakkerij De Korenaar', 'Advocatenkantoor De Wit', 'Installatiebedrijf Bos', 'Stichting Zorgpunt', 'Adviesbureau Meijer', 'Incassobureau Noord',
               'Intern (Justdata)']
    rijen = []
    for i, n in enumerate(klanten):
        c = rnd.randint(4, 40) // (1 + i // 3)
        rijen.append({'id': 100 + i, 'name': n, 'created': c, 'completed': max(0, c - rnd.randint(-3, 6)), 'open': rnd.randint(0, 9),
                      'hours': round(c * rnd.uniform(0.6, 1.8), 1), 'billable': 0.0, 'internal': n.startswith('Intern')})
    for r in rijen:
        r['billable'] = 0.0 if r['internal'] else round(r['hours'] * rnd.uniform(0.6, 0.95), 1)
    rijen.sort(key=lambda r: -r['hours'])
    weken = []
    for w in range(min(13, dagen // 7 + 1), -1, -1):
        d = nu - timedelta(weeks=w)
        j, wk, _ = d.isocalendar()
        weken.append({'week': f'{j}-W{wk:02d}', 'label': f'wk {wk}', 'created': rnd.randint(12, 30), 'completed': rnd.randint(10, 31), 'hours': round(rnd.uniform(20, 45), 1)})
    uren = round(sum(r['hours'] for r in rijen), 1)
    fact = round(sum(r['billable'] for r in rijen), 1)
    mw = [{'name': 'Beheerder Test', 'hours': round(uren * .45, 1), 'billable': round(fact * .5, 1), 'completed': 41},
          {'name': 'Servicedesk Medewerker', 'hours': round(uren * .35, 1), 'billable': round(fact * .35, 1), 'completed': 52},
          {'name': 'Collega Test', 'hours': round(uren * .20, 1), 'billable': round(fact * .15, 1), 'completed': 17}]
    for m in mw:
        m['billablePct'] = round(m['billable'] * 100 / m['hours']) if m['hours'] else None
    created, completed = sum(r['created'] for r in rijen), sum(r['completed'] for r in rijen)
    leeftijd = {'0-7 dagen': 14, '8-30 dagen': 9, '31-90 dagen': 5, 'Ouder dan 90 dagen': 2}
    return {'days': dagen, 'at': nu.strftime('%d-%m-%Y %H:%M'),
            'kpi': {'created': created, 'completed': completed, 'open': sum(leeftijd.values()), 'openOld': 7, 'openVeryOld': 2, 'leadMedian': 1.4, 'leadAvg': 3.8,
                    'within1': 46, 'hours': uren, 'billable': fact, 'billablePct': round(fact * 100 / uren), 'customers': len(rijen) - 1},
            'weeks': weken, 'customers': rijen, 'employees': mw, 'openAge': leeftijd,
            'priorities': [{'label': 'Low', 'count': 17}, {'label': 'Medium', 'count': 9}, {'label': 'High', 'count': 3}, {'label': 'Critical', 'count': 1}],
            'queues': [{'label': 'Servicedesk', 'count': int(created * .7)}, {'label': 'Projecten', 'count': int(created * .2)}, {'label': 'Monitoring', 'count': int(created * .1)}]}


_HMG.at_statistiek = lambda dagen: (time.sleep(1.0), _mg_at(dagen))[1]


# ---------- Klantrapportage (v2.24): nagebootste Autotask-gegevens van één bedrijf; de echte berekening draait erop ----------
from . import h_klantrapport as _HKR


def _kr_ophalen(company, van, tot):
    import random
    from datetime import datetime, timedelta, timezone
    rnd = random.Random(int(company))
    nu = datetime.now(timezone.utc)
    start = van.astimezone(timezone.utc)
    onderwerpen = ['Wachtwoord vergeten', 'Printer werkt niet', 'Nieuwe medewerker aanmaken', 'Outlook start niet op', 'Teams-vergadering geeft geen geluid',
                   'Laptop traag', 'Toegang tot gedeelde map', 'Licentie toevoegen', 'Telefoon koppelen aan e-mail', 'Back-up controle', 'VPN maakt geen verbinding',
                   'Medewerker uit dienst', 'Phishingmail ontvangen', 'Nieuwe laptop klaarzetten', 'Excel-bestand beschadigd']
    mensen = {30: 'Beheerder Test', 31: 'Servicedesk Medewerker', 32: 'Collega Test'}
    contacten = {501: 'Sanne Voorbeeld', 502: 'Pieter Test', 504: 'Fatima Jansen', 505: 'Kees de Vries'}
    tickets, tijd, tid, eid = [], [], 9000, 1
    dag = start
    while dag < nu:
        for _ in range(rnd.choice([0, 0, 1, 1, 1, 2, 3]) if dag.weekday() < 5 else rnd.choice([0, 0, 0, 1])):
            gemaakt = dag + timedelta(hours=rnd.uniform(7.5, 17))
            if gemaakt > nu:
                continue
            duur = rnd.choice([0.3, 0.8, 1.5, 3, 5, 20, 30, 50, 90, 200])
            klaar = gemaakt + timedelta(hours=duur * rnd.uniform(0.7, 1.3))
            tid += 1
            t = {'id': tid, 'ticketNumber': f'T{gemaakt:%Y%m%d}.{tid % 1000:04d}', 'title': rnd.choice(onderwerpen), 'priority': rnd.choice([3, 3, 3, 2, 1]),
                 'queueID': 8, 'issueType': rnd.choice([1, 1, 2, 3, 4, 5]), 'source': rnd.choice([1, 1, 2, 3, 4]), 'createDate': gemaakt.isoformat(),
                 'firstResponseDateTime': (gemaakt + timedelta(minutes=rnd.uniform(4, 90))).isoformat(), 'assignedResourceID': rnd.choice([30, 31, 31, 32]),
                 'contactID': rnd.choice([501, 501, 502, 504, 505, None]), 'status': 5 if klaar < nu else 1,
                 'completedDate': klaar.isoformat() if klaar < nu else None, 'lastActivityDate': min(klaar, nu).isoformat()}
            tickets.append(t)
            for _ in range(rnd.choice([1, 1, 2])):
                eid += 1
                tijd.append({'id': eid, 'ticketID': tid, 'resourceID': t['assignedResourceID'], 'hoursWorked': rnd.choice([0.25, 0.25, 0.5, 0.75, 1, 1.5, 2]),
                             'isNonBillable': False, 'dateWorked': (gemaakt + timedelta(minutes=30)).isoformat()})
        if dag.weekday() == 2 and rnd.random() < 0.5:
            eid += 1
            tijd.append({'id': eid, 'taskID': 701 + rnd.randint(0, 1), 'resourceID': 30, 'hoursWorked': rnd.choice([2, 3, 4]), 'isNonBillable': False,
                         'dateWorked': (dag + timedelta(hours=10)).isoformat()})
        dag += timedelta(days=1)
    return {'name': 'Bakkerij De Korenaar B.V.' if int(company) == 101 else f'Testbedrijf {company}', 'tickets': tickets, 'time': tijd,
            'projects': {801: 'Migratie naar SharePoint', 802: 'Nieuwe werkplekken'}, 'tasks': {701: 801, 702: 802}, 'resources': mensen,
            'contacts': contacten, 'done': [5],
            'labels': {'priority': {'1': 'Hoog', '2': 'Gemiddeld', '3': 'Laag'}, 'queueID': {'8': 'Servicedesk'},
                       'issueType': {'1': 'Accounts en wachtwoorden', '2': 'E-mail en Outlook', '3': 'Hardware en printers', '4': 'Microsoft Teams', '5': 'Bestellingen en wensen'},
                       'source': {'1': 'E-mail', '2': 'Telefoon', '3': 'Klantportaal', '4': 'Monitoring (automatisch)'}, 'status': {'1': 'Nieuw', '5': 'Afgerond'}}}


_HKR.ophalen = lambda company, van, tot: (time.sleep(0.8), _kr_ophalen(company, van, tot))[1]


# ---------- v2.25: klantaccount voor SharePoint en onboarding per map (nagebootst) ----------
from . import h_spmappen as _HSPM
_SPM_KLANT = {'acc': ''}
_spm_libs_oud = API['spm.libs']


def _spm_libs(c, b):
    if not _SPM_KLANT['acc']:
        raise _HSPM.KlantLoginNodig('Microsoft laat je Justdata-account (GDAP) niet in de inhoud van SharePoint-sites, ook niet als sitebeheerder. '
                                    'Log één keer in met een beheeraccount van de klant zelf (bijv. beheer@klant.onmicrosoft.com); '
                                    'daarna werkt Mapmachtigingen voor deze klant de rest van de sessie.', 403)
    return _spm_libs_oud(c, b)


API['spm.libs'] = _spm_libs
API['spm.klantstatus'] = lambda c, b: {'account': _SPM_KLANT['acc']}
API['spm.klantlogin'] = lambda c, b: (time.sleep(1), _SPM_KLANT.update(acc='beheer@korenaar.onmicrosoft.com'),
                                      c.L('Voor SharePoint ingelogd met het klantaccount beheer@korenaar.onmicrosoft.com (testmodus).'), {'account': _SPM_KLANT['acc']})[3]
API['spm.klantlogout'] = lambda c, b: (_SPM_KLANT.update(acc=''), {})[1]


def _spm_g(i, n, r='Bewerken', d=False):
    return {'id': i, 'name': n, 'kind': 'SharePoint-groep', 'role': r, 'spGroup': True, 'entraId': '', 'm365': False, 'default': d, 'email': ''}


def _spm_kaart(c, b):
    time.sleep(1.2)
    std = [_spm_g(3, 'Data-eigenaars', 'Volledig beheer', True)]
    mappen = [('1. Algemeen', [_spm_g(310, '310 Algemeen')]), ('2. Sales', [_spm_g(320, '320 Sales'), _spm_g(321, '321 Sales lezen', 'Lezen')]),
              ('3. Finance', [_spm_g(330, '330 Finance')]), ('3. Finance/Salarisadministratie', [_spm_g(331, '331 Salaris')]), ('4. HR', [_spm_g(340, '340 HR')]),
              ('5. Directie', [_spm_g(350, '350 Directie')]),
              ('6. Operations', [_spm_g(360, '360 Operations'), {'id': 77, 'name': 'Operations-team', 'kind': 'Beveiligingsgroep', 'role': 'Bewerken', 'spGroup': False,
                                                              'entraId': '0b6f1f7e-1111-2222-3333-444455556666', 'm365': False, 'default': False, 'email': ''}]),
              ('7. Juridisch', [{'id': 90, 'name': 'Jurist Extern', 'kind': 'Gebruiker', 'role': 'Bewerken', 'spGroup': False, 'entraId': '', 'm365': False,
                                 'default': False, 'email': 'jurist@extern.nl'}])]
    f = [{'lib': 'Documenten', 'listId': 'lib1', 'itemId': None, 'path': '/sites/Data/Shared Documents', 'name': 'Documenten', 'rel': '', 'depth': 0, 'unique': False,
          'access': std + [_spm_g(4, 'Data-leden', 'Bewerken', True)]}]
    for i, (rel, acc) in enumerate(mappen):
        f.append({'lib': 'Documenten', 'listId': 'lib1', 'itemId': 100 + i, 'path': '/sites/Data/Shared Documents/' + rel, 'name': rel.split('/')[-1], 'rel': rel,
                  'depth': rel.count('/') + 1, 'unique': True, 'access': acc + std})
    leden = {310: ['piet@korenaar.nl', 'klaas@korenaar.nl'], 320: ['piet@korenaar.nl'], 330: ['klaas@korenaar.nl'], 350: []}
    groepen = {x['id']: x['name'] for d in f for x in d['access'] if x['spGroup']}
    return {'folders': f, 'groups': [{'id': k, 'name': v, 'members': leden.get(k, []), 'default': k in (3, 4)} for k, v in groepen.items()], 'truncated': False}


def _spm_onboard(c, b):
    time.sleep(1)
    namen = [g['name'] for g in b.get('spGroups') or []] + [g['name'] for g in b.get('entraGroups') or []] + ['map ' + d['label'] for d in b.get('direct') or []]
    c.L(f"{b['upn']} heeft maptoegang gekregen via: {', '.join(namen)} (testmodus).")
    return {'done': namen, 'errors': []}


API['spm.toegangskaart'] = _spm_kaart
API['spm.onboard'] = _spm_onboard


# ---------- v2.26: Servicedesk en IT Glue (nagebootst; zoeken en indeling draaien echt) ----------
from . import h_itglue as _HIG
from . import h_servicedesk as _HSD
_IG = {'key': 'test'}
_HIG._sleutel = lambda: _IG['key'] or None


def _ig_index():
    time.sleep(0.6)
    d = lambda i, t, org, txt, typ='Werkinstructie (M365 beheer)': {'id': str(i), 'title': t, 'org': org, 'orgId': '1', 'type': typ,  # noqa: E731
                                                                    'url': f'https://voorbeeld.eu.itglue.com/1/assets/{i}', 'text': txt, 'updated': '2026-10-02'}
    return {'docs': [
        d(1, 'Outlook start niet op: profiel herstellen', 'Bakkerij De Korenaar', 'Outlook blijft hangen bij laden profiel. Oplossing: Outlook /safe, daarna nieuw profiel via Configuratiescherm > E-mail. OST-bestand verwijderen.'),
        d(2, 'Printer werkt niet na Windows-update', 'Justdata', 'Printer offline of afdrukken blijft in wachtrij. Spooler herstarten, driver opnieuw installeren via Intune (Win32-app).', 'Procedure'),
        d(3, 'Nieuwe medewerker: Teams en gedeelde mappen', 'Bakkerij De Korenaar', 'Nieuwe gebruiker aanmaken, licentie Business Premium, toevoegen aan Teams Algemeen en de SharePoint-groepen per map.'),
        d(4, 'VPN maakt geen verbinding (FortiClient)', 'Advocatenkantoor De Wit', 'VPN-verbinding faalt met fout -14. Certificaat vernieuwen, FortiClient opnieuw installeren.', 'Kennisbank'),
        d(5, 'Wachtwoord vergeten: zelf herstellen (SSPR)', 'Justdata', 'Gebruiker kan wachtwoord zelf herstellen via aka.ms/sspr. Anders wachtwoord opnieuw instellen in Microsoft 365 beheer.'),
        d(6, 'Phishingmail ontvangen: wat te doen', 'Justdata', 'Phishingmail melden, afzender blokkeren in Bedreigingsbeheer, sessies afmelden en wachtwoord resetten als er is geklikt.', 'Procedure'),
    ], 'orgs': [{'id': '1', 'name': 'Bakkerij De Korenaar B.V.'}, {'id': '2', 'name': 'Advocatenkantoor De Wit'}, {'id': '3', 'name': 'Justdata'}]}


_HIG.ophalen_index = _ig_index
_HIG.vastleggen = lambda klant, titel, probleem, oplossing, ticket='', trefwoorden='': (time.sleep(0.8), _HIG.vergeet(),
                                                                                         {'id': '99', 'url': 'https://voorbeeld.eu.itglue.com/1/assets/99', 'org': klant or 'Justdata'})[2]
API['ig.keys.set'] = lambda c, b: (_IG.update(key=b.get('key') or 'test'), _HIG.vergeet(), c.L('IT Glue gekoppeld (testmodus).'), {})[3]
API['ig.keys.delete'] = lambda c, b: (_IG.update(key=''), _HIG.vergeet(), {})[2]
_SD_INST = {'tweedeLijn': []}


def _sd_tickets(at, filters, max_=500):
    time.sleep(0.5)
    t = lambda i, titel, bedrijf, wie, wid, age, desc='', prio='Medium', st='In Progress': {  # noqa: E731
        'id': i, 'number': f'T20261127.{i:04d}', 'title': titel, 'description': desc, 'company': bedrijf, 'companyId': 101, 'status': st, 'priority': prio,
        'assigned': wie, 'assignedId': wid, 'age': age, 'created': '20-11-2026', 'due': '28-11-2026', 'overdue': age > 6, 'url': ''}
    alle = [t(1, 'Outlook start niet op bij receptie', 'Bakkerij De Korenaar', 'Beheerder Test', 30, 1, 'Outlook blijft hangen op profiel laden'),
            t(2, 'Nieuwe medewerker per 1 december', 'Bakkerij De Korenaar', 'Beheerder Test', 30, 3, 'Graag account, Teams en mappen voor Sanne'),
            t(3, 'Offerte nieuwe firewall', 'Installatiebedrijf Bos', 'Beheerder Test', 30, 9, prio='Low'),
            t(4, 'Printer op de werkplaats drukt niet meer af', 'Installatiebedrijf Bos', 'Tweede Lijn A', 31, 2, 'Sinds de update van gisteren'),
            t(5, 'VPN werkt niet thuis', 'Advocatenkantoor De Wit', 'Tweede Lijn B', 32, 1, 'FortiClient geeft fout'),
            t(6, 'Migratie fileserver naar SharePoint', 'Stichting Zorgpunt', 'Tweede Lijn A', 31, 20),
            t(7, 'Wachtwoord vergeten', 'Adviesbureau Meijer', '', None, 0)]
    f = filters[0]
    if f['op'] == 'eq':
        return [x for x in alle if x['assignedId'] == f['value']]
    if f['op'] == 'in':
        return [x for x in alle if x['assignedId'] in f['value']]
    return [x for x in alle if x['assignedId'] is None]


_HSD._tickets = _sd_tickets
_HAT._instellingen = (lambda f: lambda: {**f(), **_SD_INST})(_HAT._instellingen)
API['sd.tweedelijn.set'] = lambda c, b: (_SD_INST.update(tweedeLijn=[int(x) for x in b.get('ids') or []]), _HSD._CACHE.clear(), c.L('Tweede lijn ingesteld (testmodus).'), {})[3]
API['sd.resources'] = lambda c, b: {'resources': [{'id': 30, 'name': 'Beheerder Test', 'email': 'beheerder@voorbeeld.nl'}, {'id': 31, 'name': 'Tweede Lijn A', 'email': ''},
                                                  {'id': 32, 'name': 'Tweede Lijn B', 'email': ''}, {'id': 33, 'name': 'Eerste Lijn C', 'email': ''}], 'mapping': {}}


def _sd_ticket(c, b):
    time.sleep(0.8)
    if not b.get('companyId') or not str(b.get('title') or '').strip():
        raise ApiFout('Kies de klant en vul het onderwerp in.')
    c.L(f"Ticket T20261127.0042 aangemaakt bij {b.get('companyName') or 'de klant'}: {b['title']} (15 minuten geboekt, testmodus).")
    return {'ticket': {'id': 42, 'number': 'T20261127.0042', 'title': b['title'], 'url': ''}, 'booked': True}


API['sd.ticket'] = _sd_ticket
API['sd.bedrijven'] = lambda c, b: {'companies': [x for x in [{'id': 101, 'name': 'Bakkerij De Korenaar B.V.'}, {'id': 102, 'name': 'Installatiebedrijf Bos'},
                                                              {'id': 103, 'name': 'Advocatenkantoor De Wit'}] if str(b.get('q') or '').lower() in x['name'].lower()]}


# ---------- v2.28: advies (Microsoft Learn + AI) en ticketacties (nagebootst) ----------
from . import h_advies as _HADV
_ADV = {'key': ''}
_HADV._sleutel = lambda: _ADV['key'] or None
_HADV.beschikbaar = lambda: bool(_ADV['key'])
API['adv.keys.set'] = lambda c, b: (_ADV.update(key='sk-ant-test'), c.L('AI-advies gekoppeld (testmodus).'), {})[2]
API['adv.keys.delete'] = lambda c, b: (_ADV.update(key=''), {})[1]
_HADV.learn = lambda onderwerp, n=4, extra='': [
    {'title': 'Outlook reageert niet of loopt vast', 'url': 'https://learn.microsoft.com/nl-nl/troubleshoot/outlook/performance/outlook-not-responding-error-or-outlook-freezes',
     'description': 'Beschrijft een probleem waardoor Outlook vastloopt. Geeft een oplossing.', 'products': ['Outlook']},
    {'title': 'Verbindingsproblemen met Outlook in Microsoft 365 oplossen', 'url': 'https://learn.microsoft.com/nl-nl/troubleshoot/exchange/outlook-issues/outlook-connection-issues',
     'description': 'Stappen om problemen met Outlook op te sporen en op te lossen.', 'products': ['Outlook']}][:n] if onderwerp else []


def _adv_vraag(prompt, schema, effort='medium', max_tokens=8000):
    time.sleep(1.2)
    if 'tickets' in schema.get('properties', {}):
        ids = [int(r.split(' | ')[0]) for r in prompt.split('\n') if r[:1].isdigit() and ' | ' in r]
        return {'tickets': [{'id': i, 'eersteLijn': i in (5, 7), 'reden': 'Standaardvraag, bekende oplossing.' if i in (5, 7) else 'Vraagt specialistische kennis.',
                             'minuten': 30} for i in ids]}
    if 'tekst' in schema.get('properties', {}):
        return {'tekst': 'Outlook-profiel van de gebruiker opnieuw aangemaakt en het OST-bestand verwijderd. Outlook start weer normaal en de mailbox is volledig gesynchroniseerd.'}
    return {'samenvatting': 'Outlook blijft hangen bij het laden van het profiel, waarschijnlijk door een beschadigd profiel of OST-bestand.',
            'eersteLijn': True, 'waarom': 'Standaardprobleem met een bekende oplossing; er gaat geen data verloren.',
            'vragenAanKlant': ['Sinds wanneer gebeurt dit?', 'Werkt webmail (outlook.office.com) wel?'],
            'stappen': ['Vraag de gebruiker Outlook af te sluiten.', 'Start Outlook in veilige modus: Windows-toets + R, typ outlook.exe /safe en druk op Enter.',
                        'Start Outlook dat wel? Zet dan de invoegtoepassingen uit via Bestand > Opties > Invoegtoepassingen.',
                        'Start het niet? Maak een nieuw profiel: Configuratiescherm > E-mail > Profielen weergeven > Toevoegen.',
                        'Stel het nieuwe profiel in als standaard en start Outlook opnieuw (zie IT Glue: Outlook start niet op: profiel herstellen).'],
            'controle': 'Outlook start binnen een minuut en nieuwe mail komt binnen.', 'escalerenAls': 'Ook webmail werkt niet, of het nieuwe profiel helpt niet.',
            'tijdInschatting': 30, 'uitleg': 'Outlook bewaart een kopie van de mailbox op de computer (het OST-bestand). Raakt dat beschadigd, dan blijft Outlook hangen; een nieuw profiel bouwt die kopie opnieuw op vanuit Microsoft 365, er gaat geen mail verloren.'}


_HADV._vraag = _adv_vraag
_SD_STATUS = [{'value': 1, 'label': 'New', 'done': False}, {'value': 8, 'label': 'In Progress', 'done': False},
              {'value': 7, 'label': 'Waiting Customer', 'done': False}, {'value': 5, 'label': 'Complete', 'done': True}]
API['sd.statussen'] = lambda c, b: {'statuses': _SD_STATUS, 'priorities': [{'value': 4, 'label': 'Critical'}, {'value': 1, 'label': 'High'}, {'value': 2, 'label': 'Medium'}, {'value': 3, 'label': 'Low'}], 'end': {'complete': 5, 'invoice': 12}}
API['sd.tijd'] = lambda c, b: (time.sleep(0.8), c.L(f"Ticket {b['id']}: {b['minutes']} minuten geboekt (testmodus)."), {'done': [f"{b['minutes']} minuten geboekt"]})[2]
API['sd.notitie'] = lambda c, b: (time.sleep(0.5), c.L('Notitie toegevoegd (testmodus).'), {})[2]
API['sd.status'] = lambda c, b: (time.sleep(0.5), c.L('Status gewijzigd (testmodus).'), {})[2]


# ---------- v2.33: servicedesk L1/L2, changes, monitoring en facturatie (nagebootst; facturatie rekent echt) ----------
from . import h_sdniveau as _HSDN
from . import h_facturatie as _HFA
_RAW: dict = {'servicedesk-inrichting': _json.dumps({'l1Queue': 29682833, 'l2Queue': 29682834, 'l1': [33, 34, 35], 'l1Leads': [30], 'l2': [31, 32],
                                                     'approvers': [30], 'tariefL1': 75, 'tariefL2': 115, 'doelL1': 85, 'triageMin': 15, 'escalatieMax': 15})}
_HBK.GEDEELD.lees_raw = lambda titel, ttl=600: _RAW.get(titel)
_HBK.GEDEELD.schrijf_raw = lambda titel, waarde: (_RAW.pop(titel, None) if waarde is None else _RAW.__setitem__(titel, waarde))
_SD_MENSEN = {30: 'Beheerder Test', 31: 'Tweede Lijn A', 32: 'Tweede Lijn B', 33: 'Servicedesk C', 34: 'Servicedesk D', 35: 'Stagiair E'}


def _sdq(queue, max_=300):
    from datetime import datetime, timedelta, timezone
    nu = datetime.now(timezone.utc)
    t = lambda i, titel, bedrijf, wid, uur, st='New', prio='Medium', q=29682833, due=24: {  # noqa: E731
        'id': i, 'number': f'T20261128.{i:04d}', 'title': titel, 'description': 'Melding via e-mail van de klant.', 'company': bedrijf, 'companyId': 101,
        'status': st, 'statusId': 1 if st == 'New' else 8, 'priority': prio, 'priorityId': 2, 'assigned': _SD_MENSEN.get(wid, ''), 'assignedId': wid,
        'unassigned': wid is None, 'isNew': st == 'New', 'hours': uur, 'age': int(uur // 24), 'queueId': q,
        'queue': 'Servicedesk (L1)' if q == 29682833 else 'Escalatie (L2)', 'created': (nu - timedelta(hours=uur)).astimezone().strftime('%d-%m-%Y'),
        'due': '', 'overdue': uur > due, 'url': ''}
    l1 = [t(101, 'Wachtwoord vergeten, kan niet inloggen', 'Bakkerij De Korenaar', None, 0.2, prio='High'),
          t(102, 'Outlook vraagt steeds om wachtwoord', 'Advocatenkantoor De Wit', None, 0.6),
          t(103, 'Printer op de tweede verdieping offline', 'Installatiebedrijf Bos', 33, 3, st='In Progress'),
          t(104, 'Nieuwe medewerker per 1 december: Sanne', 'Bakkerij De Korenaar', 34, 26, st='In Progress', prio='Low'),
          t(105, 'Datto: back-up mislukt op SRV-APP01', 'Bakkerij De Korenaar', None, 1.5, prio='High'),
          t(106, 'Teams-vergadering geen geluid', 'Stichting Zorgpunt', 30, 5, st='In Progress')]
    l2 = [t(201, 'Intune: laptops schrijven niet in', 'Stichting Zorgpunt', 31, 30, st='In Progress', q=29682834),
          t(202, 'Firewall: VPN-tunnel valt weg', 'Advocatenkantoor De Wit', None, 4, q=29682834, prio='High'),
          t(203, 'Migratie fileserver naar SharePoint', 'Installatiebedrijf Bos', 32, 120, st='In Progress', q=29682834, due=72)]
    return l2 if int(queue) == 29682834 else l1


_HSDN._queue_tickets = _sdq
_HSDN._leden = lambda welke: ([{'id': 30, 'name': 'Beheerder Test', 'lead': True}, {'id': 33, 'name': 'Servicedesk C', 'lead': False},
                               {'id': 34, 'name': 'Servicedesk D', 'lead': False}, {'id': 35, 'name': 'Stagiair E', 'lead': False}] if welke == 'l1'
                              else [{'id': 31, 'name': 'Tweede Lijn A', 'lead': False}, {'id': 32, 'name': 'Tweede Lijn B', 'lead': False}])


def _sd_wijzig(wat):
    def f(c, b):
        time.sleep(0.5)
        n = len(b.get('ids') or [b.get('id')])
        c.L(f'(testmodus) {wat}: {n} ticket(s).')
        return {'results': [{'id': i, 'ok': True} for i in (b.get('ids') or [b.get('id')])], 'ok': n, 'failed': 0}
    return f


API['sd.triage'] = _sd_wijzig('Triage')
API['sd.escaleren'] = lambda c, b: (_sd_wijzig('Geëscaleerd naar L2')(c, b) if len(str(b.get('reason') or '').strip()) >= 10
                                    else (_ for _ in ()).throw(ApiFout('Schrijf kort waarom het naar L2 moet en wat je al hebt geprobeerd.')))
API['sd.terugnaarl1'] = _sd_wijzig('Terug naar L1')
API['sd.melding'] = lambda c, b: {'tickets': [{'id': 101, 'number': 'T20261128.0101', 'title': 'Wachtwoord vergeten, kan niet inloggen', 'company': 'Bakkerij De Korenaar', 'created': ''},
                                              {'id': 102, 'number': 'T20261128.0102', 'title': 'Outlook vraagt steeds om wachtwoord', 'company': 'Advocatenkantoor De Wit', 'created': ''},
                                              {'id': 105, 'number': 'T20261128.0105', 'title': 'Datto: back-up mislukt op SRV-APP01', 'company': 'Bakkerij De Korenaar', 'created': ''}]
                                  + ([{'id': 900 + int(time.time() // 120) % 50, 'number': f'T20261128.{900 + int(time.time() // 120) % 50:04d}', 'title': 'Nieuwe melding (testmodus)',
                                       'company': 'Stichting Zorgpunt', 'created': ''}] if int(time.time() // 120) % 2 else []),
                                  'mine': [], 'lead': True}
API['sd.inrichting'] = lambda c, b: {'settings': _HSDN.inrichting(), 'queues': [{'value': 29682833, 'label': 'Servicedesk (L1)'}, {'value': 29682834, 'label': 'Escalatie (L2)'},
                                                                                {'value': 29682835, 'label': 'Monitoring'}],
                                     'resources': [{'id': k, 'name': v, 'email': ''} for k, v in _SD_MENSEN.items()]}
_CHANGES = [{'id': 301, 'number': 'T20261127.0301', 'title': 'Firmware-update firewall kantoor', 'company': 'Advocatenkantoor De Wit', 'description': 'Update naar 7.4.5, buiten kantoortijd.',
             'info': ['Impact: VPN 15 minuten weg', 'Terugval: vorige firmware staat klaar'], 'status': 'New', 'priority': 'Medium', 'approval': 'Assigned', 'created': '27-11-2026',
             'assigned': 'Tweede Lijn B', 'url': '', 'votes': [{'name': 'Beheerder Test', 'vote': None, 'note': ''}], 'myVote': None, 'iAmApprover': True},
            {'id': 302, 'number': 'T20261127.0302', 'title': 'Nieuwe CA-regel: MFA voor alle gebruikers', 'company': 'Bakkerij De Korenaar', 'description': 'Eerst in alleen-rapporteren, na een week aan.',
             'info': ['Impact: gebruikers moeten MFA registreren'], 'status': 'New', 'priority': 'High', 'approval': 'Requested', 'created': '27-11-2026', 'assigned': 'Tweede Lijn A',
             'url': '', 'votes': [], 'myVote': None, 'iAmApprover': False},
            {'id': 303, 'number': 'T20261126.0303', 'title': 'Exchange: oude transportregel verwijderen', 'company': 'Stichting Zorgpunt', 'description': '', 'info': [],
             'status': 'In Progress', 'priority': 'Low', 'approval': 'Partially Approved', 'created': '26-11-2026', 'assigned': 'Tweede Lijn A', 'url': '',
             'votes': [{'name': 'Tweede Lijn A', 'vote': True, 'note': 'Akkoord'}], 'myVote': None, 'iAmApprover': False}]
API['sd.changes'] = lambda c, b: {'tickets': [t for t in _CHANGES if t['myVote'] is None] + [t for t in _CHANGES if t['myVote'] is not None]}


def _changes_stem(c, b):
    ja = b.get('decision') == 'approve'
    if not ja and len(str(b.get('note') or '').strip()) < 5:
        raise ApiFout('Schrijf bij afkeuren kort waarom.')
    for t in _CHANGES:
        if t['id'] in b.get('ids', []):
            t['myVote'] = ja
            t['votes'] = [v for v in t['votes'] if v['name'] != 'Beheerder Test'] + [{'name': 'Beheerder Test', 'vote': ja, 'note': b.get('note') or ''}]
    c.L(f"(testmodus) {len(b.get('ids', []))} change(s) {'goedgekeurd' if ja else 'afgekeurd'}.")
    return {'results': [{'id': i, 'ok': True} for i in b.get('ids', [])], 'ok': len(b.get('ids', [])), 'failed': 0}


API['sd.changes.stem'] = _changes_stem


def _sd_kpi(c, b):
    time.sleep(0.7)
    dagen = int(b.get('days') or 30)
    f = dagen / 30
    weken = [{'week': f'2026-W{w}', 'created': c_, 'resolved': r, 'l1': l, 'l1Pct': round(l * 100 / r, 1)} for w, c_, r, l in
             ((44, 61, 58, 41), (45, 70, 66, 49), (46, 64, 67, 52), (47, 72, 69, 57), (48, 58, 55, 47))]
    return {'days': dagen, 'at': time.strftime('%H:%M'), 'ingericht': True, 'goals': {'l1': 85, 'escalation': 15, 'triageMin': 15},
            'kpi': {'created': int(296 * f), 'resolved': int(281 * f), 'open': 47, 'openL1': 31, 'openL2': 16, 'unassigned': 6, 'overdue': 4,
                    'l1Pct': 76.4, 'l1Resolved': int(204 * f), 'l2Resolved': int(63 * f), 'otherResolved': int(14 * f), 'escalated': int(58 * f), 'escalationPct': 19.6,
                    'medianHoursL1': 3.2, 'medianHoursL2': 26.5, 'medianHours': 5.1, 'firstResponseMedianH': 0.4, 'firstResponseAvgH': 1.1, 'slaPct': 91.3},
            'hours': {'l1': round(212 * f, 1), 'l2': round(318 * f, 1), 'overig': round(22 * f, 1)},
            'billable': {'l1': round(64 * f, 1), 'l2': round(141 * f, 1), 'overig': 0},
            'revenue': {'l1': round(4800 * f, 2), 'l2': round(16215 * f, 2), 'overig': 0},
            'employees': [{'id': 30, 'name': 'Beheerder Test', 'level': 'l1', 'resolved': 41, 'open': 4, 'hours': 52.5, 'medianHours': 2.1},
                          {'id': 33, 'name': 'Servicedesk C', 'level': 'l1', 'resolved': 78, 'open': 9, 'hours': 71.0, 'medianHours': 3.0},
                          {'id': 34, 'name': 'Servicedesk D', 'level': 'l1', 'resolved': 66, 'open': 11, 'hours': 64.3, 'medianHours': 3.8},
                          {'id': 35, 'name': 'Stagiair E', 'level': 'l1', 'resolved': 19, 'open': 7, 'hours': 24.2, 'medianHours': 6.4},
                          {'id': 31, 'name': 'Tweede Lijn A', 'level': 'l2', 'resolved': 34, 'open': 9, 'hours': 161.0, 'medianHours': 22.0},
                          {'id': 32, 'name': 'Tweede Lijn B', 'level': 'l2', 'resolved': 29, 'open': 7, 'hours': 157.0, 'medianHours': 31.5}],
            'trend': weken,
            'oldest': [{'id': 203, 'number': 'T20261028.0203', 'title': 'Migratie fileserver naar SharePoint', 'company': 'Installatiebedrijf Bos', 'days': 31, 'level': 'l2', 'assigned': 'Tweede Lijn B', 'url': ''},
                       {'id': 104, 'number': 'T20261112.0104', 'title': 'Nieuwe medewerker per 1 december', 'company': 'Bakkerij De Korenaar', 'days': 16, 'level': 'l1', 'assigned': 'Servicedesk D', 'url': ''}],
            'signals': [{'level': 'warn', 'text': 'L1 handelt 76,4% af; doel is 85%.'}, {'level': 'warn', 'text': '19,6% van de tickets gaat naar L2 (maximaal 15%).'},
                        {'level': 'warn', 'text': '6 open ticket(s) zonder behandelaar.'}, {'level': 'err', 'text': '4 open ticket(s) over de deadline.'}]}


API['sd.kpi'] = _sd_kpi


def _fa_ophalen(dagen):
    tijd = []
    n = 5000
    regels = [(101, 701, 33, 1.0, 'Outlook-profiel opnieuw aangemaakt', None), (101, 701, 31, 0.5, 'Exchange-regel gecontroleerd', None),
              (101, 702, 31, 3.0, 'Intune-inschrijving laptops verkoop', None), (102, 703, 34, 0.25, 'Wachtwoord opnieuw ingesteld', None),
              (102, 704, 32, 4.0, 'Firewall-configuratie VPN aangepast', None), (102, 704, 32, 2.0, 'VPN-tunnel getest met klant', None),
              (103, 705, 33, 0.75, 'Printer opnieuw geïnstalleerd', None), (101, 706, 33, 2.0, 'Werk binnen contract (telt niet)', 9001)]
    for i, (comp, tk, res, uur, tekst, con) in enumerate(regels):
        tijd.append({'id': n + i, 'ticketID': tk, 'taskID': None, 'resourceID': res, 'roleID': 1 if res in (31, 32) else 2, 'dateWorked': f'2026-11-{10 + i:02d}T00:00:00Z',
                     'hoursWorked': uur, 'hoursToBill': uur, 'summaryNotes': tekst, 'contractID': con})
    tickets = {701: {'id': 701, 'ticketNumber': 'T20261110.0701', 'title': 'Outlook en Exchange problemen', 'companyID': 101},
               702: {'id': 702, 'ticketNumber': 'T20261112.0702', 'title': 'Laptops verkoop inschrijven', 'companyID': 101},
               703: {'id': 703, 'ticketNumber': 'T20261113.0703', 'title': 'Wachtwoord vergeten', 'companyID': 102},
               704: {'id': 704, 'ticketNumber': 'T20261114.0704', 'title': 'VPN valt weg', 'companyID': 102},
               705: {'id': 705, 'ticketNumber': 'T20261116.0705', 'title': 'Printer offline', 'companyID': 103},
               706: {'id': 706, 'ticketNumber': 'T20261117.0706', 'title': 'Regulier beheer', 'companyID': 101},
               707: {'id': 707, 'ticketNumber': 'T20261120.0707', 'title': 'Licentie Business Premium toegevoegd (2x)', 'companyID': 103}}
    return {'tijd': tijd, 'rti': [707], 'contracten': {9001: {'id': 9001, 'contractType': 7, 'contractName': 'Full service'}}, 'tm': {1}, 'tickets': tickets,
            'taken': {}, 'projecten': {}, 'bedrijven': {101: 'Bakkerij De Korenaar B.V.', 102: 'Advocatenkantoor De Wit', 103: 'Installatiebedrijf Bos'},
            'mensen': _SD_MENSEN, 'rollen': {1: {'id': 1, 'name': 'Engineer', 'hourlyRate': 115}, 2: {'id': 2, 'name': 'Servicedesk', 'hourlyRate': 75}},
            'link': lambda tid: '', 'eind': {'complete': 5, 'invoice': 12}, 'alGeboekt': 12.5, 'geboektBekend': True}


_HFA.ophalen = _fa_ophalen


# ---------- v2.34: timesheet (nagebootst, tijdregels in het geheugen) ----------
def _ts_start():
    from datetime import datetime, timedelta
    vandaag = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    uit = []
    for dag, blokken in ((0, [(8, 30, 60, 'ticket', 101, 'Wachtwoord vergeten, kan niet inloggen', 'T20261128.0101', 'Bakkerij De Korenaar', 'Wachtwoord gereset en MFA opnieuw geregistreerd'),
                              (10, 0, 45, 'algemeen', 9, 'Overleg', '', '', 'Teamoverleg servicedesk'),
                              (11, 0, 90, 'taak', 701, 'Mailboxen migreren', 'Migratie naar Microsoft 365', 'Bakkerij De Korenaar', 'Batch 2 gestart')]),
                         (-1, [(9, 0, 120, 'ticket', 103, 'Printer op de tweede verdieping offline', 'T20261128.0103', 'Installatiebedrijf Bos', 'Driver opnieuw uitgerold')])):
        for h, m, duur, soort, ref, titel, nr, bedr, tekst in blokken:
            s = vandaag + timedelta(days=dag, hours=h, minutes=m)
            uit.append({'id': 8000 + len(uit), 'kind': soort, 'start': s.astimezone().isoformat(), 'end': (s + timedelta(minutes=duur)).astimezone().isoformat(),
                        'hours': duur / 60, 'notes': tekst, 'locked': False, 'refId': ref, 'title': titel, 'ref': nr, 'company': bedr, 'url': ''})
    return uit


_TS: list = _ts_start()


def _ts_periode(c, b):
    from datetime import datetime
    van, tot = datetime.fromisoformat(b['from'].replace('Z', '+00:00')), datetime.fromisoformat(b['to'].replace('Z', '+00:00'))
    time.sleep(0.3)
    return {'entries': sorted([e for e in _TS if van <= datetime.fromisoformat(e['start']) < tot], key=lambda e: e['start']), 'me': 'Beheerder Test'}


def _ts_nieuw(c, b):
    from datetime import datetime
    s, t = datetime.fromisoformat(b['start'].replace('Z', '+00:00')), datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
    if t <= s:
        raise ApiFout('De eindtijd moet na de begintijd liggen.')
    if b['kind'] != 'algemeen' and len(str(b.get('notes') or '').strip()) < 3:
        raise ApiFout('Schrijf kort wat je hebt gedaan (Autotask vraagt een omschrijving bij ticket- en projecttijd).')
    bron = next((x for x in _TS_BRON['tickets'] + _TS_BRON['tasks'] + _TS_BRON['codes'] if x['kind'] == b['kind'] and x['id'] == b['refId']), {})
    _TS.append({'id': 8000 + len(_TS) + int(time.time()) % 1000, 'kind': b['kind'], 'start': s.astimezone().isoformat(), 'end': t.astimezone().isoformat(),
                'hours': (t - s).total_seconds() / 3600, 'notes': b.get('notes') or '', 'locked': False, 'refId': b['refId'], 'title': bron.get('title', ''),
                'ref': bron.get('ref', ''), 'company': bron.get('company', ''), 'url': ''})
    c.L(f"(testmodus) Tijd geboekt: {(t - s).total_seconds() / 3600:.2f} uur.")
    return {'id': _TS[-1]['id']}


def _ts_wijzig(c, b):
    from datetime import datetime
    for e in _TS:
        if e['id'] == int(b['id']):
            if b.get('start'):
                s, t = datetime.fromisoformat(b['start'].replace('Z', '+00:00')), datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
                e.update(start=s.astimezone().isoformat(), end=t.astimezone().isoformat(), hours=(t - s).total_seconds() / 3600)
            if 'notes' in b:
                e['notes'] = b['notes']
    return {}


_TS_BRON = {'tickets': [{'kind': 'ticket', 'id': 101, 'ref': 'T20261128.0101', 'title': 'Wachtwoord vergeten, kan niet inloggen', 'company': 'Bakkerij De Korenaar', 'mine': True, 'url': ''},
                        {'kind': 'ticket', 'id': 106, 'ref': 'T20261128.0106', 'title': 'Teams-vergadering geen geluid', 'company': 'Stichting Zorgpunt', 'mine': True, 'url': ''},
                        {'kind': 'ticket', 'id': 103, 'ref': 'T20261128.0103', 'title': 'Printer op de tweede verdieping offline', 'company': 'Installatiebedrijf Bos', 'mine': False, 'url': ''}],
            'tasks': [{'kind': 'taak', 'id': 701, 'title': 'Mailboxen migreren', 'ref': 'Migratie naar Microsoft 365', 'company': 'Bakkerij De Korenaar'},
                      {'kind': 'taak', 'id': 690, 'title': 'MFA uitrollen', 'ref': 'Beveiliging op orde', 'company': 'Bakkerij De Korenaar'}],
            'codes': [{'kind': 'algemeen', 'id': 9, 'title': 'Overleg', 'ref': '', 'company': ''}, {'kind': 'algemeen', 'id': 10, 'title': 'Opleiding', 'ref': '', 'company': ''},
                      {'kind': 'algemeen', 'id': 11, 'title': 'Administratie', 'ref': '', 'company': ''}]}
API['ts.periode'] = _ts_periode
API['ts.bronnen'] = lambda c, b: (time.sleep(0.4), _TS_BRON)[1]
API['ts.projecten'] = lambda c, b: ({'tasks': [{'kind': 'taak', 'id': 702, 'title': 'Intune-inschrijving laptops', 'ref': b.get('projectName', ''), 'company': b.get('company', '')},
                                               {'kind': 'taak', 'id': 703, 'title': 'Gebruikers informeren', 'ref': b.get('projectName', ''), 'company': b.get('company', '')}]}
                                    if b.get('projectId') else {'projects': [p for p in [{'id': 61, 'name': 'Migratie naar Microsoft 365', 'number': 'P20261101.0003', 'company': 'Bakkerij De Korenaar'},
                                                                                         {'id': 59, 'name': 'Nieuwe kantoorlocatie', 'number': 'P20260801.0002', 'company': 'Bakkerij De Korenaar'}]
                                                                             if str(b.get('q') or '').lower() in p['name'].lower()]})
API['ts.nieuw'] = _ts_nieuw
API['ts.wijzig'] = _ts_wijzig
API['ts.verwijder'] = lambda c, b: (_TS.__setitem__(slice(None), [e for e in _TS if e['id'] != int(b['id'])]), {})[1]


# ---------- v2.35: sales en projecten (nagebootst, in het geheugen) ----------
_SA = [{'id': 401, 'title': 'Nieuwe inrichting Microsoft 365 + IMAP-migratie', 'company': 'Installatiebedrijf Bos', 'companyId': 102, 'contact': 'Jan Bos', 'contactId': None,
        'owner': 'Verkoper Test', 'amount': 6850.0, 'cost': 0, 'monthly': 0, 'probability': 70, 'close': '2026-12-15', 'closed': '', 'stage': 2, 'stageLabel': 'Offerte verstuurd',
        'status': 'Active', 'final': False, 'description': '12 gebruikers, mailboxen van de oude provider overzetten, Intune voor 10 laptops.', 'created': '2026-11-20', 'project': None},
       {'id': 402, 'title': 'Back-up en monitoring (SaaS Protection)', 'company': 'Advocatenkantoor De Wit', 'companyId': 103, 'contact': '', 'contactId': None, 'owner': 'Verkoper Test',
        'amount': 2400.0, 'cost': 0, 'monthly': 200, 'probability': 40, 'close': '2027-01-10', 'closed': '', 'stage': 1, 'stageLabel': 'Kennismaking', 'status': 'Active', 'final': False,
        'description': '', 'created': '2026-11-22', 'project': None},
       {'id': 403, 'title': 'Migratie fileserver naar SharePoint', 'company': 'Bakkerij De Korenaar B.V.', 'companyId': 101, 'contact': 'Sanne Voorbeeld', 'contactId': 501,
        'owner': 'Verkoper Test', 'amount': 4200.0, 'cost': 0, 'monthly': 0, 'probability': 100, 'close': '2026-11-25', 'closed': '2026-11-26', 'stage': 3, 'stageLabel': 'Akkoord',
        'status': 'Closed', 'final': True, 'description': 'Mappen per afdeling, rechten via groepen, oude schijf daarna alleen-lezen.', 'created': '2026-11-01', 'project': None}]


def _sa_ov(c, b):
    time.sleep(0.4)
    o = [x for x in _SA if not x['final']]
    return {'opportunities': sorted(_SA, key=lambda x: (x['final'], x['close'])), 'canEdit': True, 'at': time.strftime('%H:%M'),
            'totals': {'open': len(o), 'pipeline': sum(x['amount'] for x in o), 'weighted': sum(x['amount'] * x['probability'] / 100 for x in o),
                       'won': sum(1 for x in _SA if x['final']), 'wonAmount': sum(x['amount'] for x in _SA if x['final']), 'noProject': sum(1 for x in _SA if x['final'] and not x['project'])}}


def _sa_opslaan(c, b):
    if b.get('id'):
        for x in _SA:
            if x['id'] == b['id']:
                x.update(title=b['title'], amount=b.get('amount', x['amount']), probability=b.get('probability', x['probability']), description=b.get('description', ''))
    else:
        _SA.append({'id': 410 + len(_SA), 'title': b['title'], 'company': 'Stichting Zorgpunt', 'companyId': b['companyId'], 'contact': '', 'contactId': b.get('contactId'),
                    'owner': 'Beheerder Test', 'amount': b.get('onetime', 0) + b.get('monthly', 0) * b.get('months', 0), 'cost': b.get('cost', 0), 'monthly': b.get('monthly', 0),
                    'probability': b.get('probability', 50), 'close': b.get('close') or '2026-12-31', 'closed': '', 'stage': b.get('stage'), 'stageLabel': 'Kennismaking',
                    'status': 'Active', 'final': False, 'description': b.get('description', ''), 'created': '2026-11-28', 'project': None})
    c.L('(testmodus) Saleskans opgeslagen.')
    return {'id': 1}


API['sa.opties'] = lambda c, b: {'stages': [{'value': 1, 'label': 'Kennismaking'}, {'value': 2, 'label': 'Offerte verstuurd'}, {'value': 3, 'label': 'Akkoord'}],
                                 'ratings': [], 'sources': [], 'categories': [], 'canEdit': True}
API['sa.overzicht'] = _sa_ov
API['sa.opslaan'] = _sa_opslaan
API['sa.definitief'] = lambda c, b: ([x.update(final=True, status='Closed', closed='2026-11-28', probability=100) for x in _SA if x['id'] == b['id']], c.L('(testmodus) Kans definitief.'), {})[2]
API['sa.verloren'] = lambda c, b: (_SA.__setitem__(slice(None), [x for x in _SA if x['id'] != b['id']]), {})[1]
API['pr.templates'] = lambda c, b: {'templates': [{'id': 900, 'name': 'Template: Nieuwe inrichting M365', 'description': ''}, {'id': 901, 'name': 'Template: Migratie naar SharePoint', 'description': ''}],
                                    'people': [{'id': k, 'name': v} for k, v in _SD_MENSEN.items()]}

_PR = {61: {'id': 61, 'name': 'Migratie naar Microsoft 365', 'number': 'P20261101.0003', 'company': 'Bakkerij De Korenaar B.V.', 'companyId': 101, 'statusId': 1, 'start': '2026-11-01',
            'end': '2026-12-20', 'leadId': 31, 'description': 'Alle mailboxen van de oude provider naar Exchange Online, daarna Intune.', 'url': ''},
       60: {'id': 60, 'name': 'Beveiliging op orde', 'number': 'P20260912.0001', 'company': 'Bakkerij De Korenaar B.V.', 'companyId': 101, 'statusId': 2, 'start': '2026-09-12',
            'end': '2026-11-15', 'leadId': 30, 'description': '', 'url': ''}}
_PR_TAKEN = [{'id': 701, 'p': 61, 'title': 'Mailboxen migreren', 'phaseId': 1, 'statusId': 2, 'assignedId': 30, 'estimated': 8, 'worked': 5.5, 'end': '2026-12-05'},
             {'id': 702, 'p': 61, 'title': 'Intune-inschrijving laptops', 'phaseId': 2, 'statusId': 1, 'assignedId': 31, 'estimated': 6, 'worked': 0, 'end': '2026-12-15'},
             {'id': 703, 'p': 61, 'title': 'Gebruikers informeren', 'phaseId': 1, 'statusId': 5, 'assignedId': 30, 'estimated': 1, 'worked': 1, 'end': '2026-11-10'},
             {'id': 704, 'p': 61, 'title': 'DNS omzetten (MX, autodiscover)', 'phaseId': 1, 'statusId': 1, 'assignedId': None, 'estimated': 1, 'worked': 0, 'end': '2026-12-06'},
             {'id': 690, 'p': 60, 'title': 'MFA uitrollen', 'phaseId': None, 'statusId': 2, 'assignedId': 30, 'estimated': 4, 'worked': 3, 'end': '2026-11-10'},
             {'id': 691, 'p': 60, 'title': 'Voorwaardelijke toegang inrichten', 'phaseId': None, 'statusId': 1, 'assignedId': 31, 'estimated': 3, 'worked': 0, 'end': '2026-11-14'}]
_TST = {1: 'New', 2: 'In Progress', 5: 'Complete'}


def _pr_ov(c, b):
    time.sleep(0.4)
    uit = []
    for p in _PR.values():
        t = [x for x in _PR_TAKEN if x['p'] == p['id']]
        uit.append({'id': p['id'], 'name': p['name'], 'number': p['number'], 'company': p['company'], 'status': {1: 'New', 2: 'Active'}.get(p['statusId'], ''), 'statusId': p['statusId'],
                    'type': 'Client', 'start': p['start'], 'end': p['end'], 'late': p['end'] < time.strftime('%Y-%m-%d') and any(x['statusId'] != 5 for x in t),
                    'lead': _SD_MENSEN.get(p['leadId'], ''), 'leadId': p['leadId'], 'tasks': len(t), 'done': sum(1 for x in t if x['statusId'] == 5),
                    'estimated': sum(x['estimated'] for x in t), 'members': sorted({x['assignedId'] for x in t if x['assignedId'] and x['statusId'] != 5}), 'opportunityId': None})
    return {'projects': uit, 'mine': [p['id'] for p in uit if 30 in p['members'] or p['leadId'] == 30], 'me': 30, 'at': time.strftime('%H:%M')}


def _pr_project(c, b):
    time.sleep(0.3)
    p = _PR[int(b['id'])]
    t = [x for x in _PR_TAKEN if x['p'] == p['id']]
    return {'project': p, 'phases': [{'id': 1, 'title': 'Fase 1: E-mail', 'end': '2026-12-06'}, {'id': 2, 'title': 'Fase 2: Apparaten', 'end': '2026-12-20'}] if p['id'] == 61 else [],
            'tasks': [{'id': x['id'], 'title': x['title'], 'description': '', 'status': _TST[x['statusId']], 'statusId': x['statusId'], 'done': x['statusId'] == 5, 'phaseId': x['phaseId'],
                       'assigned': _SD_MENSEN.get(x['assignedId'], ''), 'assignedId': x['assignedId'], 'estimated': x['estimated'], 'worked': x['worked'], 'start': '', 'end': x['end'],
                       'late': x['end'] < time.strftime('%Y-%m-%d') and x['statusId'] != 5} for x in t],
            'notes': [{'id': 1, 'title': 'Kick-off', 'text': 'Afspraken met de klant: migratie in het weekend.', 'at': '2026-11-02 10:00'}],
            'people': [{'id': k, 'name': v} for k, v in _SD_MENSEN.items()], 'taskStatuses': [{'value': k, 'label': v} for k, v in _TST.items()],
            'projectStatuses': [{'value': 1, 'label': 'New'}, {'value': 2, 'label': 'Active'}, {'value': 5, 'label': 'Complete'}]}


def _pr_taak(c, b):
    for x in _PR_TAKEN:
        if x['id'] in [int(i) for i in (b.get('ids') or [b.get('id')])]:
            if b.get('status') not in (None, ''):
                x['statusId'] = int(b['status'])
            if 'assignedId' in b:
                x['assignedId'] = int(b['assignedId']) if b['assignedId'] else None
    return {}


def _pr_vankans(c, b):
    time.sleep(1)
    nid = max(_PR) + 1
    kans = next(x for x in _SA if x['id'] == b['opportunityId'])
    _PR[nid] = {'id': nid, 'name': b['name'], 'number': f'P20261128.{nid:04d}', 'company': kans['company'], 'companyId': kans['companyId'], 'statusId': 1, 'start': b['start'],
                'end': b['end'], 'leadId': b.get('leadId'), 'description': b.get('description', ''), 'url': ''}
    n = 0
    if b.get('templateId'):
        for i, titel in enumerate(['Inventarisatie', 'Tenant inrichten', 'Mailboxen migreren', 'Overdracht en documentatie']):
            _PR_TAKEN.append({'id': 7000 + nid * 10 + i, 'p': nid, 'title': titel, 'phaseId': None, 'statusId': 1, 'assignedId': None, 'estimated': 2, 'worked': 0, 'end': b['end']})
            n += 1
    kans['project'] = {'id': nid, 'name': b['name'], 'number': _PR[nid]['number']}
    c.L(f"(testmodus) Project '{b['name']}' aangemaakt met {n} taken.")
    return {'id': nid, 'phases': 0, 'tasks': n, 'errors': []}


API['pr.overzicht'] = _pr_ov
API['pr.project'] = _pr_project
API['pr.taak'] = _pr_taak
API['pr.taak.nieuw'] = lambda c, b: (_PR_TAKEN.append({'id': 7900 + len(_PR_TAKEN), 'p': int(b['projectId']), 'title': b['title'], 'phaseId': b.get('phaseId') and int(b['phaseId']),
                                                       'statusId': 1, 'assignedId': b.get('assignedId') and int(b['assignedId']), 'estimated': float(b.get('estimated') or 0), 'worked': 0,
                                                       'end': b.get('end') or ''}), {})[1]
API['pr.status'] = lambda c, b: (_PR[int(b['id'])].update({k: v for k, v in (('statusId', b.get('status')), ('leadId', b.get('leadId'))) if v}), {})[1]
API['pr.notitie'] = lambda c, b: (c.L('(testmodus) Projectnotitie toegevoegd.'), {})[1]
API['pr.vankans'] = _pr_vankans
API['app.rol'] = lambda c, b: {'admin': True, 'justdata': True, 'directie': True, 'billing': True, 'sales': True, 'salesEdit': True}


# ---------- v2.35.2: notities, bijlagen en nieuwe klant bij saleskansen (nagebootst) ----------
_SA_NOTES: dict = {401: [{'id': 1, 'title': 'Gesprek met Jan', 'text': 'Wil per 1 januari over. Offerte incl. 10 laptops.', 'by': 'Verkoper Test', 'at': '2026-11-21 10:15'}]}
_SA_FILES: dict = {401: [{'id': 1, 'name': 'Offerte JDQ10023.pdf', 'title': 'Offerte', 'at': '2026-11-21 10:20'}]}


def _sa_notitie(c, b):
    lijst = _SA_NOTES.setdefault(int(b['id']), [])
    if b.get('remove'):
        lijst[:] = [n for n in lijst if n['id'] != b['noteId']]
    elif b.get('noteId'):
        for n in lijst:
            if n['id'] == b['noteId']:
                n.update(title=b['title'], text=b['text'])
    else:
        lijst.insert(0, {'id': len(lijst) + 10, 'title': b.get('title') or 'Notitie', 'text': b['text'], 'by': 'Beheerder Test', 'at': time.strftime('%Y-%m-%d %H:%M')})
    return {}


def _sa_bijlage(c, b):
    lijst = _SA_FILES.setdefault(int(b['id']), [])
    if b.get('open'):
        c.L('(testmodus) Bijlage zou nu in Downloads worden geopend.')
        return {'path': ''}
    if b.get('remove'):
        lijst[:] = [x for x in lijst if x['id'] != b['fileId']]
    else:
        lijst.insert(0, {'id': len(lijst) + 10, 'name': b['name'], 'title': b['name'], 'at': time.strftime('%Y-%m-%d %H:%M')})
    return {}


API['sa.notities'] = lambda c, b: {'notes': list(_SA_NOTES.get(int(b['id']), [])), 'files': list(_SA_FILES.get(int(b['id']), []))}
API['sa.notitie'] = _sa_notitie
API['sa.bijlage'] = _sa_bijlage
API['sa.bedrijf.nieuw'] = lambda c, b: (time.sleep(0.6), c.L(f"(testmodus) Klant {b['name']} aangemaakt (Customer) met primaire contactpersoon."),
                                        {'company': {'id': 150, 'name': b['name']}, 'contact': {'id': 650, 'name': f"{b['firstName']} {b['lastName']}"}})[2]
API['sa.overzicht'] = (lambda f: lambda c, b: {**f(c, b), 'canStatus': True, 'canProject': True})(API['sa.overzicht'])


# ---------- v2.36: snel ticket in de timesheet en Datto RMM (nagebootst) ----------
def _ts_ticket(c, b):
    from datetime import datetime
    if len(str(b.get('title') or '').strip()) < 3 or not b.get('companyId'):
        raise ApiFout('Kies de klant en vul het onderwerp in.')
    s, t = datetime.fromisoformat(b['start'].replace('Z', '+00:00')), datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
    nr = f'T{time.strftime("%Y%m%d")}.{len(_TS) + 900:04d}'
    _TS.append({'id': 8500 + len(_TS), 'kind': 'ticket', 'start': s.astimezone().isoformat(), 'end': t.astimezone().isoformat(), 'hours': (t - s).total_seconds() / 3600,
                'notes': b['notes'], 'locked': False, 'refId': 950, 'title': b['title'], 'ref': nr, 'company': 'Klant', 'url': ''})
    gesloten = (b.get('endStatus') == 'invoice' and 'invoice' or 'complete') if b.get('done') else ''
    c.L(f"(testmodus) Ticket {nr} achteraf aangemaakt" + (f' en afgerond ({gesloten})' if gesloten else '') + '.')
    return {'ticket': {'id': 950, 'number': nr}, 'closed': gesloten}


_RMM = {'configured': False}
API['ts.ticket'] = _ts_ticket
API['rmm.status'] = lambda c, b: {'configured': _RMM['configured'], 'url': 'https://merlot-api.centrastage.net' if _RMM['configured'] else '', 'admin': True}
API['rmm.keys.set'] = lambda c, b: (_RMM.update(configured=True), c.L('(testmodus) Datto RMM gekoppeld.'), {'configured': True})[2]
API['rmm.keys.delete'] = lambda c, b: (_RMM.update(configured=False), {'configured': False})[1]
API['rmm.site.nieuw'] = lambda c, b: (time.sleep(0.6), c.L(f"(testmodus) Site {b['name']} aangemaakt in Datto RMM."),
                                      {'exists': False, 'site': {'uid': 'abc-123', 'name': b['name'], 'url': ''}})[2]


def _sa_status(c, b):
    for x in list(_SA):
        if x['id'] in b.get('ids', []):
            if b['action'] == 'final':
                x.update(final=True, status='Closed', closed=time.strftime('%Y-%m-%d'), probability=100)
            elif b['action'] == 'delete':
                _SA.remove(x)
            else:
                _SA.remove(x)
    c.L(f"(testmodus) {len(b.get('ids', []))} kans(en): {b['action']}.")
    return {'ok': len(b.get('ids', []))}


API['sa.status'] = _sa_status


# ---------- v2.37: langlopende tickets en per-klantverdeling (nagebootst) ----------
_LANG: set = set()


def _met_lang(f):
    def g(*a, **k):
        r = f(*a, **k)
        for t in r:
            t['longRunning'] = t['id'] in _LANG
            if t['longRunning']:
                t['overdue'] = False
        return r
    return g


_HSD._tickets = _met_lang(_HSD._tickets)
_HSDN._queue_tickets = _met_lang(_HSDN._queue_tickets)


def _sd_lang(c, b):
    for i in b.get('ids') or []:
        (_LANG.add if b.get('on', True) else _LANG.discard)(int(i))
    _HSD._CACHE.clear()
    _HSDN._CACHE.clear()
    c.L(f"(testmodus) {len(b.get('ids') or [])} ticket(s) {'langlopend' if b.get('on', True) else 'weer normaal'}.")
    return {'ok': len(b.get('ids') or [])}


API['sd.langlopend'] = _sd_lang


def _kpi_extra(f):
    def g(c, b):
        r = f(c, b)
        tops = {30: ('Bakkerij De Korenaar', 61), 33: ('Installatiebedrijf Bos', 34), 34: ('Bakkerij De Korenaar', 40), 35: ('Stichting Zorgpunt', 72),
                31: ('Stichting Zorgpunt', 45), 32: ('Advocatenkantoor De Wit', 38)}
        for m in r['employees']:
            n, p = tops.get(m['id'], ('', 0))
            m['topCompany'] = {'name': n, 'pct': p, 'count': round((m['resolved'] + m['open']) * p / 100)} if n else None
        r['kpi']['longRunning'] = len(_LANG) or 3
        return r
    return g


API['sd.kpi'] = _kpi_extra(API['sd.kpi'])


# ---------- v2.38: voorraad, producten op tickets, contracten (nep-Autotask uitgebreid; de echte code draait erop) ----------
_V = {
    'Products': [
        {'id': 801, 'name': 'EliteBook 840 G11 (16 GB, 512 GB)', 'manufacturerName': 'HP', 'manufacturerProductName': '9G0K3ET', 'sKU': 'HP-840G11', 'unitCost': 1049.0, 'unitPrice': 1299.0, 'isActive': True},
        {'id': 802, 'name': 'USB-C Dock G5', 'manufacturerName': 'HP', 'manufacturerProductName': '5TW10AA', 'sKU': 'HP-DOCK-G5', 'unitCost': 159.0, 'unitPrice': 219.0, 'isActive': True},
        {'id': 803, 'name': 'Monitor 24 inch P24 G5', 'manufacturerName': 'HP', 'manufacturerProductName': '64X66AA', 'sKU': '', 'unitCost': 139.0, 'unitPrice': 189.0, 'isActive': True},
        {'id': 804, 'name': 'MX Keys Business toetsenbord', 'manufacturerName': 'Logitech', 'manufacturerProductName': '920-010245', 'sKU': '', 'unitCost': 79.0, 'unitPrice': 115.0, 'isActive': True},
        {'id': 805, 'name': 'Chromebook-scherm (reparatie)', 'manufacturerName': 'Lenovo', 'manufacturerProductName': '', 'sKU': '', 'unitCost': 64.0, 'unitPrice': 95.0, 'isActive': True}],
    'TicketCharges': [{'id': 9101, 'ticketID': 702, 'name': 'HP EliteBook 840 G11 (16 GB, 512 GB)', 'productID': 801, 'unitQuantity': 2, 'unitPrice': 1299.0,
                       'datePurchased': '2026-11-12T10:00:00Z', 'isBillableToCompany': True, 'isBilled': False}],
    'Contracts': [], 'ContractMilestones': [], 'ContractServices': [], 'ContractExclusionBillingCodes': [],
    'BillingCodes': [{'id': 29682801, 'name': 'Remote support', 'useType': 1, 'isActive': True}, {'id': 29682810, 'name': 'After Hours Support', 'useType': 1, 'isActive': True},
                     {'id': 29682811, 'name': 'Emergency (spoed)', 'useType': 1, 'isActive': True}, {'id': 29682820, 'name': 'Hardware', 'useType': 2, 'isActive': True},
                     {'id': 29682830, 'name': 'Milestone', 'useType': 4, 'isActive': True}],
    'Services': [{'id': 601, 'name': 'Full Service per werkplek', 'unitPrice': 49.5, 'isActive': True}, {'id': 602, 'name': 'Microsoft 365 beheer', 'unitPrice': 12.0, 'isActive': True}],
    'Tickets': [{'id': i, 'ticketNumber': f'T20261127.{i:04d}', 'title': t, 'companyID': 101} for i, t in
                [(1, 'Outlook start niet op bij receptie'), (2, 'Nieuwe medewerker per 1 december'), (3, 'Offerte nieuwe firewall'), (4, 'Printer op de werkplaats drukt niet meer af'),
                 (5, 'VPN werkt niet thuis'), (6, 'Migratie fileserver naar SharePoint'), (7, 'Wachtwoord vergeten')]],
    'Companies': [{'id': 101, 'companyName': 'Bakkerij De Korenaar B.V.'}, {'id': 102, 'companyName': 'Advocatenkantoor De Wit'}, {'id': 103, 'companyName': 'Installatiebedrijf Bos'}],
}
_V_PL = {
    'TicketCharges': {'chargeType': [{'value': 1, 'label': 'Operational'}, {'value': 2, 'label': 'Capitalized'}], 'costType': [{'value': 1, 'label': 'Billable'}, {'value': 2, 'label': 'Internal'}]},
    'Contracts': {'contractType': [{'value': 1, 'label': 'Time and Materials'}, {'value': 3, 'label': 'Fixed Price'}, {'value': 4, 'label': 'Block Hours'}, {'value': 7, 'label': 'Recurring Service'}],
                  'status': [{'value': 0, 'label': 'Inactive'}, {'value': 1, 'label': 'Active'}], 'contractPeriodType': [{'value': 'm', 'label': 'Monthly'}, {'value': 'y', 'label': 'Yearly'}]},
    'ContractMilestones': {'status': [{'value': 1, 'label': 'Ready to Bill'}, {'value': 2, 'label': 'Billed'}]},
    'BillingCodes': {'useType': [{'value': 1, 'label': 'Work Type'}, {'value': 2, 'label': 'Material Cost Code'}, {'value': 3, 'label': 'General/Regular Internal Time'}, {'value': 4, 'label': 'Milestone'}]},
    'Tickets': {'status': [{'value': 1, 'label': 'New'}, {'value': 8, 'label': 'In Progress'}, {'value': 5, 'label': 'Complete'}], 'priority': [{'value': 3, 'label': 'Low'}]},
}
_V_ID = [9500]
_oud_pl, _oud_q, _oud_req = _NEP_AT.picklists, _NEP_AT.query, _NEP_AT.req


def _v_pl(entiteit):
    if entiteit in _V_PL:
        return {k: [dict(p, default=False, parent=None) for p in v] for k, v in _V_PL[entiteit].items()}
    return _oud_pl(entiteit)


def _v_q(entiteit, filters, velden=None, max_=500, limiet=2000):
    if entiteit not in _V:
        return _oud_q(entiteit, filters, velden, max_, limiet)
    uit = list(_V[entiteit])
    for f in filters:
        w, veld = f.get('value'), f['field']
        if f['op'] == 'eq':
            uit = [x for x in uit if x.get(veld) == w or str(x.get(veld)).lower() == str(w).lower()]
        elif f['op'] == 'in':
            uit = [x for x in uit if x.get(veld) in w]
        elif f['op'] == 'exist':
            uit = [x for x in uit if x.get(veld) is not None]
        elif f['op'] == 'gte':
            uit = [x for x in uit if str(x.get(veld) or '') >= str(w)]
    return uit[:max_]


_KIND = {'Charges': 'TicketCharges', 'Milestones': 'ContractMilestones', 'Services': 'ContractServices', 'ExclusionBillingCodes': 'ContractExclusionBillingCodes'}


def _v_req(methode, pad, body=None):
    import re as _re
    delen = pad.strip('/').split('/')
    if methode == 'POST':
        ent = _KIND.get(delen[-1], delen[-1] if delen[-1] in _V else '__oud') if len(delen) == 3 else delen[0]
    elif methode == 'DELETE' and len(delen) >= 3:
        ent = _KIND.get(delen[2], delen[0])
    else:
        ent = delen[0]
    if ent not in _V:
        return _oud_req(methode, pad, body)
    time.sleep(0.15)
    if methode == 'POST':
        _V_ID[0] += 1
        nid = _V_ID[0]
        rij = {**body, 'id': nid}
        if ent == 'Tickets':
            rij['ticketNumber'] = f'T20261128.{nid:04d}'
        if ent == 'TicketCharges':
            rij.setdefault('isBilled', False)
        _V[ent].append(rij)
        return {'itemId': nid}
    if methode == 'PATCH':
        x = next((r for r in _V[ent] if r['id'] == body['id']), None)
        if x:
            x.update(body)
        return {'itemId': body['id']}
    if methode == 'GET' and len(delen) == 2 and _re.fullmatch(r'\d+', delen[1]):
        return {'item': next((r for r in _V[ent] if r['id'] == int(delen[1])), None)}
    if methode == 'DELETE':
        cid = int(delen[-1])
        _V[ent] = [r for r in _V[ent] if r['id'] != cid]
        return {}
    return {}


_NEP_AT.picklists, _NEP_AT.query, _NEP_AT.req = _v_pl, _v_q, _v_req

# Voorraad en bestellijst om mee te beginnen (gedeelde opslag van de testmodus)
_HBK.GEDEELD.schrijf_raw('voorraad', __import__('json').dumps({
    'stock': {'801': 3, '802': 5, '803': 0, '804': 2, '805': 0},
    'orders': [{'id': 'o1', 'at': '2026-11-27T14:10', 'by': 'Servicedesk Medewerker', 'brand': 'Lenovo', 'name': 'Chromebook-scherm (reparatie)', 'qty': 1,
                'note': 'Scherm gebarsten, leerling-Chromebook', 'productId': 805, 'ticketId': 4, 'ticketNumber': 'T20261127.0004',
                'ticketTitle': 'Printer op de werkplaats drukt niet meer af', 'company': 'Installatiebedrijf Bos', 'status': 'open'},
               {'id': 'o2', 'at': '2026-11-28T09:02', 'by': 'Tweede Lijn A', 'brand': '', 'name': 'USB-C naar HDMI-adapter', 'qty': 2, 'note': '',
                'productId': None, 'ticketId': None, 'status': 'open'}]}))


def _fa_met_kosten(f):
    def g(dagen):
        r = f(dagen)
        r['charges'] = [x for x in _V['TicketCharges'] if x.get('isBillableToCompany') and not x.get('isBilled') and x.get('ticketID') in r['tickets']]
        con = {c['id']: c for c in _V['Contracts']}
        r['mijlpalen'] = [{**m, 'contract': con.get(m.get('contractID')) or {}} for m in _V['ContractMilestones'] if m.get('status') != 2]
        return r
    return g


_HFA.ophalen = _fa_met_kosten(_HFA.ophalen)
API['app.rol'] = lambda c, b: {'admin': True, 'justdata': True, 'directie': True, 'billing': True, 'sales': True, 'salesEdit': True}

_sdm_oud = API['sd.melding']
API['sd.melding'] = lambda c, b: {**_sdm_oud(c, b), **_HSDN._bestellingen(c)}



# ---------- v2.39: service calls (nep-Autotask + nep-agenda) en Datto RMM-apparaten ----------
_V.update({
    'ServiceCalls': [], 'ServiceCallTickets': [], 'ServiceCallTicketResources': [],
    'Resources': [{'id': 30, 'firstName': 'Beheerder', 'lastName': 'Test', 'email': 'beheerder@voorbeeld.nl', 'isActive': True},
                  {'id': 31, 'firstName': 'Tweede', 'lastName': 'Lijn A', 'email': 'tweede.a@voorbeeld.nl', 'isActive': True},
                  {'id': 36, 'firstName': 'Servicedesk', 'lastName': 'Medewerker', 'email': 'servicedesk@voorbeeld.nl', 'isActive': True}],
    'ResourceServiceDeskRoles': [{'resourceID': 30, 'roleID': 1, 'isActive': True}, {'resourceID': 31, 'roleID': 1, 'isActive': True},
                                 {'resourceID': 36, 'roleID': 11, 'isActive': True}, {'resourceID': 36, 'roleID': 12, 'isActive': True}],
    'Roles': [{'id': 1, 'name': 'Engineer'}, {'id': 11, 'name': 'Collega A'}, {'id': 12, 'name': 'Collega B'}],
})
_V_PL['Tickets']['status'].append({'value': 14, 'label': 'Planned'})
_KIND['Tickets'] = 'ServiceCallTickets'
_KIND['Resources'] = 'ServiceCallTicketResources'

from . import h_servicecall as _HSC  # noqa: E402
_RAW['agenda-app'] = __import__('json').dumps({'secret': 'test', 'end': '2028-11-28T00:00:00+00:00'})
_AGENDA: list = []


def _nep_graph(methode, pad, body=None):
    time.sleep(0.2)
    if methode == 'POST':
        _AGENDA.append({'id': f'ev{len(_AGENDA) + 1}', 'pad': pad, **(body or {})})
        return {'id': _AGENDA[-1]['id']}
    return {}


_HSC._graph = _nep_graph

# Datto RMM: nep-apparaten (de echte zoek- en sessiecode draait erop)
from . import h_rmm as _HRMM  # noqa: E402
_HRMM._sleutels = lambda: {'url': 'https://pinotage-api.centrastage.net', 'key': 'x', 'secret': 'y'}
_NEP_DEV = [
    {'uid': 'd-1', 'hostname': 'KOR-LT-001', 'lastLoggedInUser': 'KORENAAR\\anna.devries', 'siteName': 'Bakkerij De Korenaar B.V.', 'siteUid': 's-1', 'online': True,
     'operatingSystem': 'Windows 11 Pro 24H2', 'intIpAddress': '192.168.1.21', 'extIpAddress': '203.0.113.10', 'lastSeen': 1795870000000,
     'deviceType': {'category': 'Laptop'}, 'antivirus': {'antivirusProduct': 'Datto EDR', 'antivirusStatus': 'RunningAndUpToDate'}, 'patchManagement': {'patchStatus': 'FullyPatched'},
     'portalUrl': 'https://pinotage.centrastage.net/csm/search?qs=uid%3Ad-1'},
    {'uid': 'd-2', 'hostname': 'KOR-PC-RECEPTIE', 'lastLoggedInUser': 'KORENAAR\\receptie', 'siteName': 'Bakkerij De Korenaar B.V.', 'siteUid': 's-1', 'online': True,
     'operatingSystem': 'Windows 11 Pro 23H2', 'intIpAddress': '192.168.1.30', 'deviceType': {'category': 'Desktop'}, 'patchManagement': {'patchStatus': 'ApprovedPending'}},
    {'uid': 'd-3', 'hostname': 'BOS-LT-007', 'lastLoggedInUser': 'BOS\\jan.bos', 'siteName': 'Installatiebedrijf Bos', 'siteUid': 's-2', 'online': False,
     'operatingSystem': 'Windows 10 Pro 22H2', 'lastSeen': 1795600000000, 'deviceType': {'category': 'Laptop'}},
    {'uid': 'd-4', 'hostname': 'DEWIT-SRV01', 'lastLoggedInUser': 'DEWIT\\administrator', 'siteName': 'Advocatenkantoor De Wit', 'siteUid': 's-3', 'online': True,
     'operatingSystem': 'Windows Server 2022', 'deviceType': {'category': 'Server'}, 'rebootRequired': True}]


def _nep_rmm(methode, pad, sl=None, **kw):
    time.sleep(0.2)
    if pad == '/api/v2/account/devices':
        return {'devices': _NEP_DEV, 'pageDetails': {}}
    if pad == '/api/v2/account/sites':
        return {'sites': [{'uid': 's-1', 'name': 'Bakkerij De Korenaar B.V.', 'autotaskCompanyId': 101, 'autotaskCompanyName': 'Bakkerij De Korenaar B.V.'},
                          {'uid': 's-2', 'name': 'Installatiebedrijf Bos'}, {'uid': 's-3', 'name': 'Advocatenkantoor De Wit'}], 'pageDetails': {}}
    if pad.startswith('/api/v2/device/'):
        return next(d for d in _NEP_DEV if d['uid'] == pad.rsplit('/', 1)[1])
    return {}


_HRMM._req = _nep_rmm
_oud_v_req = _NEP_AT.req


def _v_req_haak(methode, pad, body=None):
    r = _oud_v_req(methode, pad, body)
    if methode == 'PATCH' and pad == 'Tickets' and isinstance(body, dict) and body.get('status') is not None:
        for haak in _HAT.NA_STATUS:
            haak(_NEP_AT, body['id'], body['status'])
    return r


_NEP_AT.req = _v_req_haak
API['rmm.status'] = lambda c, b: {'configured': True, 'url': 'https://pinotage-api.centrastage.net', 'admin': True}

API['open.url'] = lambda c, b: (c.L(f"(testmodus) zou openen: {b.get('url')}"), {})[1]   # testmodus: geen echte browser openen

# v2.39.2: intern bedrijf (Autotask-id 0) met een apparaat, om meekijken op eigen pc's te testen
_V['Companies'].append({'id': 0, 'companyName': 'Justdata'})
_NEP_DEV.append({'uid': 'd-5', 'hostname': 'LAPTOP-BEHEER', 'lastLoggedInUser': 'AzureAD\Beheerder', 'siteName': 'Justdata', 'siteUid': 's-4', 'online': True,
                 'operatingSystem': 'Windows 11 Enterprise', 'deviceType': {'category': 'Laptop'}, 'webRemoteUrl': 'https://pinotage.centrastage.net/csm/remote/d-5'})
_oud_nep_rmm = _HRMM._req


def _nep_rmm2(methode, pad, sl=None, **kw):
    r = _oud_nep_rmm(methode, pad, sl, **kw)
    if pad == '/api/v2/account/sites':
        r = {**r, 'sites': r['sites'] + [{'uid': 's-4', 'name': 'Justdata', 'autotaskCompanyId': 0, 'autotaskCompanyName': 'Justdata'}]}
    return r


_HRMM._req = _nep_rmm2
