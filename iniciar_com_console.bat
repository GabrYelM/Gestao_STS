@echo off
chcp 65001 > nul
title Gestao STS - Servidor (Modo Console / Diagnostico)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [AVISO] O ambiente virtual nao foi encontrado!
    echo Execute primeiro o arquivo "instalar.bat".
    echo.
    pause
    exit /b 1
)

:: Encerra instancias anteriores na porta 5000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

if not exist ".env" (
    if exist ".env.example" copy /y ".env.example" ".env" > nul
)

echo ========================================================
echo       GESTAO STS - SERVIDOR COM CONSOLE ATIVO
echo ========================================================
echo.
echo Servidor iniciando na porta 5000...
echo Pressione Ctrl+C para encerrar o sistema.
echo.

:: Abre o navegador em segundo plano apos aguardar
start "" cmd /c "ping 127.0.0.1 -n 3 >nul & start http://localhost:5000"

"%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
pause
