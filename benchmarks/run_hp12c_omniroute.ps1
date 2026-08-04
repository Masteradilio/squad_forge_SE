param([string]$WorkspaceName = "hp12c-v6-omniroute-e2e-10")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$workspace = Join-Path $root "benchmarks\workspaces\$WorkspaceName"
$env:PYTHONPATH = Join-Path $root "backend"
$env:PYTHONIOENCODING = "utf-8"
$env:LOCALFORGE_MODEL_PROVIDER = "ollama"
$env:LOCALFORGE_MODEL_BASE_URL = "http://localhost:11434/v1"
$env:LOCALFORGE_DEFAULT_MODEL = "gemma4:12b"
$env:LOCALFORGE_FALLBACK_MODELS = "granite4.1:8b,nemotron-3-nano:4b"
$env:LOCALFORGE_CHIEF_PROVIDER = "omniroute"
$env:LOCALFORGE_CHIEF_BASE_URL = "http://localhost:20128/v1"
$env:LOCALFORGE_CHIEF_MODEL = "auto/pro-coding"
$env:LOCALFORGE_CHIEF_VISUAL_MODEL = "auto/multimodal"
$env:LOCALFORGE_CHIEF_API_KEY = ""
$env:LOCALFORGE_OMNIROUTE_JSON_VERIFIED = "true"
$env:LOCALFORGE_LLM_MAX_OUTPUT_TOKENS = "12000"
$log = Join-Path $workspace "run.console.log"
Push-Location $workspace
try {
    & (Join-Path $root ".venv\Scripts\python.exe") -m localforge.cli.main run --unattended *> $log
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
