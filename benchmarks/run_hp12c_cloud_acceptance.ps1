param(
    [string]$WorkspacePath,
    [ValidateSet("docker", "local")]
    [string]$SandboxType = "docker"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$workspace = if ($WorkspacePath) { (Resolve-Path $WorkspacePath).Path } else {
    Join-Path $root "benchmarks\workspaces\hp12c-cloud-acceptance-19"
}
$python = Join-Path $root ".codex_venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "backend"
$env:LOCALFORGE_MODEL_PROVIDER = "omniroute"
$env:LOCALFORGE_MODEL_BASE_URL = "http://127.0.0.1:20128/v1"
$env:LOCALFORGE_DEFAULT_MODEL = "oc/nemotron-3-ultra-free"
$env:LOCALFORGE_FALLBACK_MODELS = "oc/mimo-v2.5-free,oc/north-mini-code-free,auto/best-free"
$env:LOCALFORGE_CHIEF_PROVIDER = "omniroute"
$env:LOCALFORGE_CHIEF_BASE_URL = "http://127.0.0.1:20128/v1"
$env:LOCALFORGE_CHIEF_MODEL = "oc/nemotron-3-ultra-free"
$env:LOCALFORGE_CHIEF_VISUAL_MODEL = "oc/mimo-v2.5-free"
$env:LOCALFORGE_CHIEF_FALLBACK_MODELS = "oc/mimo-v2.5-free,oc/north-mini-code-free,auto/best-free"
$env:LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS = "oc/mimo-v2.5-free,oc/north-mini-code-free,auto/best-free"
$env:LOCALFORGE_SANDBOX_TYPE = $SandboxType
$env:LOCALFORGE_SANDBOX_IMAGE = "forgeos-sandbox:py312"
$env:LOCALFORGE_OMNIROUTE_MAX_OUTPUT_TOKENS = "8000"
$env:LOCALFORGE_OMNIROUTE_REASONING_EFFORT = "none"
$env:LOCALFORGE_OMNIROUTE_REQUEST_TIMEOUT = "180"
$env:LOCALFORGE_CHIEF_PREFLIGHT_TIMEOUT = "25"
$env:LOCALFORGE_CHIEF_PREFLIGHT_MAX_ATTEMPTS = "1"
$env:LOCALFORGE_VISUAL_REQUEST_TIMEOUT = "60"
$env:LOCALFORGE_VISUAL_SECTION_FALLBACK = "true"
$env:LOCALFORGE_CHIEF_MAX_ACTIVE_MODEL_CALLS = "16"
$env:LOCALFORGE_VISUAL_MAX_ACTIVE_MODEL_CALLS = "96"
$env:LOCALFORGE_VISUAL_MAX_TASK_DURATION = "3600"
# Keep the route budget finite, but large enough for a full 18-task run with
# bounded Chief Engineer recovery rounds.
$env:LOCALFORGE_MAX_PAID_CALLS = "120"
$env:LOCALFORGE_MAX_PAID_INPUT_TOKENS = "800000"
$env:LOCALFORGE_MAX_PAID_OUTPUT_TOKENS = "240000"
$env:LOCALFORGE_MAX_PAID_USD = "4"
$env:LOCALFORGE_MAX_RUN_RECOVERY_CYCLES = "8"

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $bounded = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -PassThru -WindowStyle Hidden
    if (-not $bounded.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $bounded.Id -Force -ErrorAction SilentlyContinue
        throw "Command '$FilePath' exceeded the ${TimeoutSeconds}s pre-flight timeout."
    }
    if ($bounded.ExitCode -ne 0) {
        throw "Command '$FilePath' failed during pre-flight with exit code $($bounded.ExitCode)."
    }
}

