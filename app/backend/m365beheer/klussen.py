"""Achtergrondklussen met voortgang (bulkacties): de interface vraagt de status op met 'job.status'."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .clients import achtergrond_fn
from .context import Ctx, api

_KLUSSEN: dict[str, dict] = {}
_lock = threading.Lock()


def start(c: Ctx, titel: str, items: list[Any], fn: Callable[[Ctx, Any], dict], naam: Callable[[Any], str],
          tegelijk: int = 4) -> dict:
    """Voert fn(ctx, item) uit voor elk item (tegelijk 'tegelijk' stuks). fn geeft een dict terug (komt in resultaten)."""
    kid = uuid.uuid4().hex[:12]
    k = {'id': kid, 'titel': titel, 'totaal': len(items), 'klaar': 0, 'ok': 0, 'fout': 0, 'bezig': True,
         'resultaten': [], 'start': time.time(), 'tenant': c.tid}
    with _lock:
        _KLUSSEN[kid] = k
        for oud in [i for i, x in _KLUSSEN.items() if not x['bezig'] and time.time() - x['start'] > 3600]:
            _KLUSSEN.pop(oud, None)

    def een(item: Any) -> None:
        sub = Ctx(c.staat, c.naam, c.tid)   # eigen log per item
        try:
            r = fn(sub, item) or {}
            res = {'naam': naam(item), 'ok': True, **r, 'log': sub.log}
            k['ok'] += 1
        except Exception as e:  # noqa: BLE001
            res = {'naam': naam(item), 'ok': False, 'fout': str(e)[:400], 'log': sub.log}
            k['fout'] += 1
            sub.L(f'FOUT {naam(item)}: {e}')
        with _lock:
            k['resultaten'].append(res)
            k['klaar'] += 1

    def alles() -> None:
        try:
            with ThreadPoolExecutor(max_workers=max(1, tegelijk)) as ex:
                list(ex.map(achtergrond_fn(een), items))
        finally:
            k['bezig'] = False
    threading.Thread(target=alles, daemon=True, name=f'klus-{kid}').start()
    return status_van(kid)


def status_van(kid: str) -> dict:
    k = _KLUSSEN.get(kid)
    if not k:
        return {'id': kid, 'bezig': False, 'onbekend': True}
    return {x: v for x, v in k.items() if x != 'start'}


@api('job.status')
def job_status(c: Ctx, b: dict) -> dict:
    return status_van(str(b.get('id') or ''))
