@echo off
chcp 65001 > nul
title Gestao STS - Servidor

if not exist ".venv" (
    echo [AVISO] O ambiente virtual nao foi encontrado!
    echo Execute primeiro o arquivo "instalar.bat".
    echo.
    pause
    exit /b 1
)

:: Encerra qualquer instancia anterior na porta 5000 para evitar conflito
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Inicia o servidor Python em segundo plano (silencioso / sem janela preta)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"

:: Abre o navegador automaticamente
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5000"

:: Fecha a janela do CMD imediatamente
exit
