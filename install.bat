@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
rem Recrée l'environnement seulement s'il est absent ou copié d'un autre PC (inutilisable ici).
.venv\Scripts\python.exe -c "pass" >nul 2>nul || python -m venv --clear .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Installation terminee. Lance run.bat
goto end
:nopython
echo Python est introuvable. Installe Python 3.11 ou 3.12 depuis python.org et coche Add Python to PATH.
:end
pause
