#!/bin/bash
# Bouwt "Microsoft 365 beheer.app" op een Mac (Apple Silicon of Intel).
# Eenmalig nodig: Python 3.11+ (brew install python) en Node.js (brew install node).
# Gebruik:  chmod +x bouwen-mac.sh && ./bouwen-mac.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ ! -d .venv-mac ]; then
  "$PY" -m venv .venv-mac
fi
.venv-mac/bin/python -m pip install --upgrade pip -q
.venv-mac/bin/python -m pip install -r requirements.txt -q
.venv-mac/bin/python bouwen.py

echo ""
echo "Klaar. Het resultaat staat in uitvoer/release/mac/:"
ls -1 uitvoer/release/mac/
echo "Stuur de .zip en de .json met hetzelfde versienummer naar Justdata; die zet ze online."
