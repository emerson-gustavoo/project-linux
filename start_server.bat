@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Criando venv...
  py -m venv venv
)
call "venv\Scripts\activate"
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload
endlocal
