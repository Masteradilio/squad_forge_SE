[CmdletBinding()]
param(
    [ValidateSet("compose", "helm")]
    [string]$Mode = "compose",
    [switch]$Build,
    [switch]$SkipRedisProbe,
    [string]$ReleaseName = "forgeos",
    [string]$Namespace = "forgeos",
    [string]$KubernetesContext = "docker-desktop",
    [string]$SecretName = "forgeos-runtime-secrets",
    [switch]$UseLocalImages
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ChartPath = Join-Path $ProjectRoot "deploy\helm\forgeos-cloud"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Compose([string[]]$Arguments) {
    Push-Location $ProjectRoot
    try {
        & docker compose @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Wait-RedisHealthy {
    $deadline = (Get-Date).AddMinutes(2)
    do {
        $health = (& docker inspect --format '{{.State.Health.Status}}' forgeos-redis 2>$null).Trim()
        if ($health -eq "healthy") {
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    & docker inspect --format '{{.State.Status}} / {{.State.Health.Status}}' forgeos-redis 2>$null
    throw "Redis did not become healthy before the 2-minute deadline."
}

function Wait-HttpHealthy([string]$Uri) {
    $deadline = (Get-Date).AddMinutes(2)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            # The service may still be starting; retain the bounded retry.
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "HTTP service '$Uri' did not become healthy before the 2-minute deadline."
}

function Start-ComposeMode {
    Require-Command "docker"
    Require-Command "python"

    Push-Location $ProjectRoot
    try {
        & docker compose config --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose config validation failed. Check .env and required variables."
        }
    }
    finally {
        Pop-Location
    }

    $composeArgs = @("up", "-d")
    if ($Build) {
        $composeArgs += "--build"
    }
    Invoke-Compose $composeArgs
    Wait-RedisHealthy
    Wait-HttpHealthy "http://127.0.0.1:8000/ready"
    Wait-HttpHealthy "http://127.0.0.1:5173/"

    if (-not $SkipRedisProbe) {
        Push-Location $ProjectRoot
        try {
            & python "scripts/probe_redis.py"
            if ($LASTEXITCODE -ne 0) {
                throw "Redis probe failed with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Compose @("ps")
}

function Start-HelmMode {
    Require-Command "helm"
    Require-Command "kubectl"

    & kubectl --context $KubernetesContext cluster-info 1>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Kubernetes context '$KubernetesContext' is unavailable. Enable Docker Desktop Kubernetes or select a configured context."
    }

    & kubectl --context $KubernetesContext get namespace $Namespace 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        & kubectl --context $KubernetesContext create namespace $Namespace 1>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create namespace '$Namespace'."
        }
    }

    & kubectl --context $KubernetesContext --namespace $Namespace get secret $SecretName 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Secret '$SecretName' is missing in namespace '$Namespace'. Create it from the local secret store before running Helm; secret values are never accepted as script arguments."
    }

    Push-Location $ProjectRoot
    try {
        & helm lint $ChartPath
        if ($LASTEXITCODE -ne 0) {
            throw "helm lint failed with exit code $LASTEXITCODE."
        }

        $helmArgs = @(
            "upgrade", "--install", $ReleaseName, $ChartPath,
            "--namespace", $Namespace,
            "--kube-context", $KubernetesContext,
            "--wait",
            "--timeout", "10m"
        )
        if ($UseLocalImages) {
            $helmArgs += @(
                "--set", "backend.image.repository=local_forge_os-backend",
                "--set", "backend.image.tag=latest",
                "--set", "backend.image.pullPolicy=IfNotPresent",
                "--set", "frontend.image.repository=local_forge_os-frontend",
                "--set", "frontend.image.tag=latest",
                "--set", "frontend.image.pullPolicy=IfNotPresent",
                "--set", "omniroute.image.repository=diegosouzapw/omniroute",
                "--set", "omniroute.image.tag=latest",
                "--set", "omniroute.image.pullPolicy=IfNotPresent",
                "--set", "autoscaling.enabled=false"
            )
        }
        & helm @helmArgs
        if ($LASTEXITCODE -ne 0) {
            throw "helm upgrade --install failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

if ($Mode -eq "compose") {
    Start-ComposeMode
}
else {
    Start-HelmMode
}
