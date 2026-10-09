@echo off
setlocal
pushd "%~dp0.."
if errorlevel 1 exit /b 1
where uv >nul 2>nul
if errorlevel 1 (
    echo uv requis : https://docs.astral.sh/uv/getting-started/installation/
    goto :failed
)
set "UV_PYTHON_INSTALL_DIR=%CD%\local\runtime"
uv python install 3.13 --no-bin --no-registry
if errorlevel 1 goto :failed
if not exist "local\.venv\Scripts\python.exe" (
    uv venv --python 3.13 --managed-python local/.venv
    if errorlevel 1 goto :failed
)
uv pip sync --python local/.venv/Scripts/python.exe requirements.txt
if errorlevel 1 goto :failed
echo Environnement pret. Decouverte : local/.venv/Scripts/python.exe scripts/discover.py
popd
exit /b 0
:failed
popd
exit /b 1
