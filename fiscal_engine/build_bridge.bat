@echo off
rem Rebuilds PondoFiscalBridge.exe from PondoFiscalBridge.cs with the C# compiler that comes with Windows.
rem Only needed if PondoFiscalBridge.exe is missing or was changed. Pondo also does this by itself when needed.
cd /d "%~dp0"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
  echo The .NET Framework 4 C# compiler was not found. Install .NET Framework 4.8 from Microsoft and try again.
  pause
  exit /b 1
)
"%CSC%" /nologo /target:exe /platform:anycpu /optimize+ /out:PondoFiscalBridge.exe /reference:FiscalStackZW.dll /reference:Newtonsoft.Json.dll PondoFiscalBridge.cs
if errorlevel 1 (
  echo.
  echo Building the bridge failed - take a photo of this window and send it to Claude.
  pause
  exit /b 1
)
echo PondoFiscalBridge.exe is ready.
