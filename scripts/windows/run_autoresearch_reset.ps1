Set-Location -Path "$PSScriptRoot\..\.."
python -u .\autoresearch\main.py --reset 2>&1 | ForEach-Object { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_} | Tee-Object -FilePath autoresearch.log
