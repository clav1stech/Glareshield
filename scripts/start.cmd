@echo off
setlocal
pushd "%~dp0.."
if not exist "local\.venv\Scripts\pythonw.exe" (
    echo Environnement absent : installation en cours.
    call "%~dp0setup.cmd"
    if errorlevel 1 goto :failed
)
set "PYTHONPATH=%CD%\src"
start "" "local\.venv\Scripts\pythonw.exe" -m glareshield.app
popd
exit /b 0
:failed
echo Echec du lancement de Glareshield.
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
popd
exit /b 1
