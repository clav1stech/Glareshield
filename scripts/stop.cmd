@echo off
setlocal
pushd "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$venv = (Join-Path $PWD 'local\.venv\Scripts').ToLower();" ^
  "$n = 0;" ^
  "Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object {" ^
  "  $_.CommandLine -and $_.CommandLine -match 'glareshield\.app' -and $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($venv)" ^
  "} | ForEach-Object {" ^
  "  Write-Host ('Arret du processus ' + $_.ProcessId);" ^
  "  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++" ^
  "};" ^
  "if ($n -eq 0) { Write-Host 'Aucun processus Glareshield en cours.' }"
popd
