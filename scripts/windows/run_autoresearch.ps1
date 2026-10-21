#
# .\scripts\windows\run_autoresearch.ps1 run
# .\scripts\windows\run_autoresearch.ps1 reset
#
# Each run writes its log to autoresearch/archive/run_<timestamp>/autoresearch.log.

$Command = $args[0]
$Rest = @($args | Select-Object -Skip 1)

if (-not $Command) {
  Write-Host "Usage: $($MyInvocation.MyCommand.Name) <command> [args...]"
  Write-Host "Commands: run, reset"
  exit 1
}

$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Invoke-Container($PythonCommand) {
  docker run --rm `
    --name autoresearch `
    -v "${Project}:/opt/project" `
    -w /opt/project `
    virtualuser/tlncsg:latest `
    bash -c "$PythonCommand `"`$@`"" _ @Rest
}

switch ($Command) {
  "run"   { Invoke-Container "python3 -u -m autoresearch.main" }
  "reset" { Invoke-Container "python3 -u -m autoresearch.main --reset" }
  default {
    Write-Host "Unknown command: $Command"
    Write-Host "Commands: run, reset"
    exit 1
  }
}

exit $LASTEXITCODE
