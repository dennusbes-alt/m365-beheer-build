"""GDAP-toegang: welke rollen heb jij werkelijk bij een klant, en ontbrekende toegangstoewijzingen regelen.

Een GDAP-relatie bevat rollen, maar die gelden pas als ze via een "toegangstoewijzing" aan een beveiligingsgroep
in de Justdata-tenant zijn toegewezen. Zonder toewijzing aan een groep waar jij in zit heb je bij die klant niets.

Afspraak (Justdata): ontbrekende toewijzingen gaan naar de groep AdminAgents, met alle rollen uit de relatie
behalve Global Administrator. Daarmee werken alle functies van de app, inclusief het automatisch koppelen
(Application Administrator / Cloud Application Administrator).
"""
from __future__ import annotations

import logging
import threading
import time

from .clients import ApiFout, Graph, parallel

log = logging.getLogger('m365beheer')

GROEP_NAAM = 'AdminAgents'
GLOBAL_ADMIN = '62e90394-69f5-4237-9190-012177145e10'
KOPPEL_ROLLEN = {'9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3', '158c047a-c907-4556-b7ef-446551a6b5f7'}   # (Cloud) Application Administrator
REL = '/tenantRelationships/delegatedAdminRelationships'


class GdapInfo:
    """Gegevens uit de Justdata-tenant: jouw groepen en de AdminAgents-groep (eenmalig per sessie opgehaald)."""

    def __init__(self, partner: Graph):
        self.p = partner
        self._lock = threading.Lock()
        self._groepen: set[str] | None = None
        self._admin_agents: str | None = None

    def mijn_groepen(self) -> set[str]:
        with self._lock:
            if self._groepen is None:
                self._groepen = {g['id'] for g in self.p.all('/me/transitiveMemberOf/microsoft.graph.group?$select=id&$top=999')}
            return self._groepen

    def admin_agents(self) -> str:
        with self._lock:
            if self._admin_agents is None:
                v = self.p.get(f"/groups?$filter=displayName eq '{GROEP_NAAM}'&$select=id").get('value') or []
                if not v:
                    raise ApiFout(f'De groep {GROEP_NAAM} bestaat niet in de Justdata-tenant.')
                self._admin_agents = v[0]['id']
            return self._admin_agents


def toewijzingen(p: Graph, rel_id: str) -> list[dict]:
    return [a for a in p.all(f'{REL}/{rel_id}/accessAssignments') if a.get('status') not in ('deleted', 'deleting', 'error')]


def effectieve_rollen(p: Graph, relaties: list[dict], mijn: set[str]) -> dict[str, set[str]]:
    """Per klant: de rol-ID's die jij via je groepen werkelijk hebt (alle relaties, parallel opgehaald)."""
    r = parallel({rel['id']: (lambda rid=rel['id']: toewijzingen(p, rid)) for rel in relaties})
    uit: dict[str, set[str]] = {}
    for rel in relaties:
        tid = (rel.get('customer') or {}).get('tenantId')
        rollen = uit.setdefault(tid, set())
        aa = r.get(rel['id'])
        if isinstance(aa, Exception):
            continue
        for a in aa:
            if a.get('status') == 'active' and (a.get('accessContainer') or {}).get('accessContainerId') in mijn:
                rollen |= {x['roleDefinitionId'] for x in (a.get('accessDetails') or {}).get('unifiedRoles') or []}
    return uit


def _beste_relatie(relaties: list[dict]) -> dict:
    """Voorkeur: een eigen relatie (niet die van Lighthouse) met de meeste rollen."""
    def score(r: dict) -> tuple:
        rollen = (r.get('accessDetails') or {}).get('unifiedRoles') or []
        return (not str(r.get('displayName', '')).startswith('NC-LHSetup'), bool(KOPPEL_ROLLEN & {x['roleDefinitionId'] for x in rollen}), len(rollen))
    return max(relaties, key=score)


STATUS_NL = {'created': 'aangemaakt, maar nog niet naar de klant verstuurd', 'approvalPending': 'wacht op goedkeuring door de klant',
             'activating': 'is goedgekeurd en wordt door Microsoft geactiveerd', 'active': 'actief', 'expired': 'verlopen',
             'terminated': 'beëindigd', 'terminationRequested': 'wordt beëindigd'}


def goedkeuringslink(rel_id: str) -> str:
    """Link die de klant (Global Administrator) opent om een GDAP-relatie goed te keuren."""
    return f'https://admin.microsoft.com/AdminPortal/Home#/partners/invitation/granularAdminRelationships/{rel_id}'


def relaties_van(p: Graph, tid: str) -> list[dict]:
    """Alle relaties met deze klant die nog lopen of eraan komen (dus niet verlopen of beëindigd)."""
    return [r for r in p.all(REL) if (r.get('customer') or {}).get('tenantId') == tid
            and r.get('status') in ('created', 'approvalPending', 'activating', 'active')]


class GdapMelding(ApiFout):
    """Duidelijke uitleg over de GDAP-situatie bij een klant, met eventueel een goedkeuringslink."""
    def __init__(self, tekst: str, link: str = '', status: str = ''):
        super().__init__(tekst)
        self.link, self.gdap_status = link, status


