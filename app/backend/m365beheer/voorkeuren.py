"""Favoriete en recente klanten (alleen tenant-ID's, geen accounts of tokens)."""
from __future__ import annotations

import threading

from . import lokaal
from .context import Ctx, api

_lock = threading.Lock()
BESTAND = 'voorkeuren.json'


def _ids(x) -> list[str]:
    return [str(i) for i in x if isinstance(i, str) and len(i) <= 64][:200] if isinstance(x, list) else []


def _lees() -> dict:
    d = lokaal.lees(BESTAND, {})
    return d if isinstance(d, dict) else {}


@api('prefs.get')
def get(c: Ctx, b: dict) -> dict:
    d = _lees()
    return {'fav': _ids(d.get('fav')), 'recent': _ids(d.get('recent'))}


@api('prefs.fav')
def fav(c: Ctx, b: dict) -> dict:
    with _lock:
        d = _lees()
        f = [i for i in _ids(d.get('fav')) if i != b.get('id')]
        if b.get('on'):
            f.append(str(b.get('id')))
        d['fav'] = f
        lokaal.schrijf(BESTAND, d)
    return {'fav': f}


@api('prefs.recent')
def recent(c: Ctx, b: dict) -> dict:
    with _lock:
        d = _lees()
        d['recent'] = ([str(b.get('id'))] + [i for i in _ids(d.get('recent')) if i != b.get('id')])[:8]
        lokaal.schrijf(BESTAND, d)
    return {'recent': d['recent']}
