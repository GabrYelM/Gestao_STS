@echo off
chcp 65001 > nul
title Gestao STS - Servidor
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto ERR_VENV
goto CHECK_FLASK

:ERR_VENV
echo ========================================================
echo   [AVISO] O ambiente virtual Python [.venv] nao foi encontrado!
echo   Por favor, execute o arquivo "instalar.bat" primeiro.
echo ========================================================
echo.
pause
exit /b 1

:CHECK_FLASK
"%~dp0.venv\Scripts\python.exe" -c "import flask" >nul 2>&1
if not errorlevel 1 goto PREPARE_ENV

echo ========================================================
echo   [AVISO] As dependencias do sistema nao estao instaladas!
echo   Por favor, execute o arquivo "instalar.bat" primeiro.
echo ========================================================
echo.
pause
exit /b 1

:PREPARE_ENV
if not exist ".env" (
    if exist ".env.example" copy /y ".env.example" ".env" > nul
)

echo ========================================================
echo             INICIANDO O SISTEMA GESTAO STS
echo ========================================================
echo.
echo [1/3] Encerrando instancias anteriores na porta 5000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [2/3] Iniciando o servidor em segundo plano...
set "RUNNER=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%RUNNER%" set "RUNNER=%~dp0.venv\Scripts\python.exe"
start "" /d "%~dp0" "%RUNNER%" "%~dp0app.py"

echo [3/3] Aguardando o servidor responder...
set "COUNT=0"

:WAIT_LOOP
curl -s -o nul http://localhost:5000
if not errorlevel 1 goto SERVER_READY

ping 127.0.0.1 -n 2 >nul
set /a COUNT+=1
if %COUNT% lss 15 goto WAIT_LOOP

echo.
echo ========================================================
echo   [ERRO] O servidor demorou para responder.
echo   Verifique o arquivo 'server.log' para detalhes.
echo ========================================================
echo.
pause
exit /b 1

:SERVER_READY
echo.
echo ========================================================
echo    SISTEMA INICIADO COM SUCESSO!
echo    Acesse: http://localhost:5000
echo ========================================================
echo.
echo Abrindo o navegador...
start "" "http://localhost:5000"
ping 127.0.0.1 -n 3 >nul
exit
