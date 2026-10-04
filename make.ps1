# Windows stopgap for GNU make, which is not installed by default on Windows.
#
# THE MAKEFILE IS CANONICAL. This file duplicates its commands, so the two can
# drift. To remove the duplication:
#     winget install ezwinports.make
#     Remove-Item make.ps1
# ...and use `make` directly.
#
# Usage:  .\make.ps1 setup | up | check | socket-test | ...

param(
    [Parameter(Position = 0)][string]$Target = "help",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

# NOT "Stop": PowerShell 5.1 turns a native command's stderr into a terminating
# ErrorRecord, and pnpm writes its "$ eslint ." banner to stderr. That made a
# passing lint look like a failure. Judge native tools by exit code only.
$ErrorActionPreference = "Continue"

$root    = $PSScriptRoot
$cp      = Join-Path $root "apps\control-plane"
$console = Join-Path $root "apps\console"
# --env-file is REQUIRED: compose reads .env from the compose file's
# directory, so the repo-root .env is otherwise silently inert.
$compose = @("compose", "--env-file", (Join-Path $root ".env"),
             "-f", (Join-Path $root "infra\docker-compose.yml"))

function Invoke-Step([string]$Label, [scriptblock]$Block) {
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "$Label FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Invoke-InConsole([string]$Label, [string[]]$PnpmArgs) {
    Write-Host "==> $Label" -ForegroundColor Cyan
    Push-Location $console
    try { pnpm @PnpmArgs } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "$Label FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Todo([string]$Phase) {
    Write-Host "Not implemented until $Phase." -ForegroundColor Yellow
    exit 1
}

switch ($Target) {
    "setup" {
        $envPath = Join-Path $root ".env"
        if (-not (Test-Path $envPath)) {
            # Compose needs it to exist. A real .env is never overwritten.
            Copy-Item (Join-Path $root ".env.example") $envPath
            Write-Host "Created .env - set KAVACH_TARGET_ADMIN_TOKEN in it." -ForegroundColor Yellow
        }
        Invoke-Step "uv sync" { uv --directory $cp sync --extra dev }
        Invoke-InConsole "pnpm install" @("install")
    }
    "up"          { Invoke-Step "compose up"   { docker @compose up -d --build } }
    "down"        { Invoke-Step "compose down" { docker @compose down } }
    "logs"        { docker @compose logs -f @Rest }
    "ps"          { docker @compose ps }

    "dev-api" {
        # NOT 8080: `make up` publishes the container there, and on Windows a
        # local uvicorn binds the same port without error and shadows it.
        $devPort = if ($env:DEV_API_PORT) { $env:DEV_API_PORT } else { "8081" }
        Write-Host "Hot-reload API on $devPort. The NORMAL path is 'make up' on 8080." -ForegroundColor Yellow
        uv --directory $cp run uvicorn kavach.main:app --reload --port $devPort
    }
    "dev-console" { Push-Location $console; try { pnpm dev } finally { Pop-Location } }

    "lint" {
        Invoke-Step "ruff check" { uv --directory $cp run ruff check . }
        Invoke-Step "ruff check harness" { uv --directory $cp run ruff check ../../harness }
        Invoke-InConsole "eslint" @("lint")
    }
    "format" {
        Invoke-Step "ruff format"    { uv --directory $cp run ruff format . }
        Invoke-Step "ruff check fix" { uv --directory $cp run ruff check --fix . }
    }
    "types" {
        Invoke-Step "mypy --strict" { uv --directory $cp run mypy }
        Invoke-Step "mypy harness" { uv --directory $cp run mypy --strict ../../harness }
        Invoke-InConsole "tsc --noEmit" @("types")
    }
    "test" {
        Invoke-Step "pytest" { uv --directory $cp run pytest -q }
        Invoke-InConsole "vitest" @("test")
    }
    "socket-test" { Invoke-Step "docker socket" { uv --directory $cp run pytest -q -m docker -v } }

    "gen-client" {
        Invoke-Step "openapi" { uv --directory $cp run python -m kavach.openapi }
        Invoke-InConsole "openapi-typescript" @("gen:client")
    }

    "check" {
        # gen-client first, so types checks the console against a fresh client.
        & $PSCommandPath gen-client
        & $PSCommandPath lint
        & $PSCommandPath types
        & $PSCommandPath test
        Write-Host "check: OK" -ForegroundColor Green
    }

    "target-up" {
        Write-Host "The target is a SEPARATE compose project in its own repo." -ForegroundColor Yellow
        Write-Host '  cd "D:\Vit\Academics Sem-5\EDI\Target_RAG-App"; docker compose up -d'
        Write-Host "Wired into this script in P1."
        exit 1
    }
    "test-integration" { Todo "P3" }
    "migrate"          { Todo "P3" }
    "migration"        { Todo "P3" }
    "onboard"          { Todo "P1" }
    "inject"           { Todo "P2" }
    "scenario"         { Todo "P9" }
    "bench"            { Todo "P8" }

    default {
        Write-Host "Kavach (Windows shim for the Makefile)"
        Write-Host "  setup  up  down  logs  ps  dev-api  dev-console"
        Write-Host "  lint  format  types  test  socket-test  check"
        Write-Host ""
        Write-Host "See AGENTS.md for the full list. Install GNU make to use the Makefile directly."
    }
}
