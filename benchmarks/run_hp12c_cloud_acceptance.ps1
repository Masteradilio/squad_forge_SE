param(
    [string]$WorkspacePath,
    [ValidateSet("docker", "local")]
    [string]$SandboxType = "docker",
    [int]$RunTimeoutSeconds = 14400
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = $null
foreach ($candidate in @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root ".codex_venv\Scripts\python.exe"),
    "python"
)) {
    if ($candidate -eq "python" -or (Test-Path -LiteralPath $candidate)) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    throw "No Python interpreter found. Activate .venv or install Python."
}

$arguments = @(
    (Join-Path $root "scripts\run_hp12c_cloud_acceptance.py"),
    "--sandbox-type", $SandboxType,
    "--run-timeout", $RunTimeoutSeconds
)
if ($WorkspacePath) {
    $arguments += @("--workspace", $WorkspacePath)
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $root "backend"
& $python @arguments
exit $LASTEXITCODE
