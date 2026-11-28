"""Lokale opslag op deze computer (geen accounts, wachtwoorden of tokens).

Wordt gebruikt voor voorkeuren (favoriete klanten) en een cache van het klantenoverzicht,
zodat dat direct verschijnt en daarna op de achtergrond ververst wordt.
Persoonsgegevens van klanten (gebruikers, apparaten) worden alleen in het geheugen gecachet.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def app_map() -> Path:
    if sys.platform == 'win32':
        p = Path(os.environ.get('APPDATA') or Path.home()) / 'Justdata' / 'M365Beheer'
    elif sys.platform == 'darwin':
        p = Path.home() / 'Library' / 'Application Support' / 'Justdata M365Beheer'
    else:
        p = Path.home() / '.config' / 'justdata-m365beheer'
    return p


def lees(naam: str, standaard: Any = None) -> Any:
    try:
        return json.loads((app_map() / naam).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return standaard


def schrijf(naam: str, data: Any) -> None:
    with _lock:
        try:
            p = app_map()
            p.mkdir(parents=True, exist_ok=True)
            tmp = p / (naam + '.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            if sys.platform != 'win32':
                os.chmod(tmp, 0o600)
            os.replace(tmp, p / naam)  # atomair: nooit een half bestand
        except OSError:
            pass


def wis(naam: str) -> None:
    try:
        (app_map() / naam).unlink()
    except OSError:
        pass
