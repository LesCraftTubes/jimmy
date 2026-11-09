# -*- mode: python ; coding: utf-8 -*-
# Construit Jimmy.exe (dossier dist/Jimmy) : pyinstaller jimmy.spec --noconfirm --clean
import re
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

# Informations de version affichées dans les propriétés du .exe (un programme sans identité est davantage suspecté par les antivirus).
_ver = re.search(r'__version__ = "([^"]+)"', open("version.py", encoding="utf-8").read()).group(1)
_n = ([int(x) for x in _ver.split(".")] + [0, 0, 0, 0])[:4]
_vi = VSVersionInfo(
    ffi=FixedFileInfo(filevers=tuple(_n), prodvers=tuple(_n), mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040C04B0", [
            StringStruct("CompanyName", "Jimmy contributors"),
            StringStruct("FileDescription", "Jimmy, assistant vocal pour Claude Code"),
            StringStruct("FileVersion", _ver),
            StringStruct("InternalName", "Jimmy"),
            StringStruct("LegalCopyright", "MIT License"),
            StringStruct("OriginalFilename", "Jimmy.exe"),
            StringStruct("ProductName", "Jimmy"),
            StringStruct("ProductVersion", _ver),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)
open("build_version_info.txt", "w", encoding="utf-8").write(str(_vi))

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers", "edge_tts", "piper",
            "_sounddevice_data", "pygame", "segno", "aiohttp"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [("mobile", "mobile"), ("jimmy.ico", ".")]
hiddenimports += ["jimmy_mem", "sessions", "PySide6.QtNetwork", "pyttsx3.drivers", "pyttsx3.drivers.sapi5"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "pywinauto"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Jimmy", console=False, icon="jimmy.ico",
          version="build_version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="Jimmy")
