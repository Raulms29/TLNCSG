Set-Location -Path "$PSScriptRoot\..\.."
python -u .\model_eval\model_eval.py 2>&1 | ForEach-Object { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_} | Tee-Object -FilePath model_eval.log -Append
