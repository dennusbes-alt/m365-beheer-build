"""Voorraad (startscherm > Voorraad): producten (Autotask Products: merk, product, inkoop- en verkoopprijs), aantallen op
voorraad, producten op tickets (TicketCharges) en een bestellijst.

- Producten staan in Autotask (Products), zodat ze op tickets en in de facturatie terechtkomen. Toevoegen en wijzigen: sales en de
  app-beheerder. Verplicht bij Autotask: name, isActive, isSerialized, chargeBillingCodeID (een Material Cost Code).
- Aantallen en de bestellijst staan in de app (gedeeld via de verborgen SharePoint-lijst, 'voorraad'), keuze Justdata: de
  Autotask-voorraadmodule wordt niet gebruikt. Iedereen mag aantallen bijwerken en een bestelling als binnen melden.
- Product op een ticket: POST Tickets/{id}/Charges (productID, aantal, prijs; isBillableToCompany) en 1 eraf van de voorraad.
  Niet op voorraad of bestaat niet: de medewerker zet het op de bestellijst (gekoppeld aan het ticket). Sales bestelt en zet
  'besteld'; wie het binnen meldt, zet het op voorraad en (bij een bestelling voor een ticket) direct op dat ticket.
NIET getest met een echte Autotask (chargeType/costType-waarden, child-URL Charges, Material Cost Code).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from .clients import ApiFout
from .context import Ctx, api
from .h_backup import GEDEELD, _zet_auth
from .rechten import is_sales

log = logging.getLogger('m365beheer')
_lock = threading.Lock()
_CACHE: dict = {}
VELDEN = ['id', 'name', 'manufacturerName', 'manufacturerProductName', 'sKU', 'unitCost', 'unitPrice', 'description', 'isActive', 'chargeBillingCodeID']


def _stand(vers: bool = False) -> dict:
    w = GEDEELD.lees_raw('voorraad', 0 if vers else 30)
    try:
        d = json.loads(w) if w else {}
    except ValueError:
        d = {}
    return {'stock': {str(k): int(v) for k, v in (d.get('stock') or {}).items()}, 'orders': d.get('orders') or []}


def _bewaar(d: dict) -> None:
    grens = datetime.now().timestamp() - 120 * 86400   # binnengekomen bestellingen 4 maanden bewaren
    d['orders'] = [o for o in d['orders'] if o.get('status') != 'binnen' or _ts(o.get('receivedAt')) >= grens]
    GEDEELD.schrijf_raw('voorraad', json.dumps(d, separators=(',', ':')))
    GEDEELD.cache.pop('raw:voorraad', None)
    _CACHE.clear()


def _ts(s) -> float:
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except (TypeError, ValueError):
        return 0


def _eis_beheer(c: Ctx) -> None:
    if not is_sales(c.staat):
        raise ApiFout('Producten en prijzen wijzigen doen sales en de app-beheerder.')


def _wie() -> dict:
    from . import h_autotask as A
    try:
        ik = A._ik(A._at())
        return {'id': ik['id'], 'name': ik['name']}
    except ApiFout:
        return {'id': None, 'name': ''}


def _materiaalcode(at) -> int | None:
    """Material Cost Code voor nieuwe producten (verplicht in Autotask): de code van bestaande producten, anders de eerste
    actieve BillingCode van dat soort (voorkeur hardware/materiaal in de naam)."""
    if 'mat' in _CACHE:
        return _CACHE['mat']
    w = None
    try:
        p = at.query('Products', [{'op': 'exist', 'field': 'chargeBillingCodeID'}], ['chargeBillingCodeID'], 1)
        w = p[0]['chargeBillingCodeID'] if p else None
    except ApiFout:
        pass
    if w is None:
        soort = next((p['value'] for p in at.picklists('BillingCodes').get('useType', []) if re.search(r'material|materia', str(p.get('label') or ''), re.I)), None)
        if soort is not None:
            codes = at.query('BillingCodes', [{'op': 'eq', 'field': 'useType', 'value': soort}, {'op': 'eq', 'field': 'isActive', 'value': True}], ['id', 'name'], 50)
            codes.sort(key=lambda x: 0 if re.search(r'hardware|materia|product', str(x.get('name') or ''), re.I) else 1)
            w = codes[0]['id'] if codes else None
    _CACHE['mat'] = w
    return w


def producten(at, vers: bool = False) -> list[dict]:
    item = _CACHE.get('prod')
    if item and not vers and time.time() - item[0] < 60:
        return item[1]
    r = at.query('Products', [{'op': 'eq', 'field': 'isActive', 'value': True}], VELDEN, 3000, 3000)
    uit = [{'id': p['id'], 'brand': p.get('manufacturerName') or '', 'name': p.get('name') or '', 'model': p.get('manufacturerProductName') or '',
            'sku': p.get('sKU') or '', 'cost': float(p.get('unitCost') or 0), 'price': float(p.get('unitPrice') or 0),
            'description': p.get('description') or ''} for p in r]
    uit.sort(key=lambda p: (p['brand'].lower(), p['name'].lower()))
    _CACHE['prod'] = (time.time(), uit)
    return uit


def _vorm_order(o: dict) -> dict:
    return {k: o.get(k) for k in ('id', 'at', 'by', 'brand', 'name', 'qty', 'note', 'ticketId', 'ticketNumber', 'ticketTitle', 'company', 'productId',
                                  'status', 'orderedAt', 'orderedBy', 'supplier', 'receivedAt', 'receivedBy', 'charged')}


@api('vr.overzicht')
def vr_overzicht(c: Ctx, b: dict) -> dict:
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    st = _stand(bool(b.get('fresh')))
    prods = [{**p, 'stock': st['stock'].get(str(p['id']), 0)} for p in producten(at, bool(b.get('fresh')))]
    orders = sorted((_vorm_order(o) for o in st['orders']), key=lambda o: ({'open': 0, 'besteld': 1}.get(o['status'], 2), o.get('at') or ''))
    open_ = [o for o in orders if o['status'] == 'open']
    return {'products': prods, 'orders': orders, 'canEdit': is_sales(c.staat),
            'totals': {'products': len(prods), 'inStock': sum(1 for p in prods if p['stock'] > 0), 'units': sum(max(0, p['stock']) for p in prods),
                       'value': round(sum(max(0, p['stock']) * p['cost'] for p in prods), 2), 'toOrder': len(open_),
                       'ordered': sum(1 for o in orders if o['status'] == 'besteld')}}


@api('vr.product.opslaan')
def vr_product_opslaan(c: Ctx, b: dict) -> dict:
    """Product toevoegen of wijzigen (merk, product, type/artikelnummer, inkoop- en verkoopprijs), optioneel met aantal op voorraad."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_beheer(c)
    at = A._at()
    pid = nieuw_product(at, b) if not b.get('id') else int(b['id'])
    if b.get('id'):
        body = {'id': pid, 'name': str(b.get('name') or '').strip()[:1000], 'manufacturerName': str(b.get('brand') or '').strip()[:100] or None,
                'manufacturerProductName': str(b.get('model') or '').strip()[:50] or None, 'sKU': str(b.get('sku') or '').strip()[:50] or None,
                'unitCost': round(float(b.get('cost') or 0), 2), 'unitPrice': round(float(b.get('price') or 0), 2),
                'description': str(b.get('description') or '').strip()[:2000] or None}
        if not body['name']:
            raise ApiFout('Vul de productnaam in.')
        at.req('PATCH', 'Products', body)
    if b.get('stock') is not None:
        with _lock:
            st = _stand(True)
            st['stock'][str(pid)] = max(0, int(b['stock']))
            _bewaar(st)
    _CACHE.pop('prod', None)
    c.L(f"Product {'gewijzigd' if b.get('id') else 'toegevoegd'}: {(str(b.get('brand') or '') + ' ' + str(b.get('name') or '')).strip()}.")
    return {'id': pid}


