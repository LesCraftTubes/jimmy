"""Lanceur de Jimmy : petit .exe à poser sur le bureau, qui démarre l'appli avec son environnement Python."""
import os
import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    Path(sys.executable).resolve().parent / "jarvis",
    Path.home() / "Desktop" / "jarvis",
    Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop" / "jarvis",
]


def _venv_ok(folder: Path) -> bool:
    """L'environnement Python existe et pointe vers un Python présent sur CE PC."""
    pyw = folder / ".venv" / "Scripts" / "pythonw.exe"
    cfg = folder / ".venv" / "pyvenv.cfg"
    if not (pyw.exists() and cfg.exists()):
        return False
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("home"):
            return Path(line.split("=", 1)[1].strip()).exists()
    return True


def main() -> int:
    for folder in CANDIDATES:
        if not (folder / "main.py").exists():
            continue
        if not _venv_ok(folder) and (folder / "install.bat").exists():
            # Premier lancement sur ce PC : installation automatique des dépendances.
            subprocess.call(
                ["cmd", "/c", str(folder / "install.bat")],
                cwd=str(folder),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        if _venv_ok(folder):
            pyw = folder / ".venv" / "Scripts" / "pythonw.exe"
            subprocess.Popen([str(pyw), str(folder / "main.py")], cwd=str(folder))
            return 0
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        None, "Dossier de Jimmy introuvable (Bureau\\jarvis).", "Jimmy", 0x10
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
