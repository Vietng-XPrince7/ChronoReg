param([switch]$Native, [switch]$SetupOnly, [switch]$RebuildRag, [ValidateSet("auto","cuda","cpu")][string]$Device = "auto")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$flags = @('--device', $Device)
if ($SetupOnly) { $flags += '--setup-only' }
if ($RebuildRag) { $flags += '--rebuild-rag' }
# Prefer a configured Ubuntu WSL2 runtime. No security settings are changed.
if (-not $Native -and (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    $distros = ((& wsl.exe --list --quiet 2>$null) -join "`n") -replace "`0",''
    if ($LASTEXITCODE -eq 0 -and ($distros -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -eq 'Ubuntu' })) {
        & wsl.exe -d Ubuntu --exec bash ./start_chronoreg.sh @flags
        exit $LASTEXITCODE
    }
}
if ($Device -eq 'cpu') {
    $venv = Join-Path $PSScriptRoot '.local_models\web-runtime-win-cpu'
} else {
    $venv = Join-Path $PSScriptRoot '.local_models\web-runtime-win'
}
$exe = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv "$venv"
        if ($LASTEXITCODE -ne 0) { & python -m venv "$venv" }
    } else { & python -m venv "$venv" }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or 3.13 first.' }
}
$env:CUDA_VISIBLE_DEVICES = '0'
& "$exe" scripts/bootstrap_chronoreg.py @flags
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Native startup failed. Check the actual error above. If Windows blocks torch DLLs, use Ubuntu WSL2; do not disable application control.'
    exit $LASTEXITCODE
}
