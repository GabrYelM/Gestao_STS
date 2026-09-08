@echo off
chcp 65001 > nul
title Gestao STS - Instalacao e Configuracao Automatica

echo ========================================================
echo       GESTAO STS - INSTALACAO AUTOMATICA DO SISTEMA
echo ========================================================
echo.

:: 1. Verifica se Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    :: Tenta encontrar nos caminhos padroes caso o PATH ainda nao esteja atualizado
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    ) else if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "PATH=%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%PATH%"
    ) else if exist "C:\Program Files\Python312\python.exe" (
        set "PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
    ) else if exist "C:\Program Files\Python311\python.exe" (
        set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%PATH%"
    )
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [AVISO] Python nao foi encontrado nesta maquina.
    echo [INFO] Baixando e instalando o Python 3.12 automaticamente...
    echo.

    :: Baixa o instalador oficial do Python 3.12 usando PowerShell
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host 'Baixando instalador oficial do Python...'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile 'python_installer.exe'"
    
    if not exist "python_installer.exe" (
        echo [ERRO] Falha no download automatico do Python.
        echo Por favor, baixe e instale manualmente em: https://www.python.org/downloads/
        echo (Lembre-se de marcar 'Add python.exe to PATH')
        pause
        exit /b 1
    )

    echo Instalando Python 3.12 com configuracao automatica de PATH...
    :: Executa a instalacao silenciosa adicionando ao PATH
    start /wait python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
    
    :: Remove o instalador temporario
    del /f /q python_installer.exe >nul 2>&1

    :: Atualiza o PATH da sessao atual
    set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"

    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [INFO] Python instalado com sucesso!
        echo Para que o Windows atualize todos os atalhos, por favor feche e abra o 'instalar.bat' novamente.
        echo.
        pause
        exit /b 0
    )
)

echo [1/5] Python detectado com sucesso:
python --version

:: 2. Cria o ambiente virtual se nao existir
if not exist ".venv" (
    echo.
    echo [2/5] Criando ambiente virtual isolado (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
) else (
    echo.
    echo [2/5] Ambiente virtual (.venv) ja existe.
)

:: 3. Ativa o ambiente virtual e instala dependencias
echo.
echo [3/5] Instalando bibliotecas necessarias (requirements.txt)...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao com a internet.
    pause
    exit /b 1
)

:: 4. Instala os navegadores necessarios para os robos (Playwright)
echo.
echo [4/5] Instalando navegador para automacoes (Chromium)...
playwright install chromium

:: 5. Configura arquivo .env se necessario e inicializa o banco
echo.
echo [5/5] Inicializando configuracoes e banco de dados...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env > nul
        echo      Arquivo .env criado a partir de .env.example.
    )
)

python -c "import app; print('     Banco de dados e credenciais verificados com sucesso!')"

echo.
echo ========================================================
echo        INSTALACAO CONCLUIDA COM SUCESSO!
echo ========================================================
echo.
echo  Credenciais padrao de acesso:
echo    Usuario: admin
echo    Senha:   admin
echo.
echo  Para iniciar o sistema, dê dois cliques em:
echo    -> iniciar.bat
echo.
pause