def nieuw_product(at, b: dict) -> int:
    naam = str(b.get('name') or '').strip()
    if not naam:
        raise ApiFout('Vul de productnaam in.')
    code = _materiaalcode(at)
    if code is None:
        raise ApiFout('Autotask heeft geen Material Cost Code (nodig voor producten). Maak er een aan in Autotask (Admin > Billing Codes).')
    body = {'name': naam[:1000], 'manufacturerName': str(b.get('brand') or '').strip()[:100] or None,
            'manufacturerProductName': str(b.get('model') or '').strip()[:50] or None, 'sKU': str(b.get('sku') or '').strip()[:50] or None,
            'unitCost': round(float(b.get('cost') or 0), 2), 'unitPrice': round(float(b.get('price') or 0), 2), 'isActive': True, 'isSerialized': False,
            'chargeBillingCodeID': code, 'description': str(b.get('description') or '').strip()[:2000] or None}
    r = at.req('POST', 'Products', {k: v for k, v in body.items() if v is not None})
    pid = (r or {}).get('itemId')
    if not pid:
        raise ApiFout('Autotask gaf geen productnummer terug.')
    _CACHE.pop('prod', None)
    return int(pid)


@api('vr.product.weg')
def vr_product_weg(c: Ctx, b: dict) -> dict:
    """Autotask kan producten niet verwijderen: inactief zetten (verdwijnt uit de lijst)."""
    from . import h_autotask as A
    _zet_auth(c)
    _eis_beheer(c)
    A._at().req('PATCH', 'Products', {'id': int(b['id']), 'isActive': False})
    with _lock:
        st = _stand(True)
        st['stock'].pop(str(int(b['id'])), None)
        _bewaar(st)
    _CACHE.pop('prod', None)
    c.L('Product uit de voorraadlijst gehaald (inactief in Autotask).')
    return {}