def toegang_regelen(info: GdapInfo, tid: str, voortgang=None, max_sec: int = 300) -> bool:
    """Zorgt dat AdminAgents bij deze klant een actieve toewijzing heeft met alle rollen uit de relatie behalve
    Global Administrator. Geeft True als er iets is aangemaakt of aangevuld. Wacht tot de toewijzing actief is."""
    meld = voortgang or (lambda t: None)
    p = info.p
    meld('GDAP-relaties van de klant controleren...')
    alle = relaties_van(p, tid)
    relaties = [r for r in alle if r.get('status') == 'active']
    onderweg = [r for r in alle if r.get('status') != 'active' and KOPPEL_ROLLEN & {x['roleDefinitionId'] for x in (r.get('accessDetails') or {}).get('unifiedRoles') or []}]
    groep = info.admin_agents()
    mijn = info.mijn_groepen()
    # Heb je via een bestaande toewijzing al de rollen om te koppelen? Dan hoeft er niets te gebeuren.
    if relaties and KOPPEL_ROLLEN & effectieve_rollen(p, relaties, mijn).get(tid, set()):
        return False
    bruikbaar = [r for r in relaties if KOPPEL_ROLLEN & {x['roleDefinitionId'] for x in (r.get('accessDetails') or {}).get('unifiedRoles') or []}]
    if not bruikbaar:
        if onderweg:   # er komt een nieuwe relatie aan: precies uitleggen waar die staat
            r = onderweg[0]
            st = r.get('status')
            if st == 'approvalPending':
                raise GdapMelding(f"De nieuwe GDAP-relatie '{r.get('displayName')}' {STATUS_NL[st]}. Stuur de klant de goedkeuringslink; "
                                  'zodra de klant heeft goedgekeurd regelt de app de rest automatisch.', goedkeuringslink(r['id']), st)
            if st == 'activating':
                raise GdapMelding(f"De nieuwe GDAP-relatie '{r.get('displayName')}' {STATUS_NL[st]}. Dat duurt meestal enkele minuten; "
                                  'probeer het daarna opnieuw.', '', st)
            raise GdapMelding(f"De nieuwe GDAP-relatie '{r.get('displayName')}' is {STATUS_NL.get(st, st)}. Verstuur hem in het partnerportaal "
                              'naar de klant (Goedkeuring aanvragen).', 'https://partner.microsoft.com/dashboard/v2/customers/list', st)
        if not relaties:
            raise GdapMelding('Er is geen actieve GDAP-relatie met deze klant. Maak er een aan in het partnerportaal en laat de klant hem goedkeuren.',
                              'https://partner.microsoft.com/dashboard/v2/customers/list', 'none')
        raise GdapMelding('De GDAP-relatie met deze klant bevat geen Application Administrator of Cloud Application Administrator. '
                          'Daardoor kan de app niet gekoppeld worden. Maak in het partnerportaal een nieuwe relatie met die rol en laat de klant hem goedkeuren.',
                          'https://partner.microsoft.com/dashboard/v2/customers/list', 'roles')
    rel = _beste_relatie(bruikbaar)
    gewenst = [x['roleDefinitionId'] for x in (rel.get('accessDetails') or {}).get('unifiedRoles') or [] if x['roleDefinitionId'] != GLOBAL_ADMIN]
    bestaand = next((a for a in toewijzingen(p, rel['id']) if (a.get('accessContainer') or {}).get('accessContainerId') == groep), None)
    body = {'accessDetails': {'unifiedRoles': [{'roleDefinitionId': x} for x in gewenst]}}
    if bestaand:
        heeft = {x['roleDefinitionId'] for x in (bestaand.get('accessDetails') or {}).get('unifiedRoles') or []}
        if set(gewenst) <= heeft and bestaand.get('status') == 'active':
            if groep not in mijn:
                raise GdapMelding(f'Je account zit niet in de groep {GROEP_NAAM}. Vraag een beheerder om je toe te voegen.')
            return False
        if set(gewenst) <= heeft and bestaand.get('status') in ('pending', 'created'):
            meld('Er loopt al een GDAP-toewijzing; wachten tot Microsoft die heeft geactiveerd...')   # niet opnieuw aanmaken
        else:
            meld(f"GDAP-toewijzing aanvullen op relatie '{rel.get('displayName')}'...")
            p.req('PATCH', f"{REL}/{rel['id']}/accessAssignments/{bestaand['id']}", body, headers={'If-Match': bestaand.get('@odata.etag', '*')})
        aid = bestaand['id']
    else:
        meld(f"GDAP-toewijzing aanmaken op relatie '{rel.get('displayName')}' (AdminAgents, {len(gewenst)} rollen)...")
        nieuw = p.post(f"{REL}/{rel['id']}/accessAssignments",
                       {**body, 'accessContainer': {'accessContainerId': groep, 'accessContainerType': 'securityGroup'}})
        aid = nieuw['id']
    log.info('GDAP-toewijzing aangemaakt/aangevuld voor %s (relatie %s, %d rollen)', tid, rel.get('displayName'), len(gewenst))
    # Wachten tot Microsoft de toewijzing heeft verwerkt (in de praktijk 1 tot 3 minuten)
    begin = time.time()
    while time.time() - begin < max_sec:
        a = p.get(f"{REL}/{rel['id']}/accessAssignments/{aid}")
        if a.get('status') == 'active':
            return True
        if a.get('status') == 'error':
            raise GdapMelding('Microsoft kon de GDAP-toewijzing niet verwerken. Probeer het later opnieuw.')
        meld(f'Wachten tot Microsoft de GDAP-toewijzing activeert ({int(time.time() - begin)} s, meestal 1 tot 3 minuten)...')
        time.sleep(5)
    raise GdapMelding('De GDAP-toewijzing is aangemaakt, maar Microsoft heeft hem na 5 minuten nog niet geactiveerd. '
                      'Probeer het later opnieuw; de app gaat dan verder waar hij was.', '', 'pending')
