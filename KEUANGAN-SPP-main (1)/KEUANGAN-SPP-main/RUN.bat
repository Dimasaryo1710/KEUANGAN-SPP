@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe app.py
pause
exit /b
:fail
echo Gagal menyiapkan aplikasi. Pastikan Python 3.10+ terpasang dan internet aktif.
pause