@api('vr.voorraad')
def vr_voorraad(c: Ctx, b: dict) -> dict:
    """Aantal op voorraad bijwerken: {id, delta} (+1/-1) of {id, stock} (vast aantal). Iedereen."""
    _zet_auth(c)
    pid = str(int(b['id']))
    with _lock:
        st = _stand(True)
        nu = st['stock'].get(pid, 0)
        st['stock'][pid] = max(0, int(b['stock']) if b.get('stock') is not None else nu + int(b.get('delta') or 0))
        _bewaar(st)
        return {'stock': st['stock'][pid]}


# ---------------------------------------------------------------- product op een ticket
def _pl_waarde(at, ent: str, veld: str, patroon: str):
    lijst = at.picklists(ent).get(veld, [])
    return next((p['value'] for p in lijst if re.search(patroon, str(p.get('label') or ''), re.I)),
                next((p['value'] for p in lijst if p.get('default')), lijst[0]['value'] if lijst else None))


def ticket_product(at, ticket_id: int, product: dict, aantal: float, prijs: float | None = None, voorraad: bool = True) -> dict:
    """Product als kosten (TicketCharge) op het ticket; factureerbaar aan de klant. Haalt het van de voorraad af."""
    body = {'ticketID': int(ticket_id), 'productID': int(product['id']), 'name': (f"{product.get('brand') or ''} {product.get('name') or ''}".strip() or 'Product')[:100],
            'unitQuantity': float(aantal), 'unitPrice': round(float(product.get('price') if prijs is None else prijs), 2), 'unitCost': round(float(product.get('cost') or 0), 2),
            'datePurchased': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'), 'isBillableToCompany': True,
            'chargeType': _pl_waarde(at, 'TicketCharges', 'chargeType', r'operat|bill|customer|klant'),
            'costType': _pl_waarde(at, 'TicketCharges', 'costType', r'bill|customer|operat|klant')}
    body = {k: v for k, v in body.items() if v is not None}
    try:
        r = at.req('POST', f'Tickets/{int(ticket_id)}/Charges', body)
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        r = at.req('POST', 'TicketCharges', body)
    if voorraad:
        with _lock:
            st = _stand(True)
            st['stock'][str(product['id'])] = max(0, st['stock'].get(str(product['id']), 0) - int(round(aantal)))
            _bewaar(st)
    _CACHE.pop(('charges', int(ticket_id)), None)
    return {'id': (r or {}).get('itemId'), 'amount': round(float(aantal) * body['unitPrice'], 2)}


