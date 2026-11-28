@echo off
title Microsoft 365 beheer installeren
rem Haalt het installatiescript (altijd de nieuwste versie) van de updateserver en voert het uit.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { [Net.ServicePointManager]::SecurityProtocol='Tls12' } catch {}; try { $s = Invoke-RestMethod -Uri ('https://m365admin.justsecure.nl/download/install-windows.ps1?t=' + [guid]::NewGuid()) -TimeoutSec 20 } catch { Write-Host ''; Write-Host '  De updateserver is niet bereikbaar. Controleer je internetverbinding.' -ForegroundColor Red; exit 1 }; & ([scriptblock]::Create($s))"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
timeout /t 4 >nul
