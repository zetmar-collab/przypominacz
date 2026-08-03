# Przebudowuje Przypominacz.exe po zmianach w przypominacz.py
Set-Location $PSScriptRoot
Get-Process Przypominacz -ErrorAction SilentlyContinue | Stop-Process -Force
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed `
    --name Przypominacz --icon "$PSScriptRoot\ikona.ico" `
    --distpath . --workpath build --specpath build przypominacz.py
Write-Host "Gotowe: $PSScriptRoot\Przypominacz.exe"
