param([int]$Port=8765,[switch]$Gemini,[switch]$Offline,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
function Refresh-Path {
    $env:Path = (@($env:Path, [Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User')) -join ';')
}
function Find-Python {
    $candidates = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $candidates += @{exe=$py.Source; prefix=@('-3')} }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*\WindowsApps\*') { $candidates += @{exe=$python.Source; prefix=@()} }
    foreach ($v in @('312','313','311','314')) {
        foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles")) {
            $p = Join-Path $base "Python$v\python.exe"
            if (Test-Path -LiteralPath $p) { $candidates += @{exe=$p; prefix=@()} }
        }
    }
    foreach ($c in $candidates) {
        $prefix = $c.prefix
        try {
            $exe = $c.exe
            & $exe @prefix -c 'import sys,venv; assert sys.version_info >= (3,11)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch { }
    }
    return $null
}
function Find-Ollama {
    $cmd = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $p = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $p) { return $p }
    return $null
}
function Install-Package([string]$Id) {
    $wg = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $wg) { throw "Missing winget (App Installer). Install it or install $Id manually, then retry." }
    Write-Host "Installing $Id via Windows Package Manager..."
    $wgExe = $wg.Source
    & $wgExe install --id $Id --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget installation failed: $Id ($LASTEXITCODE)" }
    Refresh-Path
}
$runtime = Find-Python
if (-not $runtime) {
    Install-Package 'Python.Python.3.12'
    $runtime = Find-Python
    if (-not $runtime) { throw 'Python 3.11+ not detected after installation. Reopen the terminal and retry.' }
}
if (-not $Offline -and -not $Gemini) {
    $ollama = Find-Ollama
    if (-not $ollama) {
        Install-Package 'Ollama.Ollama'
        $ollama = Find-Ollama
        if (-not $ollama) { throw 'Ollama not detected after installation. Reopen the terminal and retry.' }
    }
    $env:Path = "$(Split-Path -Parent $ollama);$env:Path"
}
$cmdArgs=@((Join-Path $PSScriptRoot 'team_launch.py'),'--port',"$Port")
if ($Gemini) { $cmdArgs += '--gemini' }
if ($Offline) { $cmdArgs += '--offline' }
if ($NoBrowser) { $cmdArgs += '--no-browser' }
$prefix = $runtime.prefix
$pythonExe = $runtime.exe
& $pythonExe @prefix @cmdArgs
exit $LASTEXITCODE
