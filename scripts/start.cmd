@echo off
setlocal
pushd "%~dp0.."
if not exist "local\.venv\Scripts\pythonw.exe" (
    echo Executer scripts\setup.cmd avant le lancement.
    popd
    exit /b 1
)
if not exist "local\config.yaml" (
    echo Configuration locale requise : voir README.md.
    popd
    exit /b 1
)
set "PYTHONPATH=%CD%\src"
start "" "local\.venv\Scripts\pythonw.exe" -m glareshield.app
popd
