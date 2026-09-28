param([string]$Python = "$PSScriptRoot/../backend/.venv/Scripts/python.exe")
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot/..").Path
$env:PYTHONPATH = "$repo;$repo/backend"
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& $Python -m scripts.release_health --dependencies-only
if ($LASTEXITCODE -ne 0) { throw 'Release preflight failed; backend was not started.' }
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
