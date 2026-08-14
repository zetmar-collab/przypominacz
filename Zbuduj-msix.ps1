# Buduje pakiet MSIX do Sklepu Windows.
#   .\Zbuduj-msix.ps1              -> Przypominacz.msix (niepodpisany, do Partner Center)
#   .\Zbuduj-msix.ps1 -Podpisz     -> dodatkowo podpisuje certyfikatem testowym do instalacji lokalnej
param([switch]$Podpisz)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$sdk = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe" |
    Sort-Object FullName | Select-Object -Last 1
if (-not $sdk) { throw "Brak makeappx.exe - zainstaluj Windows SDK (winget install Microsoft.WindowsSDK)." }
$makeappx = $sdk.FullName
$makepri  = Join-Path $sdk.DirectoryName "makepri.exe"
$signtool = Join-Path $sdk.DirectoryName "signtool.exe"

# 1. Exe i logotypy - exe budujemy zawsze, zeby do pakietu nie trafil stary plik
& .\Zbuduj-exe.ps1
& .\.venv\Scripts\python.exe .\Zrob-assety.py

# 2. Katalog roboczy pakietu
$stage = ".\build\msix"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage, "$stage\Assets" -Force | Out-Null
Copy-Item .\Przypominacz.exe $stage
Copy-Item .\AppxManifest.xml $stage
Copy-Item .\Assets\* "$stage\Assets"

# 3. Zasoby (resources.pri) - Sklep tego oczekuje
Push-Location $stage
& $makepri createconfig /cf priconfig.xml /dq pl-PL /o | Out-Null
& $makepri new /pr . /cf priconfig.xml /of resources.pri /o | Out-Null
Remove-Item priconfig.xml
Pop-Location

# 4. Pakowanie
$msix = ".\Przypominacz.msix"
if (Test-Path $msix) { Remove-Item $msix -Force }
& $makeappx pack /d $stage /p $msix /o
if ($LASTEXITCODE -ne 0) { throw "makeappx zwrocil blad $LASTEXITCODE" }

# 5. Opcjonalny podpis testowy (tylko do sprawdzenia instalacji u siebie)
if ($Podpisz) {
    $cn = ([xml](Get-Content .\AppxManifest.xml)).Package.Identity.Publisher
    $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $cn } | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type Custom -Subject $cn -KeyUsage DigitalSignature `
            -FriendlyName "Przypominacz test" -CertStoreLocation "Cert:\CurrentUser\My" `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
        Write-Host "Utworzono certyfikat testowy. Zaufaj mu (jako administrator):"
        Write-Host "  Export-Certificate -Cert Cert:\CurrentUser\My\$($cert.Thumbprint) -FilePath test.cer"
        Write-Host "  Import-Certificate -FilePath test.cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople"
    }
    & $signtool sign /fd SHA256 /a /sha1 $cert.Thumbprint $msix
    if ($LASTEXITCODE -ne 0) { throw "signtool zwrocil blad $LASTEXITCODE" }
}

Write-Host ""
Write-Host "Gotowe: $((Resolve-Path $msix).Path)"
Write-Host "Do Partner Center wysylasz WERSJE NIEPODPISANA - Sklep podpisuje pakiet sam."
