Set-Location -Path "$PSScriptRoot\..\.."
python -u -m query_eval.query_eval 2>&1 | ForEach-Object { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_} | Tee-Object -FilePath query_eval.log -Append
