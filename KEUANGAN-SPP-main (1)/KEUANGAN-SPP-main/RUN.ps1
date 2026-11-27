Set-Location $PSScriptRoot
if (!(Test-Path ".venv/Scripts/python.exe")) { python -m venv .venv }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ./.venv/Scripts/python.exe app.py
