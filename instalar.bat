@echo off
chcp 65001 > nul
title Gestao STS - Instalacao e Configuracao Automatica
cd /d "%~dp0"

echo ========================================================
echo       GESTAO STS - INSTALACAO AUTOMATICA DO SISTEMA
echo ========================================================
echo.

set "PYTHON_CMD="

REM 1. Verifica se Python esta disponivel diretamente no PATH
python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto PYTHON_FOUND
)

REM 2. Verifica se o Python Launcher (py.exe) esta disponivel
py -3 -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto PYTHON_FOUND
)

REM 3. Verifica diretorios padroes de instalacao do Python
for %%p in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%LocalAppData%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%p (
        %%p -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=%%~p"
            set "PATH=%%~dpp;%%~dppScripts;%PATH%"
            goto PYTHON_FOUND
        )
    )
)

REM 4. Se chegou aqui, Python nao foi encontrado. Baixa e instala o Python oficial.
echo [AVISO] Python 3 nao foi encontrado nesta maquina.
echo [INFO] Baixando instalador oficial do Python 3.12...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe', 'python_installer.exe')"

if not exist "python_installer.exe" (
    echo [ERRO] Falha no download automatico do Python.
    echo Por favor, baixe e instale manualmente em: https://www.python.org/downloads/
    echo Certifique-se de marcar a opcao 'Add python.exe to PATH'.
    pause
    exit /b 1
)

echo Instalando Python 3.12... Aguarde a conclusao.
start /wait python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
del /f /q python_installer.exe >nul 2>&1

set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto PYTHON_FOUND
)

python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto PYTHON_FOUND
)

echo [ERRO] A instalacao do Python nao pode ser validada.
echo Por favor, instale o Python manualmente em: https://www.python.org/downloads/
echo Lembre-se de marcar a opcao 'Add python.exe to PATH'.
pause
exit /b 1

:PYTHON_FOUND
echo [1/5] Python detectado com sucesso:
%PYTHON_CMD% --version
if errorlevel 1 (
    echo [ERRO] Falha ao testar o Python detectado.
    pause
    exit /b 1
)

REM 5. Cria o ambiente virtual (.venv) se nao existir
echo.
if exist ".venv\Scripts\python.exe" goto VENV_EXISTS

echo [2/5] Criando ambiente virtual isolado [.venv]...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERRO] Falha ao criar o ambiente virtual.
    pause
    exit /b 1
)
echo      Ambiente virtual criado com sucesso.
goto VENV_DONE

:VENV_EXISTS
echo [2/5] Ambiente virtual [.venv] ja existe.

:VENV_DONE

REM 6. Atualiza pip e instala dependencias do requirements.txt
echo.
echo [3/5] Instalando bibliotecas necessarias [requirements.txt]...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao com a internet.
    pause
    exit /b 1
)
echo      Dependencias instaladas com sucesso.

REM 7. Instala os navegadores necessarios para os robos (Playwright)
echo.
echo [4/5] Configurando navegador para automacoes [Chromium]...
"%~dp0.venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo [AVISO] Ocorreu um aviso na instalacao do Chromium do Playwright.
) else (
    echo      Navegador Chromium verificado com sucesso.
)

REM 8. Configura arquivo .env se necessario e inicializa o banco
echo.
echo [5/5] Inicializando configuracoes e banco de dados...
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" > nul
        echo      Arquivo .env criado a partir de .env.example.
    )
)

"%~dp0.venv\Scripts\python.exe" -c "import app; print('     Banco de dados e credenciais verificados com sucesso!')"
if errorlevel 1 (
    echo [ERRO] Falha ao inicializar o banco de dados.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo        INSTALACAO CONCLUIDA COM SUCESSO!
echo ========================================================
echo.
echo  Credenciais padrao de acesso:
echo    Usuario: admin
echo    Senha:   admin
echo.
echo  Para iniciar o sistema, de dois cliques em:
echo    -^> iniciar.bat
echo.
pause