def _ticket_info(at, tid: int) -> dict:
    t = at.req('GET', f'Tickets/{int(tid)}').get('item') or {}
    if not t:
        raise ApiFout('Ticket niet gevonden.')
    naam = ''
    if t.get('companyID') is not None:
        naam = (at.req('GET', f"Companies/{t['companyID']}").get('item') or {}).get('companyName') or ''
    return {'id': t['id'], 'number': t.get('ticketNumber') or '', 'title': t.get('title') or '', 'company': naam, 'contractID': t.get('contractID')}


@api('vr.ticket')
def vr_ticket(c: Ctx, b: dict) -> dict:
    """Producten (kosten) die al op het ticket staan, plus de voorraadlijst om te kiezen."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    tid = int(b['ticketId'])
    try:
        ch = at.query('TicketCharges', [{'op': 'eq', 'field': 'ticketID', 'value': tid}],
                      ['id', 'name', 'productID', 'unitQuantity', 'unitPrice', 'datePurchased', 'isBillableToCompany', 'isBilled'], 200)
    except ApiFout as e:
        log.info('TicketCharges ophalen: %s', e)
        ch = []
    st = _stand()
    open_ = [_vorm_order(o) for o in st['orders'] if str(o.get('ticketId')) == str(tid) and o.get('status') != 'binnen']
    return {'charges': [{'id': x['id'], 'name': x.get('name') or '', 'qty': float(x.get('unitQuantity') or 0), 'price': float(x.get('unitPrice') or 0),
                         'amount': round(float(x.get('unitQuantity') or 0) * float(x.get('unitPrice') or 0), 2), 'date': str(x.get('datePurchased') or '')[:10],
                         'billable': x.get('isBillableToCompany') is not False, 'billed': bool(x.get('isBilled'))} for x in ch],
            'products': [{**p, 'stock': st['stock'].get(str(p['id']), 0)} for p in producten(at)], 'orders': open_}


@api('vr.ticket.product')
def vr_ticket_product(c: Ctx, b: dict) -> dict:
    """{ticketId, productId, qty, price?}: product van de voorraad op het ticket."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    p = next((x for x in producten(at) if x['id'] == int(b['productId'])), None)
    if not p:
        raise ApiFout('Product niet gevonden (ververs de lijst).')
    aantal = max(1, int(b.get('qty') or 1))
    op = _stand(True)['stock'].get(str(p['id']), 0)
    if op < aantal and not b.get('force'):
        raise ApiFout(f"Er {'is' if op == 1 else 'zijn'} er nog {op} op voorraad. Zet de rest op de bestellijst, of voeg het toch toe als het er wel is.")
    r = ticket_product(at, int(b['ticketId']), p, aantal, float(b['price']) if b.get('price') not in (None, '') else None)
    c.L(f"{aantal}x {p['brand']} {p['name']} op ticket {b.get('ticketNumber') or b['ticketId']} gezet (€ {r['amount']:.2f}).")
    return r


