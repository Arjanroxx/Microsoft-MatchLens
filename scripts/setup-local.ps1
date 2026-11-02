param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Install Python 3.12+ with pip first.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollamaCommand) { throw 'Install Ollama from https://ollama.com/download, open it, then rerun this script.' }
& $ollamaCommand.Source pull qwen3:1.7b
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Start Ollama and retry.' }
Write-Host 'Ready. Start with: .\scripts\run-local.ps1'
