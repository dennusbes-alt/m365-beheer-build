"""App-beheer: wie mag de gedeelde koppelingen (API-sleutels van Datto, Unitrends en Autotask) en de Autotask-instellingen wijzigen.

Alleen de app-beheerder. Het e-mailadres staat hier niet leesbaar (de code gaat ook naar de openbare bouwrepository),
alleen de SHA-256 van het adres in kleine letters. Een beheerder toevoegen: hashlib.sha256(b'naam@justdata.nl').hexdigest().
"""
from __future__ import annotations

import hashlib

from .clients import ApiFout
from .context import Ctx, api

try:
    from .appid import PARTNER_TENANT
except ImportError:   # pragma: no cover
    PARTNER_TENANT = ''

# Koppelingen die alleen voor Justdata zijn (Datto, Unitrends/UniView, Autotask, EasyDMARC en de afvinklijst):
# alleen bruikbaar als de ingelogde Microsoft-account thuishoort in de Justdata-tenant.
JUSTDATA_ACTIES = ('bk.', 'at.', 'dm.', 'mg.', 'sd.', 'ig.', 'adv.', 'fa.', 'ts.', 'sa.', 'pr.', 'rmm.', 'vr.', 'sc.')
JUSTDATA_MELDING = ('Back-up, e-mailbeveiliging en Autotask zijn alleen beschikbaar als je inlogt met een Justdata-account.')


def is_justdata(staat) -> bool:
    """Ingelogd met een account uit de Justdata-tenant. De tenant komt uit het door Microsoft ondertekende
    id-token (claim tid, gecontroleerd door MSAL); gasten van andere organisaties hebben een andere tid."""
    try:
        a = staat.auth
        return bool(PARTNER_TENANT) and bool(a.ingelogd) and str(a.home_tenant or '').lower() == PARTNER_TENANT.lower()
    except Exception:  # noqa: BLE001
        return False


def eis_justdata(staat) -> None:
    if not is_justdata(staat):
        raise ApiFout(JUSTDATA_MELDING, 403)

BEHEERDERS = {
    '62b36bcb8a45b1bbb8bcadef2283a06babcbfd2d59a13b83648aa503bbdef002',
}


def is_beheerder(staat) -> bool:
    if not is_justdata(staat):
        return False
    try:
        mail = str((staat.auth.account or {}).get('username') or '').strip().lower()
    except Exception:  # noqa: BLE001
        return False
    return bool(mail) and hashlib.sha256(mail.encode('utf-8')).hexdigest() in BEHEERDERS


# Directie: alleen deze logins zien het tabblad Management (alle mg.-acties). Ook hier alleen SHA-256 van het adres.
DIRECTIE = BEHEERDERS | {
    'c36616a4d9ecec6997ff24c28829bfa31fc5518ceec0960e8904f75ac4a2fdba',
    'ae1f674dd99920105154e4c37a53c88cc35f639ab53d7f0c263396afab0e49a7',
    'b9ffabb8f0405dc58fb97ac8528e221baa343b85c169fcd9572ac620609c7be6',
}
DIRECTIE_MELDING = 'Management is alleen beschikbaar voor de directie.'


def is_directie(staat) -> bool:
    if not is_justdata(staat):
        return False
    try:
        mail = str((staat.auth.account or {}).get('username') or '').strip().lower()
    except Exception:  # noqa: BLE001
        return False
    return bool(mail) and hashlib.sha256(mail.encode('utf-8')).hexdigest() in DIRECTIE


def _mail_hash(staat) -> str:
    try:
        mail = str((staat.auth.account or {}).get('username') or '').strip().lower()
    except Exception:  # noqa: BLE001
        return ''
    return hashlib.sha256(mail.encode('utf-8')).hexdigest() if mail else ''


# Facturatie (uren buiten full-service-contracten goedkeuren, factuurspecificatie, verwerkt in Exact): app-beheerder + één directielid.
FACTURATIE = BEHEERDERS | {'c36616a4d9ecec6997ff24c28829bfa31fc5518ceec0960e8904f75ac4a2fdba'}
FACTURATIE_MELDING = 'Facturatie is alleen beschikbaar voor de mensen die de facturen goedkeuren.'


def is_facturatie(staat) -> bool:
    return is_justdata(staat) and _mail_hash(staat) in FACTURATIE


# Sales: kansen invoeren en definitief maken (één directielid); inzien ook voor de app-beheerder, die er een project van maakt.
SALES_INVOEREN = {'c36616a4d9ecec6997ff24c28829bfa31fc5518ceec0960e8904f75ac4a2fdba'}
SALES_INZIEN = SALES_INVOEREN | BEHEERDERS
SALES_MELDING = 'Sales is alleen beschikbaar voor wie kansen invoert of er projecten van maakt.'


def is_sales(staat) -> bool:
    return is_justdata(staat) and _mail_hash(staat) in SALES_INZIEN


def mag_sales_invoeren(staat) -> bool:
    return is_justdata(staat) and _mail_hash(staat) in SALES_INVOEREN


def eis_beheerder(c: Ctx) -> None:
    if not is_beheerder(c.staat):
        raise ApiFout('Alleen de app-beheerder mag koppelingen en instellingen wijzigen.')


@api('app.rol')
def app_rol(c: Ctx, b: dict) -> dict:
    return {'admin': is_beheerder(c.staat), 'justdata': is_justdata(c.staat), 'directie': is_directie(c.staat), 'billing': is_facturatie(c.staat),
            'sales': is_sales(c.staat), 'salesEdit': mag_sales_invoeren(c.staat)}