@api('vr.ticket.product.weg')
def vr_ticket_product_weg(c: Ctx, b: dict) -> dict:
    """Product weer van het ticket (alleen als het nog niet gefactureerd is) en terug op voorraad."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    tid, cid = int(b['ticketId']), int(b['id'])
    ch = at.query('TicketCharges', [{'op': 'eq', 'field': 'id', 'value': cid}], ['id', 'productID', 'unitQuantity', 'isBilled'], 1)
    if not ch:
        raise ApiFout('Niet gevonden op het ticket.')
    if ch[0].get('isBilled'):
        raise ApiFout('Dit product is al gefactureerd en kan niet meer van het ticket.')
    try:
        at.req('DELETE', f'Tickets/{tid}/Charges/{cid}')
    except ApiFout as e:
        if e.status not in (404, 405):
            raise
        at.req('DELETE', f'TicketCharges/{cid}')
    if ch[0].get('productID'):
        with _lock:
            st = _stand(True)
            k = str(ch[0]['productID'])
            st['stock'][k] = st['stock'].get(k, 0) + int(round(float(ch[0].get('unitQuantity') or 0)))
            _bewaar(st)
    c.L('Product van het ticket gehaald en terug op voorraad.')
    return {}


# ---------------------------------------------------------------- bestellijst
@api('vr.bestellen')
def vr_bestellen(c: Ctx, b: dict) -> dict:
    """Iedereen: iets op de bestellijst zetten (niet op voorraad of bestaat nog niet), optioneel voor een ticket."""
    from . import h_autotask as A
    _zet_auth(c)
    naam = str(b.get('name') or '').strip()
    if not naam and not b.get('productId'):
        raise ApiFout('Vul in wat er besteld moet worden.')
    p = None
    if b.get('productId'):
        p = next((x for x in producten(A._at()) if x['id'] == int(b['productId'])), None)
    t = None
    if b.get('ticketId'):
        try:
            t = _ticket_info(A._at(), int(b['ticketId']))
        except ApiFout:
            t = {'id': int(b['ticketId']), 'number': str(b.get('ticketNumber') or ''), 'title': '', 'company': str(b.get('company') or '')}
    o = {'id': uuid.uuid4().hex[:10], 'at': datetime.now().isoformat(timespec='minutes'), 'by': _wie()['name'],
         'brand': (p or {}).get('brand') or str(b.get('brand') or '').strip()[:100], 'name': (p or {}).get('name') or naam[:200],
         'qty': max(1, int(b.get('qty') or 1)), 'note': str(b.get('note') or '').strip()[:500], 'productId': (p or {}).get('id'),
         'ticketId': (t or {}).get('id'), 'ticketNumber': (t or {}).get('number'), 'ticketTitle': (t or {}).get('title'),
         'company': (t or {}).get('company') or str(b.get('company') or '')[:100], 'status': 'open', 'charged': bool(b.get('charged'))}
    with _lock:
        st = _stand(True)
        st['orders'].append(o)
        _bewaar(st)
    c.L(f"Op de bestellijst: {o['qty']}x {(o['brand'] + ' ' + o['name']).strip()}" + (f" (ticket {o['ticketNumber']})" if o['ticketNumber'] else '') + '.')
    return {'order': _vorm_order(o)}


@api('vr.besteld')
def vr_besteld(c: Ctx, b: dict) -> dict:
    """Sales: bestellingen op 'besteld' zetten (of terug naar open met undo)."""
    _zet_auth(c)
    _eis_beheer(c)
    ids = set(b.get('ids') or [])
    wie = _wie()['name']
    with _lock:
        st = _stand(True)
        n = 0
        for o in st['orders']:
            if o['id'] in ids and o.get('status') in ('open', 'besteld'):
                if b.get('undo'):
                    o.update(status='open', orderedAt=None, orderedBy=None)
                else:
                    o.update(status='besteld', orderedAt=datetime.now().isoformat(timespec='minutes'), orderedBy=wie, supplier=str(b.get('supplier') or '')[:100] or o.get('supplier'))
                n += 1
        _bewaar(st)
    c.L(f"{n} bestelling(en) {'terug naar te bestellen' if b.get('undo') else 'op besteld gezet'}.")
    return {'count': n}


@api('vr.binnen')
def vr_binnen(c: Ctx, b: dict) -> dict:
    """Iedereen: bestelling is binnen. Bestaat het product nog niet, dan wordt het aangemaakt (prijzen invullen).
    Op voorraad; was het besteld voor een ticket, dan direct op dat ticket (en weer van de voorraad)."""
    from . import h_autotask as A
    _zet_auth(c)
    at = A._at()
    st0 = _stand(True)
    o = next((x for x in st0['orders'] if x['id'] == b.get('id')), None)
    if not o or o.get('status') == 'binnen':
        raise ApiFout('Deze bestelling staat niet (meer) open.')
    aantal = max(1, int(b.get('qty') or o.get('qty') or 1))
    pid = int(b['productId']) if b.get('productId') else o.get('productId')
    if not pid:
        pid = nieuw_product(at, {'brand': b.get('brand', o.get('brand')), 'name': b.get('name') or o.get('name'), 'model': b.get('model'), 'sku': b.get('sku'),
                                 'cost': b.get('cost'), 'price': b.get('price')})
    p = next((x for x in producten(at, True) if x['id'] == int(pid)), None) or {'id': int(pid), 'brand': o.get('brand'), 'name': o.get('name'),
                                                                                 'cost': float(b.get('cost') or 0), 'price': float(b.get('price') or 0)}
    al_op_ticket = bool(o.get('charged'))   # product stond al op het ticket (vaste prijs-ticket): niet nog eens op voorraad of ticket
    with _lock:
        st = _stand(True)
        if not al_op_ticket:
            st['stock'][str(pid)] = st['stock'].get(str(pid), 0) + aantal
        for x in st['orders']:
            if x['id'] == o['id']:
                x.update(status='binnen', receivedAt=datetime.now().isoformat(timespec='minutes'), receivedBy=_wie()['name'], productId=int(pid), qty=aantal)
        _bewaar(st)
    op_ticket = None
    if o.get('ticketId') and b.get('toTicket', True) and not al_op_ticket:
        try:
            op_ticket = ticket_product(at, int(o['ticketId']), p, aantal)
            with _lock:
                st = _stand(True)
                for x in st['orders']:
                    if x['id'] == o['id']:
                        x['charged'] = True
                _bewaar(st)
        except ApiFout as e:
            log.info('Binnengekomen product op ticket zetten: %s', e)
            c.L(f"Let op: op voorraad gezet, maar niet op ticket {o.get('ticketNumber')} ({e}).")
    c.L(f"Binnen: {aantal}x {(str(p.get('brand') or '') + ' ' + str(p.get('name') or '')).strip()}" + (f", op ticket {o.get('ticketNumber')} gezet" if op_ticket else f", stond al op ticket {o.get('ticketNumber')}" if al_op_ticket else ', op voorraad') + '.')
    return {'productId': pid, 'ticket': bool(op_ticket) or al_op_ticket}


@api('vr.bestelling.weg')
def vr_bestelling_weg(c: Ctx, b: dict) -> dict:
    """Bestelling van de lijst halen (vergissing of niet meer nodig): sales of wie hem invoerde."""
    _zet_auth(c)
    wie = _wie()['name']
    with _lock:
        st = _stand(True)
        o = next((x for x in st['orders'] if x['id'] == b.get('id')), None)
        if not o:
            raise ApiFout('Niet gevonden.')
        if not is_sales(c.staat) and o.get('by') != wie:
            raise ApiFout('Alleen sales of wie het op de lijst zette kan het weghalen.')
        st['orders'] = [x for x in st['orders'] if x['id'] != o['id']]
        _bewaar(st)
    c.L(f"Van de bestellijst gehaald: {(str(o.get('brand') or '') + ' ' + str(o.get('name') or '')).strip()}.")
    return {}


def te_bestellen() -> int:
    """Aantal open bestellingen (voor de melding bij sales)."""
    try:
        return sum(1 for o in _stand()['orders'] if o.get('status') == 'open')
    except Exception:  # noqa: BLE001
        return 0


def vergeet() -> None:
    _CACHE.clear()
