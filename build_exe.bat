@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name Jimmy ^
 --collect-all faster_whisper --collect-all ctranslate2 --collect-all av ^
 --collect-all onnxruntime --collect-all tokenizers --collect-all edge_tts --collect-all piper ^
 --collect-all _sounddevice_data main.py
echo.
echo Termine : dist\Jimmy\Jimmy.exe
pause
