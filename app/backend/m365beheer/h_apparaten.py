"""Apparaten: Intune, Entra ID, BitLocker en Autopilot."""
from __future__ import annotations

import time
from urllib.parse import quote

from . import common as C
from .clients import GB, ApiFout, parallel
from .context import Ctx, api, VERS

LEEG_ID = '00000000-0000-0000-0000-000000000000'


def _autopilot(c: Ctx, serie: str) -> dict | None:
    if not serie:
        return None
    try:
        r = c.g.get("/deviceManagement/windowsAutopilotDeviceIdentities?$filter=contains(serialNumber,'" + quote(serie.replace("'", "''")) + "')")
        a = next((x for x in r.get('value', []) if x.get('serialNumber') == serie), None)
        if a:
            return {'id': a['id'], 'tag': a.get('groupTag') or '', 'profile': a.get('deploymentProfileAssignmentStatus') or '',
                    'state': a.get('enrollmentState') or '', 'contact': a.get('lastContactedDateTime') or ''}
    except ApiFout:
        pass
    return None


def _entra(c: Ctx, aad: str) -> dict | None:
    if not aad or aad == LEEG_ID:
        return None
    r = c.g.get(f"/devices?$filter=deviceId eq '{aad}'&$select=id,displayName,trustType,approximateLastSignInDateTime,accountEnabled")
    e = (r.get('value') or [None])[0]
    if e:
        return {'id': e['id'], 'name': e.get('displayName') or '', 'trust': e.get('trustType') or '',
                'enabled': e.get('accountEnabled') is not False, 'last': e.get('approximateLastSignInDateTime') or ''}
    return None


@api('dev.list')
def dev_list(c: Ctx, b: dict) -> dict:
    g = c.g
    try:
        return c.t.cache('apparaten', lambda: _apparaten(g), VERS, bool(b.get('fresh')))
    except ApiFout as e:
        if e.status in (401, 403):
            raise ApiFout('Intune is bij deze klant niet beschikbaar: er is geen Intune-licentie (bijv. Business Premium), '
                          'of de rol Intune Administrator is (nog) niet actief. Een nieuwe GDAP-toewijzing kan tot een uur duren voordat Intune hem herkent.')
        raise


def _apparaten(g) -> dict:
    alle = g.all('/deviceManagement/managedDevices?$select=id,deviceName,managedDeviceOwnerType,operatingSystem,osVersion,complianceState,'
                   'userPrincipalName,userDisplayName,lastSyncDateTime,serialNumber,model,manufacturer,azureADDeviceId&$top=500')
    l = [{'id': d['id'], 'name': d.get('deviceName') or '', 'owner': d.get('managedDeviceOwnerType') or '', 'os': d.get('operatingSystem') or '',
          'osv': d.get('osVersion') or '', 'comp': d.get('complianceState') or '', 'upn': d.get('userPrincipalName') or '',
          'user': d.get('userDisplayName') or '', 'sync': d.get('lastSyncDateTime') or '', 'serial': d.get('serialNumber') or '',
          'model': d.get('model') or '', 'man': d.get('manufacturer') or '', 'aad': d.get('azureADDeviceId') or ''} for d in alle]
    return {'devices': sorted(l, key=lambda x: x['name'].lower())}


@api('dev.get')
def dev_get(c: Ctx, b: dict) -> dict:
    # Intune, Entra en Autopilot tegelijk ophalen; serienummer en Entra-ID komen al mee uit de lijst
    if b.get('serial') is not None and b.get('aad') is not None:
        r = parallel({'d': lambda: c.g.get(f"/deviceManagement/managedDevices/{b['id']}"),
                      'e': lambda: _entra(c, str(b['aad'])), 'a': lambda: _autopilot(c, str(b['serial']))})
        if isinstance(r['d'], Exception):
            raise r['d']
        d = r['d']
        extra = {'entra': None if isinstance(r['e'], Exception) else r['e'], 'autopilot': None if isinstance(r['a'], Exception) else r['a']}
    else:
        d = c.g.get(f"/deviceManagement/managedDevices/{b['id']}")
        extra = {'entra': _entra(c, str(d.get('azureADDeviceId') or '')), 'autopilot': _autopilot(c, str(d.get('serialNumber') or ''))}
    s = lambda k: str(d.get(k) or '')
    return {'id': s('id'), 'name': s('deviceName'), 'model': s('model'), 'man': s('manufacturer'), 'serial': s('serialNumber'),
            'os': s('operatingSystem'), 'osv': s('osVersion'), 'owner': s('managedDeviceOwnerType'), 'comp': s('complianceState'),
            'mgmt': s('managementAgent'), 'upn': s('userPrincipalName'), 'user': s('userDisplayName'), 'last': s('lastSyncDateTime'),
            'enrolled': s('enrolledDateTime'), 'enc': d.get('isEncrypted'), 'free': float(d.get('freeStorageSpaceInBytes') or 0),
            'total': float(d.get('totalStorageSpaceInBytes') or 0), 'mac': s('wiFiMacAddress'), 'imei': s('imei'), 'phone': s('phoneNumber'),
            'aad': s('azureADDeviceId'), 'enrollType': s('deviceEnrollmentType'), 'reg': s('deviceRegistrationState'),
            'category': s('deviceCategoryDisplayName'), 'patch': s('androidSecurityPatchLevel'), 'jail': s('jailBroken'),
            **extra}


