@echo off
title Pondo Bakery
cd /d "%~dp0"
rem Trouble-shooting start: shows the black window with any error messages.
set "PY="
if exist "python\python.exe" set "PY=python\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo  Pondo cannot find Python. The "python" folder must be inside the Pondo Bakery folder.
  echo.
  pause
  exit /b
)
%PY% run.py
if errorlevel 1 pause
