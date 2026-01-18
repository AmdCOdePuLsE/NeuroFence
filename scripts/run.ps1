$ErrorActionPreference = 'Stop'

function Write-Info([string]$Message) {
    Write-Host "[neurofence] $Message"
}

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Test-Health([int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
            if ($null -ne $resp -and $resp.status -eq 'healthy') {
                return $resp
            }
        } catch {
            # keep polling
        }
        Start-Sleep -Seconds 2
    }

    throw "API health check timed out after ${TimeoutSeconds}s. Try: docker compose logs -f api"
}

Write-Info "Checking prerequisites (Docker Desktop + Compose)..."
Require-Command "docker"

# Verify docker daemon is reachable
try {
    docker version | Out-Null
} catch {
    throw "Docker daemon not reachable. Ensure Docker Desktop is running."
}

# Move to repo root (scripts folder is one level down)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

Write-Info "Starting services (db + api)..."

# Proactively pull postgres image; if the user is logged in with an unverified account, Docker Hub can reject pulls.
try {
    docker compose pull db | Out-Null
} catch {
    Write-Info "Compose pull failed; trying docker logout then pull again..."
    try { docker logout | Out-Null } catch { }
    docker compose pull db | Out-Null
}

# Build and start
& docker compose up -d --build | Out-Null

Write-Info "Waiting for API health..."
$health = Test-Health -TimeoutSeconds 240
Write-Info ("API is healthy (version={0})." -f $health.version)

Write-Info "Running tests (pytest inside api container)..."
& docker compose exec -T api pytest -q

Write-Info "All good."
Write-Info "Open: http://localhost:8000/health"
Write-Info "Stop: docker compose down (add -v to wipe DB volume)"