@api('dev.bitlocker')
def dev_bitlocker(c: Ctx, b: dict) -> dict:
    aad = b.get('aad')
    if not aad or aad == LEEG_ID:
        return {'keys': []}
    r = c.g.get(f"/informationProtection/bitlocker/recoveryKeys?$filter=deviceId eq '{aad}'")
    l = [{'id': k['id'], 'created': k.get('createdDateTime') or '', 'vol': k.get('volumeType') or ''} for k in r.get('value', [])]
    return {'keys': sorted(l, key=lambda x: x['created'], reverse=True)}


@api('dev.bitlockerkey')
def dev_bitlockerkey(c: Ctx, b: dict) -> dict:
    r = c.g.get(f"/informationProtection/bitlocker/recoveryKeys/{b['id']}?$select=key")
    c.L('BitLocker-herstelsleutel opgevraagd (dit wordt vastgelegd in de auditlog van Entra).')
    return {'key': r.get('key') or ''}


@api('dev.groups')
def dev_groups(c: Ctx, b: dict) -> dict:
    r = c.g.all(f"/devices/{b['entraId']}/memberOf/microsoft.graph.group?$select=id,displayName,groupTypes,securityEnabled&$top=999")
    l = sorted([{'id': g['id'], 'name': g.get('displayName') or '', 'dynamic': 'DynamicMembership' in (g.get('groupTypes') or []),
                 'sec': bool(g.get('securityEnabled'))} for g in r], key=lambda x: x['name'].lower())
    return {'groups': l, 'all': [g for g in C.groepen(c) if g['type'] == 'Beveiliging' and g['edit']]}


@api('dev.group')
def dev_group(c: Ctx, b: dict) -> dict:
    ids = list(b.get('groupIds') or [b.get('groupId')])
    namen = {g['id']: g['name'] for g in C.groepen(c)}
    erbij = b.get('action') == 'add'

    def een(gid: str):
        if erbij:
            return c.g.post(f"/groups/{gid}/members/$ref", {'@odata.id': f"{GB}/directoryObjects/{b['entraId']}"})
        return c.g.delete(f"/groups/{gid}/members/{b['entraId']}/$ref")
    r = parallel({gid: (lambda g=gid: een(g)) for gid in ids if gid})
    for gid, uit in r.items():
        naam = namen.get(gid, gid)
        if isinstance(uit, Exception):
            tekst = str(uit)
            if 'Insufficient privileges' in tekst or getattr(uit, 'status', 0) == 403:
                tekst = 'onvoldoende rechten (is het een groep die rollen kan krijgen, of een on-premises groep?)'
            c.L(f'FOUT {naam}: {tekst}')
        else:
            c.L(f"Apparaat {'toegevoegd aan' if erbij else 'verwijderd uit'} {naam}.")
    if all(isinstance(x, Exception) for x in r.values()):
        raise ApiFout('Het is niet gelukt; zie de melding(en).')
    return {}


@api('dev.sync')
def dev_sync(c: Ctx, b: dict) -> dict:
    ok = 0
    for i in b.get('ids') or []:
        try:
            c.g.post(f'/deviceManagement/managedDevices/{i}/syncDevice')
            ok += 1
        except ApiFout as e:
            c.L(f'FOUT bij synchroniseren ({i}): {e}')
    c.L(f'Synchronisatie gestart voor {ok} apparaat/apparaten.')
    return {}


