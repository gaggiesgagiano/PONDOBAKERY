# Makes the "Pondo Bakery" icon on the desktop and in the Start menu (pointing at Pondo Bakery.exe).
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$exe = Join-Path $here 'Pondo Bakery.exe'
if (-not (Test-Path $exe)) {
    Write-Host ""
    Write-Host "  'Pondo Bakery.exe' is missing from this folder." -ForegroundColor Red
    exit 1
}
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $s = $ws.CreateShortcut((Join-Path $dir 'Pondo Bakery.lnk'))
    $s.TargetPath = $exe
    $s.Arguments = ''
    $s.WorkingDirectory = $here
    $s.IconLocation = $exe + ',0'
    $s.Description = 'Pondo Bakery'
    $s.Save()
}
Write-Host ""
Write-Host "  Done! The Pondo Bakery icon is on your desktop and in the Start menu." -ForegroundColor Green
Write-Host "  To pin it: right-click 'Pondo Bakery.exe' (or the icon) - 'Show more options' - 'Pin to taskbar'."
