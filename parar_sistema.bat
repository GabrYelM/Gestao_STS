@echo off
chcp 65001 > nul
title Gestao STS - Encerrar Servidor
cd /d "%~dp0"

echo Encerrando o servidor Gestao STS...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo ========================================================
echo       SISTEMA GESTAO STS ENCERRADO COM SUCESSO!
echo ========================================================
echo.
ping 127.0.0.1 -n 3 >nul
exit
