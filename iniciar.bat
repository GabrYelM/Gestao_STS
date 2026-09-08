@echo off
chcp 65001 > nul
title Gestao STS - Servidor Local

echo ========================================================
echo           INICIANDO SISTEMA GESTAO STS...
echo ========================================================
echo.

if not exist ".venv" (
    echo [AVISO] O ambiente virtual nao foi encontrado!
    echo Execute primeiro o arquivo "instalar.bat".
    echo.
    pause
    exit /b 1
)

:: Ativa o ambiente virtual
call .venv\Scripts\activate.bat

:: Abre o navegador automaticamente apos 2 segundos
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5000"

echo Servidor rodando em http://localhost:5000
echo Pressione Ctrl+C na janela para encerrar o sistema.
echo.

python app.py
