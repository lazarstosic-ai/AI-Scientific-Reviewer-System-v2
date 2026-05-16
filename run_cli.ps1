$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $true)][string]$InputDocx,
  [Parameter(Mandatory = $false)][string]$OutDir = "out"
)

Set-Location -LiteralPath $PSScriptRoot

$srcPath = Join-Path $PSScriptRoot "src"
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = $srcPath
}

function Find-Python {
  $localVenv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
  $codexPython = "C:\Users\lazar\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

  if (Test-Path -LiteralPath $localVenv) {
    return $localVenv
  }

  if (Test-Path -LiteralPath $codexPython) {
    return $codexPython
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return "py"
  }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return "python"
  }

  throw "Python was not found. Install Python 3.11+ from https://www.python.org/downloads/ and run this script again."
}

$pythonExe = Find-Python

if ($pythonExe -eq "py") {
  $pythonCmd = @("py", "-3")
} else {
  $pythonCmd = @($pythonExe)
}

function Invoke-ProjectPython {
  if ($pythonCmd.Length -gt 1) {
    & $pythonCmd[0] $pythonCmd[1] @args
  } else {
    & $pythonCmd[0] @args
  }
}

Write-Host "Using Python: $($pythonCmd -join ' ')" -ForegroundColor Cyan

Invoke-ProjectPython -c "import fastapi, uvicorn, langgraph, docx, jinja2, requests; import ai_scientific_reviewer" *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing dependencies..." -ForegroundColor Cyan
  Invoke-ProjectPython -m pip install -e .
} else {
  Write-Host "Dependencies already available." -ForegroundColor Cyan
}

if (-not $env:CROSSREF_MAILTO) {
  Write-Host "Tip: set CROSSREF_MAILTO for Crossref polite requests, e.g.:" -ForegroundColor Yellow
  Write-Host '$env:CROSSREF_MAILTO="you@domain.com"' -ForegroundColor Yellow
}

Invoke-ProjectPython -m ai_scientific_reviewer.cli review --input $InputDocx --out $OutDir
