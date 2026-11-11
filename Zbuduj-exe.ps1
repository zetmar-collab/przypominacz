# Przebudowuje Przypominacz.exe po zmianach w przypominacz.py
Set-Location $PSScriptRoot
Get-Process Przypominacz -ErrorAction SilentlyContinue | Stop-Process -Force

# Zasob wersji bierze numer z __version__ w kodzie - jedno miejsce prawdy
& .\.venv\Scripts\python.exe .\Zrob-wersje.py

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed `
    --name Przypominacz --icon "$PSScriptRoot\ikona.ico" `
    --version-file "$PSScriptRoot\build\wersja.txt" `
    --distpath . --workpath build --specpath build przypominacz.py
Write-Host "Gotowe: $PSScriptRoot\Przypominacz.exe"
