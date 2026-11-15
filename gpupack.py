"""Accélération carte graphique NVIDIA pour la reconnaissance vocale, dans la version installée de Jimmy.

La version .exe n'embarque pas les bibliothèques CUDA (elles pèsent plusieurs centaines de Mo). Avec l'accord de l'utilisateur,
ce module les télécharge (≈ 1,3 Go) depuis PyPI (paquets officiels nvidia-cublas-cu12 et nvidia-cudnn-cu12, sans pip ni Python) dans
%APPDATA%\\Jimmy\\cuda. Ensuite le modèle le plus précis (large-v3-turbo) tourne sur la carte graphique en moins d'une seconde.
"""
from __future__ import annotations

import json
import os
import urllib.request
import zipfile
from pathlib import Path

from config import data_dir

PACKAGES = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")
UA = {"User-Agent": "Jimmy-gpupack"}


def target_dir() -> Path:
    d = data_dir() / "cuda"
    d.mkdir(parents=True, exist_ok=True)
    return d


def register() -> None:
    """Rend visibles les DLL téléchargées (à appeler avant de charger le modèle vocal)."""
    d = str(target_dir())
    if not any(Path(d).glob("*.dll")):
        return
    try:
        os.add_dll_directory(d)
    except (OSError, AttributeError):
        pass
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def installed() -> bool:
    d = target_dir()
    return (d / "cublas64_12.dll").exists() and any(d.glob("cudnn*64_9.dll"))


def _wheel_url(pkg: str) -> tuple:
    """La version la plus récente QUI A un fichier Windows (la toute dernière n'en a pas toujours)."""
    with urllib.request.urlopen(urllib.request.Request(f"https://pypi.org/pypi/{pkg}/json", headers=UA), timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    best = None
    for ver, files in data["releases"].items():
        wins = [f for f in files if f["filename"].endswith(".whl") and "win_amd64" in f["filename"] and not f.get("yanked")]
        key = tuple(int(x) for x in ver.split(".") if x.isdigit())
        if wins and (best is None or key > best[0]):
            best = (key, wins[0])
    if best is None:
        raise RuntimeError(f"aucun fichier Windows pour {pkg}")
    f = best[1]
    return f["url"], int(f.get("size") or 0), f.get("digests", {}).get("sha256", "")


def download(progress=None) -> None:
    """Télécharge et installe les bibliothèques. progress(texte, pourcentage 0-100). Lève une exception en cas d'échec."""
    import hashlib
    tmp_dir = target_dir() / "_tmp"
    tmp_dir.mkdir(exist_ok=True)
    total_pkgs = len(PACKAGES)
    for idx, pkg in enumerate(PACKAGES):
        url, size, sha = _wheel_url(pkg)
        wheel = tmp_dir / f"{pkg}.whl"
        h = hashlib.sha256()
        got = 0
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r, open(wheel, "wb") as out:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress and size:
                    progress(f"Téléchargement {idx + 1}/{total_pkgs} : {pkg.replace('nvidia-', '').replace('-cu12', '')} "
                             f"({got // 1_000_000} / {size // 1_000_000} Mo)", int((idx + got / size) * 100 / total_pkgs))
        if sha and h.hexdigest() != sha:
            wheel.unlink(missing_ok=True)
            raise RuntimeError(f"fichier corrompu : {pkg} (empreinte différente)")
        with zipfile.ZipFile(wheel) as z:
            for name in z.namelist():
                if name.lower().endswith(".dll") and "/bin/" in name.replace("\\", "/"):
                    (target_dir() / Path(name).name).write_bytes(z.read(name))
        wheel.unlink(missing_ok=True)
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
    register()
    if progress:
        progress("Accélération carte graphique installée.", 100)


def remove() -> None:
    for f in target_dir().glob("*.dll"):
        try:
            f.unlink()
        except OSError:
            pass
