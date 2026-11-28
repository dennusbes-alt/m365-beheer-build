#!/bin/bash
# Dubbelklik om Microsoft 365 beheer te installeren of bij te werken.
# Opent macOS een waarschuwing? Klik met de rechtermuisknop op dit bestand en kies "Open".
curl -fsSL --max-time 20 "https://m365admin.justsecure.nl/download/install-mac.sh?t=$(date +%s)" | bash
echo ""
read -r -p "  Druk op Enter om dit venster te sluiten..." _ </dev/tty || true
