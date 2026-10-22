@echo off
title Pondo - allow phones and other computers
rem Lets phones and computers on the SHOP Wi-Fi open Pondo (port 8765).
rem Run it once, at the shop, on the shop Wi-Fi. It asks for permission (Yes) because it changes the Windows Firewall.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo.
echo  Pondo Bakery - allowing phones and other computers on this Wi-Fi
echo  ----------------------------------------------------------------
echo.
echo  1. Setting this Wi-Fi network to Private ...
powershell -NoProfile -Command "Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } | Set-NetConnectionProfile -NetworkCategory Private; Get-NetConnectionProfile | ForEach-Object { '     ' + $_.Name + ' : ' + $_.NetworkCategory }"
echo.
echo  2. Opening Pondo's door (port 8765) for private networks only ...
netsh advfirewall firewall delete rule name="Pondo Bakery (port 8765)" >nul 2>&1
netsh advfirewall firewall add rule name="Pondo Bakery (port 8765)" dir=in action=allow protocol=TCP localport=8765 profile=private,domain >nul
if errorlevel 1 (echo      Could not add the rule.) else (echo      Done.)
echo.
echo  3. This laptop's address for phones:
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { '     http://' + $_.IPAddress + ':8765' }"
echo.
echo  Now open that address in Chrome on the phone (same Wi-Fi).
echo.
pause
