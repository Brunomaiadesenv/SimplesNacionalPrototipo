@echo off
REM Execucao no Windows. 1a vez: cria o ambiente e instala as dependencias (offline pela pasta "pacotes"; se falhar, tenta pela internet).
cd /d %~dp0
if exist .venv\Scripts\python.exe goto pronto

if exist .venv rmdir /s /q .venv
py -m venv .venv
if errorlevel 1 goto sempython

echo Instalando dependencias a partir da pasta "pacotes" (sem internet)...
.venv\Scripts\python -m pip install --no-index --find-links pacotes\cp311 --find-links pacotes\cp312 --find-links pacotes\cp313 -r requirements.txt
if not errorlevel 1 goto pronto

echo.
echo Instalacao offline nao funcionou. Tentando pela internet...
.venv\Scripts\python -m pip install -r requirements.txt
if not errorlevel 1 goto pronto

echo.
echo Falha na instalacao das dependencias. Informe a versao do Python (py --version) e veja o README, secao "Instalacao sem internet".
rmdir /s /q .venv
pause
exit /b 1

:sempython
echo Python nao encontrado. Instale o Python 3.11 ou superior (64 bits) e marque "Add python.exe to PATH".
pause
exit /b 1

:pronto
if not exist .env copy .env.example .env >nul
if not exist demo.db .venv\Scripts\python criar_demo.py
echo.
echo Sistema em http://127.0.0.1:8000  - feche esta janela para encerrar.
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
