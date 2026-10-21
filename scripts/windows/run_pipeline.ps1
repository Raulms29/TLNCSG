#
# .\scripts\windows\run_pipeline.ps1 execution
# .\scripts\windows\run_pipeline.ps1 execution --resume-dir outputs/execution/101026_101026_0001
# .\scripts\windows\run_pipeline.ps1 grouping --execution-dir outputs/execution/300926_300926_0001
# .\scripts\windows\run_pipeline.ps1 evaluation --grouping-dir outputs/grouping/011026_011026_0001
# .\scripts\windows\run_pipeline.ps1 review
# .\scripts\windows\run_pipeline.ps1 metrics --run-dir outputs/review/011026_011026_0001

$Module = $args[0]
$Rest = @($args | Select-Object -Skip 1)

if (-not $Module) {
  Write-Host "Usage: $($MyInvocation.MyCommand.Name) <module> [args...]"
  Write-Host "Modules: execution, grouping, evaluation, review, metrics"
  exit 1
}

$Project = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Invoke-Container($Name, $Command, $DockerArgs = @()) {
  docker run --rm `
    --name $Name `
    @DockerArgs `
    -v "${Project}:/opt/project" `
    -w /opt/project `
    virtualuser/tlncsg:latest `
    bash -c "$Command `"`$@`"" _ @Rest
}

switch ($Module) {
  "execution"  { Invoke-Container execution "python3 -u -m pipeline.execution.main --config execution_config.json" }
  "grouping"   { Invoke-Container grouping "python3 -u -m pipeline.grouping.main --config grouping_config.json" }
  "evaluation" { Invoke-Container evaluation "python3 -u -m pipeline.evaluation.main --config evaluation_config.json" }
  "review"     { Invoke-Container review "python3 -m streamlit run pipeline/review/app.py" @("-p", "8501:8501") }
  "metrics"    { Invoke-Container metrics "python3 -u -m pipeline.metrics.main --config metrics_config.json" }
  default {
    Write-Host "Unknown module: $Module"
    Write-Host "Modules: execution, grouping, evaluation, review, metrics"
    exit 1
  }
}

exit $LASTEXITCODE
