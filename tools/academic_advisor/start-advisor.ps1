param([int]$Port=8765,[switch]$Gemini,[switch]$Offline,[switch]$NoBrowser)
$ErrorActionPreference='Continue'
$env:PYTHONUTF8='1'
$cmdArgs=@((Join-Path $PSScriptRoot 'team_launch.py'),'--port',"$Port")
if ($Gemini) { $cmdArgs += '--gemini' }
if ($Offline) { $cmdArgs += '--offline' }
if ($NoBrowser) { $cmdArgs += '--no-browser' }
if (Get-Command python -ErrorAction SilentlyContinue) {
 & python -c 'import sys; assert sys.version_info >= (3,11)' 2>$null
 if ($LASTEXITCODE -eq 0) { & python @cmdArgs; exit $LASTEXITCODE }
}
if (Get-Command py -ErrorAction SilentlyContinue) {
 & py -3 -c 'import sys; assert sys.version_info >= (3,11)' 2>$null
 if ($LASTEXITCODE -eq 0) { & py -3 @cmdArgs; exit $LASTEXITCODE }
}
throw 'Python 3.11+ is required.'