@api('dev.delete')
def dev_delete(c: Ctx, b: dict) -> dict:
    d = c.g.get(f"/deviceManagement/managedDevices/{b['id']}")
    naam, serie, aad = d.get('deviceName') or '', d.get('serialNumber') or '', d.get('azureADDeviceId') or ''
    c.g.delete(f"/deviceManagement/managedDevices/{b['id']}")
    c.L(f'{naam} is verwijderd uit Intune.')
    if b.get('autopilot'):
        ap = _autopilot(c, serie)
        if ap:
            try:
                c.g.delete(f"/deviceManagement/windowsAutopilotDeviceIdentities/{ap['id']}")
                c.L('Autopilot-registratie verwijderd.')
            except ApiFout as e:
                c.L(f'FOUT Autopilot: {e}')
        else:
            c.L('Geen Autopilot-registratie gevonden.')
    if b.get('entra'):
        try:
            e = _entra(c, aad)
            if e:
                c.g.delete(f"/devices/{e['id']}")
                c.L('Apparaat verwijderd uit Entra ID.')
            else:
                c.L('Geen Entra-apparaat gevonden.')
        except ApiFout as e:
            c.L(f'FOUT Entra ID: {e}')
    return {}


@api('dev.deletemany')
def dev_deletemany(c: Ctx, b: dict) -> dict:
    """Meerdere apparaten tegelijk uit Intune verwijderen (optioneel ook uit Entra ID en Autopilot), vier tegelijk."""
    from concurrent.futures import ThreadPoolExecutor
    ids = [str(i) for i in b.get('ids') or [] if i]
    if not ids:
        raise ApiFout('Kies eerst de apparaten.')

    def een(i):
        try:
            dev_delete(c, {'id': i, 'entra': b.get('entra'), 'autopilot': b.get('autopilot')})
            return True
        except ApiFout as e:
            c.L(f'FOUT bij verwijderen ({i}): {e}')
            return False
    with ThreadPoolExecutor(max_workers=4) as ex:
        ok = sum(ex.map(een, ids))
    c.t.weg('apparaten', 'autopilot')
    c.L(f'{ok} van {len(ids)} apparaten verwijderd uit Intune.')
    return {'ok': ok}


@api('dev.restartmany')
def dev_restartmany(c: Ctx, b: dict) -> dict:
    ok = 0
    for i in b.get('ids') or []:
        try:
            c.g.post(f'/deviceManagement/managedDevices/{i}/rebootNow')
            ok += 1
        except ApiFout as e:
            c.L(f'FOUT bij herstarten ({i}): {e}')
    c.L(f'Herstart gestuurd naar {ok} apparaat/apparaten.')
    return {}


@api('dev.apreset')
def dev_apreset(c: Ctx, b: dict) -> dict:
    """Autopilot Reset (zoals in Intune): Windows opnieuw inrichten met behoud van de inschrijving in Intune en Entra.
    Persoonlijke bestanden, apps en instellingen gaan weg; het apparaat blijft van de organisatie en richt zich daarna
    zelf weer in. Vereist Windows 10/11 (1709+), Entra-join en de Windows-herstelomgeving op het apparaat."""
    d = c.g.get(f"/deviceManagement/managedDevices/{b['id']}")
    if 'windows' not in str(d.get('operatingSystem') or '').lower():
        raise ApiFout('Autopilot Reset kan alleen bij Windows-apparaten.')
    if str(d.get('joinType') or '').lower() == 'hybridazureadjoined':
        raise ApiFout('Autopilot Reset werkt niet bij hybride (on-premises AD) apparaten. Gebruik daarvoor Wissen in Intune.')
    c.g.post(f"/deviceManagement/managedDevices/{b['id']}/wipe", {'keepEnrollmentData': True, 'keepUserData': False})
    c.L(f"Autopilot Reset gestart voor {d.get('deviceName')}. Bij de volgende check-in wordt Windows opnieuw ingericht; "
        'dat duurt meestal 30 tot 60 minuten.')
    try:
        c.g.post(f"/deviceManagement/managedDevices/{b['id']}/syncDevice")   # zo snel mogelijk laten oppakken
    except ApiFout:
        pass
    return {}


