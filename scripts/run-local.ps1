param([string]$InputMatch='data/examples/movement-match',[int]$Port=8082,[switch]$Demo,[switch]$Live)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$runtime = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Run scripts/setup-local.ps1 first, or use python -m backend.app.server --provider demo.' }
$provider = if ($Demo) { 'demo' } else { 'ollama' }
$serverArguments=@('-m','backend.app.server','--input',$InputMatch,'--port',"$Port",'--provider',$provider)
if ($Live) { $serverArguments += '--live' }
& $runtime @serverArguments
