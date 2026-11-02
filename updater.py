"""Mises à jour automatiques : Jimmy regarde les « Releases » du dépôt GitHub configuré (update_repo)
et, avec ton accord, télécharge puis lance le nouvel installateur.

Fonctionnement côté publication : à chaque version publiée (tag vX.Y.Z), GitHub Actions construit
Jimmy-Setup-X.Y.Z.exe et l'attache à la release (voir .github/workflows/release.yml et release.ps1).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from version import __version__


@dataclass
class Update:
    version: str
    url: str          # adresse de l'installateur (.exe)
    notes: str
    size: int


def _vtuple(v: str) -> tuple:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _vtuple(remote) > _vtuple(local)


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "Jimmy-updater", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def check(repo: str) -> Update | None:
    """Renvoie la mise à jour disponible, ou None (à jour, hors ligne, dépôt introuvable...)."""
    repo = (repo or "").strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return None
    try:
        with _get(f"https://api.github.com/repos/{repo}/releases/latest") as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    tag = str(data.get("tag_name", "")).lstrip("vV")
    if not tag or not is_newer(tag):
        return None
    for a in data.get("assets", []):
        name = str(a.get("name", ""))
        if name.lower().endswith(".exe") and "setup" in name.lower():
            return Update(tag, str(a.get("browser_download_url", "")), str(data.get("body", ""))[:600], int(a.get("size", 0)))
    return None


def download(update: Update, progress=None) -> Path:
    """Télécharge l'installateur dans le dossier temporaire. progress(octets_lus, total)."""
    dest = Path(tempfile.gettempdir()) / f"Jimmy-Setup-{update.version}.exe"
    part = dest.with_suffix(".part")
    with _get(update.url, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or update.size or 0)
        done = 0
        while True:
            chunk = r.read(1 << 17)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    part.replace(dest)
    return dest


def run_installer(path: Path) -> None:
    """Lance l'installateur en mode discret : il ferme Jimmy, met à jour, puis le relance."""
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    subprocess.Popen([str(path), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NOCANCEL"],
                     creationflags=flags, close_fds=True)


def can_self_update() -> bool:
    """Seule une version installée (.exe) peut se mettre à jour toute seule."""
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"
