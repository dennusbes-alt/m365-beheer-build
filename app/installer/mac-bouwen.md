# Microsoft 365 beheer bouwen voor Apple Silicon (M-chip)

Met deze handleiding bouw je op een Mac met een M-chip de **Apple Silicon-versie (arm64)** van
Microsoft 365 beheer. Het resultaat zet je in de GitHub-repository, waarna Justdata hem controleert
en online zet. Daarna krijgt elke M-chip-Mac automatisch deze snellere versie in plaats van de
Intel-versie via Rosetta.

Duur: eerste keer ongeveer 20 minuten, daarna ongeveer 5 minuten per versie.

## Wat je nodig hebt

- Een Mac met een M-chip (M1 of nieuwer) en macOS 11 of nieuwer
- Een beheerdersaccount op de Mac (alleen voor het installeren van Homebrew)
- Toegang tot de privé-repository `dennusbes-alt/m365-beheer` op GitHub
- Ongeveer 3 GB vrije ruimte

Controleer dat je echt op Apple Silicon zit. Dit moet `arm64` geven:

```bash
uname -m
```

Staat er `x86_64`, dan draait Terminal via Rosetta. Sluit Terminal, kies in Finder bij
Programma's > Hulpprogramma's > Terminal > Toon info en zet "Open met Rosetta" uit.

## Stap 1: Homebrew (eenmalig)

Heb je Homebrew al (`brew -v` geeft een versie), sla deze stap dan over.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

## Stap 2: Python, Node.js en GitHub CLI (eenmalig)

```bash
brew install python@3.13 node gh
```

Gebruik Python 3.13: daarmee is de app getest en gebouwd.

## Stap 3: Inloggen bij GitHub (eenmalig)

```bash
gh auth login --web --hostname github.com --git-protocol https
```

Er verschijnt een code van 8 tekens en de browser opent. Log in, vul de code in en klik op
**Authorize**. Beantwoord de vraag of git je GitHub-login mag gebruiken met **Yes**.

## Stap 4: Code ophalen

De eerste keer:

```bash
gh repo clone dennusbes-alt/m365-beheer ~/m365-beheer
```

Bij een volgende versie (bestaande map bijwerken):

```bash
git -C ~/m365-beheer pull
```

## Stap 5: Bouwen

```bash
cd ~/m365-beheer/app
PYTHON=python3.13 bash bouwen-mac.sh
```

Het script maakt een eigen Python-omgeving (`.venv-mac`), bouwt de interface en daarna de app.
Aan het eind staat het resultaat in `uitvoer/release/mac/`. Controleer dat de bestandsnaam
`arm64` bevat:

```bash
ls uitvoer/release/mac/
```

Je ziet dan bijvoorbeeld:

```
Microsoft-365-beheer-2.4.2-mac-arm64.json
Microsoft-365-beheer-2.4.2-mac-arm64.zip
```

## Stap 6: Even testen (aanbevolen)

Start de zojuist gebouwde app direct vanuit de bouwmap:

```bash
open "$TMPDIR/m365beheer-bouw/dist/Microsoft 365 beheer.app"
```

Het venster van Microsoft 365 beheer moet openen met het inlogscherm. Je hoeft niet in te loggen;
sluit de app weer. Controleer in Activiteitenweergave (kolom "Soort") dat er **Apple** staat en
niet Intel.

## Stap 7: Resultaat naar GitHub sturen

```bash
cd ~/m365-beheer/app
VERSIE=$(sed -n "s/^__version__ = '\(.*\)'/\1/p" backend/m365beheer/__init__.py)
gh release create "mac-arm64-$VERSIE" uitvoer/release/mac/*"$VERSIE"-mac-arm64.* \
  --repo dennusbes-alt/m365-beheer --prerelease \
  --title "Mac Apple Silicon $VERSIE" --notes "Gebouwd op $(sw_vers -productVersion), $(uname -m)"
```

Bestaat die release al (je bouwt dezelfde versie opnieuw), voeg dan `--clobber` toe en gebruik
`gh release upload` in plaats van `gh release create`:

```bash
gh release upload "mac-arm64-$VERSIE" uitvoer/release/mac/*"$VERSIE"-mac-arm64.* --repo dennusbes-alt/m365-beheer --clobber
```

Laat daarna weten dat de Mac-versie klaarstaat. Justdata haalt hem op, controleert hem en zet hem
online. Er komt niets online zonder die controle.

## Problemen oplossen

| Melding | Oplossing |
| --- | --- |
| `xcrun: error: invalid active developer path` | `xcode-select --install` en daarna opnieuw bouwen |
| `python3.13: command not found` | `brew install python@3.13` en een nieuw Terminal-venster openen |
| `npm: command not found` | `brew install node` en een nieuw Terminal-venster openen |
| Fout bij `pip install` | De map opnieuw opbouwen: `rm -rf .venv-mac` en stap 5 opnieuw |
| Fout bij `npm ci` | `rm -rf frontend/node_modules` en stap 5 opnieuw |
| Bestandsnaam bevat `x86_64` in plaats van `arm64` | Terminal draait via Rosetta, zie "Wat je nodig hebt". Daarna `rm -rf .venv-mac` en opnieuw bouwen |
| `gh: Not Found` bij clonen | Je GitHub-account heeft geen toegang tot de repository; vraag Justdata om je toe te voegen |

## Goed om te weten

- Er gaan geen wachtwoorden, tokens of servergegevens mee: die staan niet in de repository.
- De app is niet door Apple ondertekend. Installeren via de Terminal-installer
  (`curl -fsSL https://m365admin.justsecure.nl/download/install-mac.sh | bash`) geeft daardoor
  geen waarschuwing van macOS.