def _ap_item(a: dict) -> dict:
    intune = a.get('managedDeviceId') or ''
    return {'id': a['id'], 'serial': a.get('serialNumber') or '', 'tag': a.get('groupTag') or '', 'man': a.get('manufacturer') or '',
            'model': a.get('model') or '', 'profile': a.get('deploymentProfileAssignmentStatus') or '', 'state': a.get('enrollmentState') or '',
            'contact': a.get('lastContactedDateTime') or '', 'upn': a.get('userPrincipalName') or '', 'name': a.get('displayName') or '',
            'intune': '' if intune == LEEG_ID else intune, 'order': a.get('purchaseOrderIdentifier') or ''}


@api('ap.list')
def ap_list(c: Ctx, b: dict) -> dict:
    def ophalen() -> dict:
        r = parallel({'items': lambda: c.g.all('/deviceManagement/windowsAutopilotDeviceIdentities?$top=500'),
                      'set': lambda: c.g.get('/deviceManagement/windowsAutopilotSettings')})
        if isinstance(r['items'], Exception):
            e = r['items']
            if e.status in (401, 403):
                raise ApiFout('Autopilot is bij deze klant niet beschikbaar: er is geen Intune-licentie, of de rol Intune Administrator '
                              'is (nog) niet actief in de GDAP-relatie.', e.status)
            raise e
        st = r['set'] if isinstance(r['set'], dict) else {}
        return {'items': sorted((_ap_item(a) for a in r['items']), key=lambda x: x['serial']),
                'lastSync': st.get('lastSyncDateTime') or '', 'syncStatus': st.get('syncStatus') or '',
                'lastManualSync': st.get('lastManualSyncTriggerDateTime') or ''}
    return c.t.cache('autopilot', ophalen, VERS, bool(b.get('fresh')))


@api('ap.delete')
def ap_delete(c: Ctx, b: dict) -> dict:
    """Autopilot-registraties verwijderen. Staat een apparaat nog in Intune, dan weigert Microsoft dat; met 'intune'
    wordt het Intune-apparaat eerst verwijderd (zoals de portal vraagt)."""
    ook_intune = bool(b.get('intune'))

    def een(i: str) -> str:
        a = c.g.get(f'/deviceManagement/windowsAutopilotDeviceIdentities/{i}')
        naam = a.get('serialNumber') or i
        md = a.get('managedDeviceId') or ''
        beheerd = bool(md) and md != LEEG_ID
        if beheerd and ook_intune:
            try:
                c.g.delete(f'/deviceManagement/managedDevices/{md}')
                c.L(f'{naam}: verwijderd uit Intune.')
            except ApiFout as e:
                if e.status != 404:
                    raise ApiFout(f'{naam}: verwijderen uit Intune lukte niet ({e})')
        for poging in range(4):   # na het verwijderen uit Intune duurt het even voordat Autopilot dat weet
            try:
                c.g.delete(f'/deviceManagement/windowsAutopilotDeviceIdentities/{i}')
                return naam
            except ApiFout as e:
                if e.status == 404:
                    return naam
                if beheerd and not ook_intune:
                    raise ApiFout(f'{naam}: staat nog in Intune. Vink "ook uit Intune verwijderen" aan, of verwijder het apparaat eerst bij Apparaten.')
                if poging == 3:
                    raise ApiFout(f'{naam}: {e}')
                time.sleep(5)
        return naam

    ids = [str(i) for i in b.get('ids') or []]
    r = parallel({i: (lambda i=i: een(i)) for i in ids})
    ok = [v for v in r.values() if not isinstance(v, Exception)]
    for v in r.values():
        if isinstance(v, Exception):
            c.L(f'FOUT {v}')
    if ok:
        c.L(f'{len(ok)} Autopilot-registratie(s) verwijderd. Het kan enkele minuten duren voor ze uit de lijst verdwijnen.')
    if ids and not ok:
        raise ApiFout('Er is niets verwijderd; zie de melding(en).')
    return {'deleted': len(ok)}


@api('ap.tag')
def ap_tag(c: Ctx, b: dict) -> dict:
    ok = 0
    for i in b.get('ids') or []:
        try:
            c.g.post(f'/deviceManagement/windowsAutopilotDeviceIdentities/{i}/updateDeviceProperties', {'groupTag': str(b.get('tag') or '')})
            ok += 1
        except ApiFout as e:
            c.L(f'FOUT bij group tag ({i}): {e}')
    c.L(f'Group tag aangepast voor {ok} apparaat/apparaten.')
    return {}


