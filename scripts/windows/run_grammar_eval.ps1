Set-Location -Path "$PSScriptRoot\..\.."
python -u -m grammar_eval.grammar_eval 2>&1 | ForEach-Object { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_} | Tee-Object -FilePath grammar_eval.log -Append
