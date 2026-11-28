#!/bin/bash
# Installeert of werkt Microsoft 365 beheer (Justdata) bij op deze Mac.
# Haalt altijd de nieuwste versie van de updateserver. Geen beheerdersrechten nodig.
#
# Gebruik (Terminal):  curl -fsSL https://m365admin.justsecure.nl/download/install-mac.sh | bash
# Via curl gedownloade bestanden krijgen geen quarantaine-markering, dus macOS blokkeert de app niet.
set -uo pipefail

NAAM="Microsoft 365 beheer"
SERVER="m365admin.justsecure.nl"
BASIS="https://$SERVER/updates/mac/"
MIN_MACOS=11

stap() { printf '  \033[36m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m%s\033[0m\n' "$1"; }
fout() {
  printf '\n  \033[31mFOUT: %s\033[0m\n\n' "$1"
  local tekst=${1//\"/\'}
  osascript -e "display dialog \"$tekst\" buttons {\"OK\"} default button \"OK\" with title \"$NAAM installeren\" with icon stop" >/dev/null 2>&1 || true
  exit 1
}
# JSON uitlezen zonder Python (die staat niet standaard op een Mac): via JavaScript for Automation.
# Geeft niets terug (in plaats van een foutmelding) als de tekst geen geldige JSON is.
json() {
  osascript -l JavaScript -e 'function run(a){try{var o=JSON.parse(a[0])}catch(e){return ""}var p=a[1].split(".");for(var i=0;i<p.length;i++){o=(o==null)?undefined:o[p[i]]}return (o==null)?"":String(o)}' "$1" "$2" 2>/dev/null
}

printf '\n  %s installeren\n  -----------------------------------------\n' "$NAAM"

# 1. Controleren of deze Mac geschikt is
MACOS=$(sw_vers -productVersion 2>/dev/null || echo 0)
[ "${MACOS%%.*}" -ge "$MIN_MACOS" ] 2>/dev/null \
  || fout "Deze Mac heeft macOS $MACOS. Voor $NAAM is macOS $MIN_MACOS (Big Sur) of nieuwer nodig. Werk macOS eerst bij via Systeeminstellingen > Software-update."
ECHT=$(uname -m)
# Draait de Terminal zelf via Rosetta, dan meldt uname x86_64 op een Apple Silicon-Mac
[ "$(sysctl -in hw.optional.arm64 2>/dev/null)" = "1" ] && ECHT="arm64"
stap "macOS $MACOS ($([ "$ECHT" = arm64 ] && echo 'Apple Silicon' || echo 'Intel'))."

# 2. Nieuwste versie opvragen
stap "Nieuwste versie opvragen..."
MANIFEST=$(curl -fsSL --max-time 20 -H 'Cache-Control: no-cache' "${BASIS}latest.json?t=$(date +%s)" 2>/dev/null)
[ $? -eq 0 ] && [ -n "$MANIFEST" ] \
  || fout "De updateserver ($SERVER) is niet bereikbaar. Controleer je internetverbinding, of vraag Justdata of je netwerk toegang heeft tot de server."
VERSIE=$(json "$MANIFEST" version)
[ -n "$VERSIE" ] \
  || fout "Er staat nog geen Mac-versie van $NAAM klaar op de server. Neem contact op met Justdata."

# 3. Juiste versie voor deze Mac kiezen (Apple Silicon: eigen versie, anders de Intel-versie via Rosetta)
ARCH="$ECHT"
[ "$ARCH" = "arm64" ] || ARCH="x86_64"
URL=$(json "$MANIFEST" "files.$ARCH.url")
if [ -z "$URL" ] && [ "$ARCH" = "arm64" ]; then
  ARCH="x86_64"
  URL=$(json "$MANIFEST" "files.$ARCH.url")
  if [ -n "$URL" ] && ! /usr/bin/pgrep -q oahd; then
    stap "Rosetta installeren (nodig voor de Intel-versie)..."
    softwareupdate --install-rosetta --agree-to-license >/dev/null 2>&1 \
      || fout "Rosetta is nodig, maar kon niet automatisch geinstalleerd worden. Voer in Terminal uit: softwareupdate --install-rosetta (met een beheerderswachtwoord) en start de installatie opnieuw."
  fi
fi
[ -n "$URL" ] || fout "Er staat nog geen versie van $NAAM voor deze Mac ($ECHT) op de server. Neem contact op met Justdata."
SHA=$(json "$MANIFEST" "files.$ARCH.sha256")
case "$URL" in http*) ;; *) URL="${BASIS}${URL}" ;; esac
stap "Versie $VERSIE gevonden ($ARCH)."

# 4. Downloaden en controleren
TMP=$(mktemp -d /tmp/m365beheer.XXXXXX) || fout "Kan geen tijdelijke map maken."
trap 'rm -rf "$TMP"' EXIT
stap "Downloaden..."
curl -fL --progress-bar --max-time 900 -o "$TMP/app.zip" "$URL" \
  || fout "Downloaden is niet gelukt. Controleer je internetverbinding en probeer het opnieuw."
if [ -n "$SHA" ]; then
  [ "$(shasum -a 256 "$TMP/app.zip" | awk '{print $1}')" = "$SHA" ] \
    || fout "De download is beschadigd (controlegetal klopt niet). Probeer het opnieuw."
  ok "Download gecontroleerd."
fi
ditto -x -k "$TMP/app.zip" "$TMP/uit" 2>/dev/null || fout "Het downloadbestand kon niet uitgepakt worden. Probeer het opnieuw."
NIEUW=$(find "$TMP/uit" -maxdepth 1 -name "*.app" | head -1)
[ -n "$NIEUW" ] || fout "Het downloadbestand heeft niet de verwachte inhoud."

# 5. Installeren: in /Programma's als dat zonder wachtwoord kan, anders in de Programma's-map van de gebruiker
if [ -w /Applications ]; then DOELMAP="/Applications"; else DOELMAP="$HOME/Applications"; mkdir -p "$DOELMAP"; fi
APP="$DOELMAP/$NAAM.app"
# Een oude installatie op de andere plek opruimen, zodat er maar een in Launchpad staat
for OUD in "/Applications/$NAAM.app" "$HOME/Applications/$NAAM.app"; do
  [ "$OUD" != "$APP" ] && [ -w "$(dirname "$OUD")" ] && rm -rf "$OUD" 2>/dev/null
done
stap "Installeren in $DOELMAP..."
pkill -f "$NAAM.app/Contents/MacOS/" 2>/dev/null && sleep 1
rm -rf "$APP" 2>/dev/null
[ ! -e "$APP" ] || fout "De oude versie in $DOELMAP kon niet vervangen worden. Sluit $NAAM en probeer het opnieuw."
mv "$NIEUW" "$APP" || fout "Installeren in $DOELMAP is niet gelukt."
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

printf '\n'
ok "Klaar: versie $VERSIE is geinstalleerd in $DOELMAP."
printf '  De app start nu. Je vindt hem ook in Launchpad.\n\n'
open "$APP" 2>/dev/null \
  || printf '  Start de app zelf via Finder > %s.\n\n' "$DOELMAP"
exit 0
