# Lokal LiveKit sunucusunu açar (sesli/görüntülü görüşme için).
# Program yoksa resmi GitHub sürümünden indirir; bin/ klasörü repoya girmez.
# Geliştirme modu: adres ws://localhost:7880, anahtar devkey / secret (sadece bu bilgisayar için).
$ErrorActionPreference = "Stop"
$version = "1.13.10"
$bin = Join-Path $PSScriptRoot "bin"
$exe = Join-Path $bin "livekit-server.exe"

if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force $bin | Out-Null
    $zip = Join-Path $bin "livekit.zip"
    $url = "https://github.com/livekit/livekit/releases/download/v$version/livekit_${version}_windows_amd64.zip"
    Write-Host "LiveKit indiriliyor: $url"
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $bin -Force
    Remove-Item $zip
}

& $exe --dev