if ($env:LOCALFORGE_SANDBOX_TYPE -eq "docker") {
    Invoke-BoundedProcess -FilePath $python -ArgumentList @(
        "-c",
        "import docker; client = docker.from_env(timeout=10); client.ping()"
    ) -TimeoutSeconds 20
    docker image inspect $env:LOCALFORGE_SANDBOX_IMAGE 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & docker build --file (Join-Path $root "Dockerfile.sandbox") --tag $env:LOCALFORGE_SANDBOX_IMAGE $root
        if ($LASTEXITCODE -ne 0) {
            throw "Could not build the ForgeOS sandbox image '$env:LOCALFORGE_SANDBOX_IMAGE'."
        }
    }
} else {
    Write-Host "Using explicit local development sandbox; Docker isolation is not part of this run."
}

Push-Location $workspace
try {
    $sampleDocs = Join-Path $root "samples\e2e-hp12c-platinum\docs"
    $workspaceDocs = Join-Path $workspace "docs"
    New-Item -ItemType Directory -Path $workspaceDocs -Force | Out-Null
    foreach ($document in @("PRD.md", "hp12c_platinum_design_target.png")) {
        $source = Join-Path $sampleDocs $document
        $destination = Join-Path $workspaceDocs $document
        if (-not (Test-Path $source)) {
            throw "Missing HP12C benchmark source document '$source'."
        }
        if (-not (Test-Path $destination)) {
            Copy-Item -LiteralPath $source -Destination $destination
        }
    }
    $gitMetadata = Join-Path $workspace ".git"
    $hasGitCommit = $false
    if (Test-Path $gitMetadata) {
        try {
            git rev-parse --verify HEAD 2>&1 | Out-Null
            $hasGitCommit = ($LASTEXITCODE -eq 0)
        } catch {
            $hasGitCommit = $false
        }
    }
    if (-not (Test-Path $gitMetadata)) {
        git init --initial-branch=main | Out-Null
    }
    if (-not $hasGitCommit) {
        git config user.name "ForgeOS Benchmark"
        git config user.email "benchmark@forgeos.invalid"
        git add -- docs/PRD.md docs/hp12c_platinum_design_target.png
        git commit -m "chore: initialize HP12C benchmark baseline" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not initialize the benchmark workspace Git baseline."
        }
    }
    git rev-parse --show-toplevel | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark workspace is not a valid Git repository after initialization."
    }
} finally {
    Pop-Location
}

Push-Location $workspace
try {
    $databasePath = Join-Path $workspace ".localforge\localforge.db"
    if (-not (Test-Path $databasePath)) {
        & $python -m localforge.cli.main init
        if ($LASTEXITCODE -ne 0) {
            throw "Could not initialize the ForgeOS benchmark workspace."
        }
    }
    $existingTasks = & $python -c "import sqlite3; print(sqlite3.connect(r'$databasePath').execute('select count(*) from tasks').fetchone()[0])"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect benchmark task state."
    }
    if ([int]$existingTasks -eq 0) {
        & $python -m localforge.cli.main import-prd docs\PRD.md
        if ($LASTEXITCODE -ne 0) {
            throw "Could not import the HP12C benchmark PRD."
        }
    } else {
        Write-Host "Reusing existing benchmark tasks: $existingTasks"
    }
    & $python -m localforge.cli.main plan --approve-all
    if ($LASTEXITCODE -ne 0) {
        throw "Could not approve the HP12C benchmark plans."
    }
    $runningRuns = & $python -c "import sqlite3; print(sqlite3.connect(r'$databasePath').execute('select count(*) from runs where status=?', ('RUNNING',)).fetchone()[0])"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect existing benchmark runs."
    }
    if ([int]$runningRuns -gt 0) {
        throw "Benchmark workspace already has a RUNNING execution; use a fresh workspace instead of creating a concurrent run."
    }
} finally {
    Pop-Location
}

$out = Join-Path $workspace "run.console.log"
$err = Join-Path $workspace "run.stderr.log"
$process = Start-Process -FilePath $python `
    -ArgumentList @("-m", "localforge.cli.main", "run", "--unattended") `
    -WorkingDirectory $workspace `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -WindowStyle Hidden `
    -PassThru
$process | Select-Object Id, StartTime
