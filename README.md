# Gestão STS - Automação e Analytics 🚀

Este projeto é uma plataforma completa de Engenharia e Análise de Dados focada na automação da coleta, tratamento (ETL), armazenamento e geração de relatórios dinâmicos sobre a produção da região (STS). 

Desenvolvido para rodar localmente como uma aplicação web robusta, o sistema elimina o trabalho manual e repetitivo de lidar com planilhas gigantes, servindo como a "fonte única de verdade" (*Single Source of Truth*) para a equipe.

---

## ⚡ Guia Rápido: Como Baixar e Rodar em Outra Máquina (Instalação 100% Automática)

O instalador foi preparado para fazer **tudo de forma automática**, inclusive baixar e instalar o Python se a máquina não tiver!

### 1️⃣ Baixar o Projeto
- **Opção A (Arquivo ZIP):** Baixe o `.zip` do repositório e extraia na pasta desejada (ex: `C:\Projetos\Gestao_STS`).
- **Opção B (Git):** Abra o terminal e clone o repositório:
  ```bash
  git clone https://github.com/SEU-USUARIO/Gestao_STS.git
  cd Gestao_STS
  ```

---

### 2️⃣ Instalação Automática em 1 Clique
1. Dê dois cliques no arquivo **`instalar.bat`** na pasta do projeto.
2. O script cuidará de tudo sozinho:
   - 🐍 **Se a máquina não tiver Python:** Ele baixa o instalador oficial do Python e instala silenciosamente configurando o PATH.
   - 📦 Cria o ambiente virtual isolado (`.venv`).
   - 📚 Baixa e instala todas as bibliotecas necessárias (`requirements.txt`).
   - 🌐 Instala o navegador para os robôs (`Playwright / Chromium`).
   - 🗄️ Inicializa o banco de dados e os usuários padrão.

---

### 3️⃣ Iniciar e Parar o Sistema
- **Para Iniciar:** Dê dois cliques no arquivo **`iniciar.bat`**.
  - O sistema inicia **silenciosamente em segundo plano** (a janela preta do CMD fecha automaticamente).
  - O navegador abre direto no sistema: 👉 **`http://localhost:5000`**.
- **Para Encerrar:** Dê dois cliques no arquivo **`parar_sistema.bat`**.

---

## 🌐 Compartilhar Acesso com Outros Computadores (Rede Local / Intranet)

Para que qualquer colega conectado à mesma rede ou servidor acesse o sistema:
1. Abra o sistema no seu navegador.
2. Clique no botão **`🌐 Link da Rede`** (no topo direito) ou use o botão **`📋 Copiar Link`** na página inicial.
3. Envie o link gerado (ex: `http://172.17.174.87:5000`) para a outra pessoa. Ela abrirá direto no navegador sem precisar instalar nada!

---

## 🔑 Credenciais Padrão de Acesso

O acesso aos relatórios de produção é **livre para consulta e exportação**. O login é necessário apenas para gestores atualizarem dados e rodarem robôs:

| Perfil | Usuário | Senha Padrão | Permissões |
|---|---|---|---|
| **Administrador** | `admin` | `admin` | Acesso total (Uploads, Automações, Cadastros e Relatórios) |
| **Visualizador** | `normal` | `normal` | Acesso de consulta e visualização aos relatórios |

> 💡 *As senhas e novos usuários podem ser gerenciados após o primeiro login.*

---

## 🏗️ Arquitetura do Projeto

O sistema divide as responsabilidades em camadas lógicas claras:

1. **Camada de Extração (`services/bot.py`):** 
   - Utiliza **Playwright** (Web Scraping / Automação) para acessar o portal silenciosamente.
   - Navega, preenche formulários de datas e faz o download automático de dezenas de relatórios pesados simultaneamente (usando sistema de filas/threads).
   
2. **Camada de Tratamento / ETL (`services/etl.py`):**
   - Utiliza **Pandas** para processamento pesado de dados.
   - Remove cabeçalhos e formatações desnecessárias.
   - Padroniza colunas e cataloga procedimentos, CBOs e profissionais.
   - Aplica lógica idempotente (*Delete & Replace*) para impedir a duplicação de dados históricos no banco.

3. **Camada de Armazenamento (`database.db` & `models.py`):**
   - Banco de dados relacional (SQLite) centralizado, armazenando registros históricos (AT-02, AT-03, VG-02, REL-10, RAAS, etc.).
   - Estrutura modelada e mapeada usando **SQLAlchemy ORM**.

4. **Camada de Analytics / Produção (`services/producao.py`):**
   - Motor de tabelas dinâmicas *on-the-fly*.
   - Cruza e resume as tabelas brutas do banco de dados usando agregações do **Pandas (`pivot_table`, `groupby`)**.
   - Reproduz fielmente os layouts e índices dos relatórios de produção exigidos pela gestão, com suporte a exportação em Excel.

5. **Catálogo Geral Unificado (`services/catalogo_geral.json`):**
   - Base nacional completa de CBOs oficiais (2.742 ocupações), SIGTAP/Procedimentos SUS e Unidades de Saúde (CNES).

---

## 🔒 Privacidade e Segurança de Dados (LGPD)

Por motivos de segurança e em estrita conformidade com a LGPD (Lei Geral de Proteção de Dados), **nenhum dado real, relatório original ou banco de dados sensível está presente neste repositório**. 

Toda a carga, manipulação e armazenamento ocorre **exclusivamente no ambiente local do servidor da unidade**. O Git ignora completamente arquivos brutos e bancos de dados (`.db`), garantindo sigilo absoluto das informações.

---
*Projeto em constante evolução - Equipe de Automação e Gestão STS.*