@api('ap.sync')
def ap_sync(c: Ctx, b: dict) -> dict:
    """Apparaten die de leverancier heeft geregistreerd (bijv. via de distributeur) ophalen in Intune."""
    try:
        c.g.post('/deviceManagement/windowsAutopilotSettings/sync')
    except ApiFout as e:
        if e.status in (409, 429) or 'too many' in str(e).lower() or 'already' in str(e).lower():
            raise ApiFout('Er is net al gesynchroniseerd. Microsoft staat dat maximaal eens per 10 minuten toe; probeer het straks opnieuw.')
        raise
    c.L('Autopilot-synchronisatie gestart. Nieuwe apparaten verschijnen meestal binnen enkele minuten in de lijst.')
    return {}


@api('ap.import')
def ap_import(c: Ctx, b: dict) -> dict:
    ids: dict[str, str] = {}
    for r in b.get('rows') or []:
        body = {'@odata.type': '#microsoft.graph.importedWindowsAutopilotDeviceIdentity', 'groupTag': str(r.get('tag') or ''),
                'serialNumber': str(r.get('serial') or ''), 'hardwareIdentifier': str(r.get('hash') or ''),
                'state': {'@odata.type': 'microsoft.graph.importedWindowsAutopilotDeviceIdentityState', 'deviceImportStatus': 'pending',
                          'deviceRegistrationId': '', 'deviceErrorCode': 0, 'deviceErrorName': ''}}
        try:
            x = c.g.post('/deviceManagement/importedWindowsAutopilotDeviceIdentities', body)
            ids[x['id']] = str(r.get('serial') or '')
        except ApiFout as e:
            c.L(f"FOUT bij {r.get('serial')}: {e}")
    klaar = 0
    for _ in range(24):
        if not ids:
            break
        time.sleep(10)
        for i in list(ids):
            try:
                s = c.g.get(f'/deviceManagement/importedWindowsAutopilotDeviceIdentities/{i}').get('state') or {}
                st = str(s.get('deviceImportStatus') or '')
                if st == 'complete':
                    c.L(f'Geregistreerd: {ids.pop(i)}')
                    klaar += 1
                elif st == 'error':
                    c.L(f"FOUT bij {ids.pop(i)}: {s.get('deviceErrorName')}")
            except ApiFout:
                pass
    for serie in ids.values():
        c.L(f'FOUT: {serie} is na 4 minuten nog niet klaar. Kijk later in de lijst.')
    try:
        c.g.post('/deviceManagement/windowsAutopilotSettings/sync')
    except ApiFout:
        pass
    return {'done': klaar}


@api('dev.bitlocker.zoek')
def dev_bitlocker_zoek(c: Ctx, b: dict) -> dict:
    """Zoeken op (het begin van) het herstelsleutel-ID zoals het op het BitLocker-herstelscherm staat."""
    q = ''.join(ch for ch in str(b.get('q') or '').lower() if ch.isalnum())
    if len(q) < 4:
        raise ApiFout('Typ minimaal de eerste 4 tekens van het sleutel-ID (zoals op het herstelscherm).')
    sleutels = c.t.cache('bitlocker', lambda: c.g.all('/informationProtection/bitlocker/recoveryKeys?$select=id,createdDateTime,deviceId,volumeType'), 300,
                         bool(b.get('fresh')))
    hits = [k for k in sleutels if k['id'].replace('-', '').lower().startswith(q)][:20]
    devs = parallel({h['deviceId']: (lambda d=h['deviceId']: _entra(c, d)) for h in hits if h.get('deviceId')})
    intune = parallel({h['deviceId']: (lambda d=h['deviceId']: (c.g.get(
        f"/deviceManagement/managedDevices?$filter=azureADDeviceId eq '{d}'&$select=id,deviceName,userDisplayName").get('value') or [None])[0])
        for h in hits if h.get('deviceId')})
    uit = []
    for h in hits:
        e = devs.get(h.get('deviceId'))
        m = intune.get(h.get('deviceId'))
        uit.append({'id': h['id'], 'created': h.get('createdDateTime', ''), 'vol': h.get('volumeType', ''), 'aad': h.get('deviceId', ''),
                    'device': (e or {}).get('name', '') if not isinstance(e, Exception) else '',
                    'intuneId': (m or {}).get('id', '') if m and not isinstance(m, Exception) else '',
                    'user': (m or {}).get('userDisplayName', '') if m and not isinstance(m, Exception) else ''})
    return {'keys': uit, 'searched': len(sleutels)}
