# Installeert of werkt Microsoft 365 beheer (Justdata) bij voor de huidige Windows-gebruiker.
# Haalt altijd de nieuwste versie van de updateserver. Geen beheerdersrechten nodig.
#
# Gebruik:  irm https://m365admin.justsecure.nl/download/install-windows.ps1 | iex
#     of:   dubbelklik op Installeer-Microsoft-365-beheer.cmd
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # maakt downloaden in Windows PowerShell vele malen sneller
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$Naam      = 'Microsoft 365 beheer'
$Basis     = if ($env:M365_UPDATE_BASIS) { $env:M365_UPDATE_BASIS } else { 'https://m365admin.justsecure.nl/updates/windows/' }
$Test      = [bool]$env:M365_INSTALL_TEST   # alleen voor testen: installeert in TEMP, zonder snelkoppelingen en register
$Programs  = if ($Test) { Join-Path $env:TEMP 'M365BeheerInstallTest' } else { Join-Path $env:LOCALAPPDATA 'Programs\Justdata' }
$Doel      = Join-Path $Programs $Naam
$Exe       = Join-Path $Doel "$Naam.exe"
$Verwijder = Join-Path $Programs 'M365Beheer-verwijderen.ps1'
$RegPad    = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JustdataM365Beheer'

function Stap($t) { Write-Host "  $t" -ForegroundColor Cyan }
function Fout($t) {
    Write-Host ''
    Write-Host "  FOUT: $t" -ForegroundColor Red
    try { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show($t, "$Naam installeren", 'OK', 'Error') | Out-Null } catch { }
    exit 1
}

Write-Host ''
Write-Host "  $Naam installeren" -ForegroundColor White
Write-Host '  -----------------------------------------'

# 1. Nieuwste versie opvragen
Stap 'Nieuwste versie opvragen...'
try {
    $m = Invoke-RestMethod -Uri ($Basis + 'latest.json?t=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -Headers @{ 'Cache-Control' = 'no-cache' } -TimeoutSec 20
} catch {
    Fout "De updateserver is niet bereikbaar ($($_.Exception.Message)). Controleer je internetverbinding of vraag de beheerder of je netwerk toegang heeft tot m365admin.justsecure.nl."
}
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
$f = $m.files.$arch
if (-not $f) { $f = $m.files.x64 }   # Windows op ARM draait x64-programma's ook
if (-not $f) { Fout 'Er staat nog geen Windows-versie klaar op de server.' }
$url = if ($f.url -match '^https?://') { $f.url } else { $Basis + $f.url }
Stap "Versie $($m.version) gevonden."

# 2. Downloaden en controleren
$tmp = Join-Path $env:TEMP ('m365beheer-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$zip = Join-Path $tmp 'app.zip'
Stap ('Downloaden ({0:N0} MB)...' -f ([double]$f.size / 1MB))
try { Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 600 } catch { Fout "Downloaden is niet gelukt: $($_.Exception.Message)" }
if ($f.sha256) {
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
    if ($hash -ne ([string]$f.sha256).ToUpper()) { Fout 'De download is beschadigd (controlegetal klopt niet). Probeer het opnieuw.' }
    Stap 'Download gecontroleerd.'
}

# 3. Draaiende app sluiten en installeren
Get-Process -Name $Naam -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Stap 'Installeren...'
$uit = Join-Path $tmp 'uit'
New-Item -ItemType Directory -Force -Path $uit | Out-Null
$tar = Join-Path $env:SystemRoot 'System32\tar.exe'   # ingebouwd sinds Windows 10 1803, veel sneller dan Expand-Archive
if (Test-Path $tar) { & $tar -xf $zip -C $uit; if ($LASTEXITCODE -ne 0) { Expand-Archive -LiteralPath $zip -DestinationPath $uit -Force } }
else { Expand-Archive -LiteralPath $zip -DestinationPath $uit -Force }
$bron = Get-ChildItem -LiteralPath $uit -Directory | Select-Object -First 1
if (-not $bron -or -not (Test-Path (Join-Path $bron.FullName "$Naam.exe"))) { Fout 'Het downloadbestand heeft niet de verwachte inhoud.' }
New-Item -ItemType Directory -Force -Path $Doel | Out-Null
robocopy $bron.FullName $Doel /MIR /XF unins*.* /R:10 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fout "Kopieren naar $Doel is niet gelukt (robocopy $LASTEXITCODE). Is de app nog open?" }
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

if ($Test) { Write-Host "  TEST: geinstalleerd in $Doel (geen snelkoppelingen of register)." -ForegroundColor Yellow; Start-Process -FilePath $Exe; return }

# 4. Snelkoppelingen (bureaublad en Startmenu)
$sh = New-Object -ComObject WScript.Shell
foreach ($map in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    # Eerst weggooien: een bestaande snelkoppeling (bijv. van de oude PowerShell-versie) houdt anders zijn oude argumenten
    $pad = Join-Path $map "$Naam.lnk"
    Remove-Item -LiteralPath $pad -Force -ErrorAction SilentlyContinue
    $l = $sh.CreateShortcut($pad)
    $l.TargetPath = $Exe
    $l.Arguments = ''
    $l.WorkingDirectory = $Doel
    $l.IconLocation = "$Exe,0"
    $l.Description = "$Naam (Justdata)"
    $l.Save()
}

# 5. Verwijderen via Instellingen > Apps
@"
`$ErrorActionPreference = 'SilentlyContinue'
Get-Process -Name '$Naam' | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item -LiteralPath '$Doel' -Recurse -Force
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) '$Naam.lnk') -Force
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) '$Naam.lnk') -Force
Remove-Item -LiteralPath '$RegPad' -Recurse -Force
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show('$Naam is verwijderd.', '$Naam', 'OK', 'Information') | Out-Null
Remove-Item -LiteralPath `$PSCommandPath -Force
"@ | Set-Content -LiteralPath $Verwijder -Encoding UTF8
New-Item -Path $RegPad -Force | Out-Null
$reg = @{
    DisplayName = $Naam; DisplayVersion = [string]$m.version; Publisher = 'Justdata BV'; DisplayIcon = "$Exe,0"
    InstallLocation = $Doel; NoModify = 1; NoRepair = 1
    UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Verwijder`""
}
foreach ($k in $reg.Keys) { New-ItemProperty -Path $RegPad -Name $k -Value $reg[$k] -PropertyType $(if ($reg[$k] -is [int]) { 'DWord' } else { 'String' }) -Force | Out-Null }

Write-Host ''
Write-Host "  Klaar: versie $($m.version) is geinstalleerd." -ForegroundColor Green
Write-Host '  Je vindt de app op het bureaublad en in het Startmenu. Hij start nu.'
Start-Process -FilePath $Exe
