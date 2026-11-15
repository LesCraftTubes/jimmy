"""Analyse du PC pour savoir s'il peut faire tourner une IA locale, et laquelle.

Tout est lu sur place (nvidia-smi, Windows) : aucune donnée n'est envoyée nulle part.
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path

NOWIN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Profils : (clé, nom affiché, modèle conseillé, taille approximative en Go, explication)
PROFILES = {
    "none": ("Aucun", "", 0.0,
             "Ce PC est trop juste pour une IA locale agréable. Jimmy fonctionne très bien sans (Claude seul)."),
    "light": ("Léger", "qwen2.5-coder-3b-instruct", 2.0,
              "Petit modèle : aiguillage des commandes simples et résumés courts. Lent sans carte graphique."),
    "standard": ("Standard", "qwen2.5-coder-7b-instruct", 4.7,
                 "Modèle de 7 milliards de paramètres : résumés, recherche, petits scripts. Compatible avec un jeu lancé à côté."),
    "comfort": ("Confort", "qwen2.5-coder-14b-instruct", 9.0,
                "Modèle de 14 milliards de paramètres : meilleur code. Occupe presque toute la carte graphique (pas en jouant)."),
}


def _run(cmd: list, timeout: float = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NOWIN,
                           encoding="utf-8", errors="replace")
        return r.stdout or ""
    except Exception:  # noqa: BLE001
        return ""


def _ram_gb() -> float:
    if os.name == "nt":
        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        try:
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1024 ** 3
        except Exception:  # noqa: BLE001
            return 0.0
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (ValueError, OSError, AttributeError):
        return 0.0


def _gpus() -> list:
    """[(nom, mémoire vidéo en Go)] : NVIDIA par nvidia-smi (fiable), sinon ce que Windows déclare (approximatif)."""
    out = []
    smi = shutil.which("nvidia-smi")
    if smi:
        for line in _run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]).splitlines():
            name, _, mem = line.rpartition(",")
            try:
                out.append((name.strip(), float(mem) / 1024))
            except ValueError:
                pass
    if not out and os.name == "nt":
        # Registre : qwMemorySize est juste même au-delà de 4 Go (AdapterRAM de WMI ne l'est pas).
        ps = ("Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' "
              "-ErrorAction SilentlyContinue | ForEach-Object { \"$($_.DriverDesc)|$($_.'HardwareInformation.qwMemorySize')\" }")
        for line in _run(["powershell", "-NoProfile", "-Command", ps], 20).splitlines():
            name, _, mem = line.partition("|")
            try:
                gb = float(mem) / 1024 ** 3
            except ValueError:
                continue
            if name.strip() and gb >= 1:
                out.append((name.strip(), gb))
    return out


def survey(path: str = "") -> dict:
    """État du PC : carte graphique, mémoire vidéo, RAM, disque libre, processeur."""
    gpus = _gpus()
    best = max(gpus, key=lambda g: g[1]) if gpus else ("", 0.0)
    try:
        free = shutil.disk_usage(path or str(Path.home())).free / 1024 ** 3
    except OSError:
        free = 0.0
    return {
        "gpu": best[0], "vram_gb": round(best[1], 1), "gpus": gpus,
        "ram_gb": round(_ram_gb(), 1), "disk_free_gb": round(free, 1),
        "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count() or 0,
        "system": f"{platform.system()} {platform.release()}",
    }


def profile(s: dict) -> str:
    """Clé du profil conseillé (none, light, standard, comfort)."""
    vram, ram, disk = s.get("vram_gb", 0), s.get("ram_gb", 0), s.get("disk_free_gb", 0)
    if ram < 7.5 or disk < 6:
        return "none"
    if vram >= 11.5 and ram >= 15 and disk >= 14:
        return "comfort"
    if vram >= 7.5 or (ram >= 15.5 and vram >= 5.5):
        return "standard" if disk >= 8 else "light"
    if vram >= 3.5 or ram >= 15.5:
        return "light"
    return "none"


def describe(s: dict) -> str:
    """Phrase lisible : « RTX 4070 SUPER 12 Go, 31 Go de RAM, 70 Go libres »."""
    gpu = f"{s['gpu']} {s['vram_gb']:g} Go" if s.get("gpu") else "pas de carte graphique dédiée détectée"
    return f"{gpu}, {s.get('ram_gb', 0):g} Go de RAM, {s.get('disk_free_gb', 0):g} Go libres sur le disque"


def recommendation(s: dict = None) -> dict:
    s = s or survey()
    key = profile(s)
    name, model, size, why = PROFILES[key]
    return {"profile": key, "name": name, "model": model, "size_gb": size, "why": why,
            "pc": describe(s), "survey": s}
