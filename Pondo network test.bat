@echo off
title Pondo network test - leave open for 3 minutes
cd /d "%~dp0"
if exist "%USERPROFILE%\Pondo Bakery\python\python.exe" (set "PY=%USERPROFILE%\Pondo Bakery\python\python.exe") else (set "PY=python")
echo.
echo  Pondo network test is running for 3 minutes.
echo  On the PHONE open:   http://192.168.0.106:8770
echo.
"%PY%" "%USERPROFILE%\Pondo Bakery\data\network_test.py"
echo.
echo  Finished. Tell Claude "done".
pause
