@echo off
title Pondo - phone check and fix
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set "R=%USERPROFILE%\Pondo Bakery\data\phone_check.txt"
echo Working ... please wait.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$o = @();" ^
 "$o += '=== ' + (Get-Date);" ^
 "$o += '--- network profiles'; $o += (Get-NetConnectionProfile | Format-Table Name,InterfaceAlias,NetworkCategory -AutoSize | Out-String);" ^
 "$o += '--- addresses'; $o += (Get-NetIPAddress -AddressFamily IPv4 | Format-Table InterfaceAlias,IPAddress -AutoSize | Out-String);" ^
 "$o += '--- firewall on/off per profile'; $o += (Get-NetFirewallProfile | Format-Table Name,Enabled,DefaultInboundAction -AutoSize | Out-String);" ^
 "$o += '--- other security programs'; try { $o += (Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | Select-Object -ExpandProperty displayName) } catch {}; try { $o += (Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object -ExpandProperty displayName) } catch {};" ^
 "$o += '--- who listens on 8765'; $o += (netstat -ano | Select-String ':8765 ' | Out-String);" ^
 "$p = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; $exe = ''; if ($p) { $exe = (Get-Process -Id $p.OwningProcess).Path; $o += 'program: ' + $exe };" ^
 "$o += '--- BLOCK rules for python / Pondo (removed)';" ^
 "$bad = Get-NetFirewallRule -Direction Inbound -Action Block -ErrorAction SilentlyContinue | Where-Object { $f = ($_ | Get-NetFirewallApplicationFilter).Program; $f -match 'python|pondo' };" ^
 "foreach ($r in $bad) { $o += ('  ' + $r.DisplayName + ' | ' + ($r | Get-NetFirewallApplicationFilter).Program); Remove-NetFirewallRule -Name $r.Name };" ^
 "if ($exe) { Remove-NetFirewallRule -DisplayName 'Pondo Bakery (program)' -ErrorAction SilentlyContinue; New-NetFirewallRule -DisplayName 'Pondo Bakery (program)' -Direction Inbound -Action Allow -Program $exe -Profile Private,Domain | Out-Null; $o += 'allowed program: ' + $exe };" ^
 "Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue;" ^
 "$o += '--- profiles after'; $o += (Get-NetConnectionProfile | Format-Table Name,NetworkCategory -AutoSize | Out-String);" ^
 "$o += '--- Pondo allow rules'; $o += (Get-NetFirewallRule -DisplayName 'Pondo*' | Format-Table DisplayName,Enabled,Action,Profile -AutoSize | Out-String);" ^
 "$o | Out-File -Encoding utf8 $env:R"
echo.
echo  Done. Try the phone again now (tap Reload).
echo  A report was saved for Claude: Pondo Bakery\data\phone_check.txt
echo.
pause
