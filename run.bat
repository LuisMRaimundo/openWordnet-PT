@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado no PATH.
    pause
    exit /b 1
)

echo A abrir a consulta local do OpenWordnet-PT...
python consult_ownpt.py %*
if errorlevel 1 pause
endlocal
