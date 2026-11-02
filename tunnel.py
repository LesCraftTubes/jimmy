"""Tunnel Internet gratuit (Cloudflare « quick tunnel ») pour joindre Jimmy depuis le téléphone hors du Wi-Fi.

Aucun compte nécessaire. `cloudflared` (programme officiel de Cloudflare) est téléchargé à la demande dans le
dossier de données de Jimmy, puis lancé vers le serveur local. Il donne une adresse https://xxxx.trycloudflare.com
qui change à chaque démarrage : il faut alors re-scanner le QR code (ou utiliser le mode « adresse perso »
avec Tailscale / ton propre domaine pour une adresse fixe).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from config import data_dir

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
DOWNLOAD = {
    "win32": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "linux": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    "darwin": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
}


def binary_path() -> Path:
    name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    return data_dir() / name


class Tunnel:
    def __init__(self, on_change=None):
        self.url = ""
        self.status = "arrêté"      # arrêté | téléchargement | démarrage | prêt | erreur
        self.error = ""
        self.on_change = on_change
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _set(self, status: str, error: str = "", url: str | None = None) -> None:
        self.status, self.error = status, error
        if url is not None:
            self.url = url
        if self.on_change:
            self.on_change()

    # ---------------------------------------------------------------- binaire
    def _ensure_binary(self) -> bool:
        exe = binary_path()
        if exe.exists() and exe.stat().st_size > 1_000_000:
            return True
        url = DOWNLOAD.get(sys.platform)
        if not url or url.endswith(".tgz"):
            self._set("erreur", "Téléchargement automatique non géré sur ce système : installe cloudflared à la main.")
            return False
        self._set("téléchargement")
        tmp = exe.with_suffix(".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jimmy"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(exe)
            if os.name != "nt":
                exe.chmod(0o755)
            return True
        except Exception as e:  # noqa: BLE001
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._set("erreur", f"Téléchargement de cloudflared impossible : {e}")
            return False

    # ------------------------------------------------------------- démarrage
    def start(self, port: int) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(port,), daemon=True, name="jimmy-tunnel")
        self._thread.start()

    def _run(self, port: int) -> None:
        if not self._ensure_binary():
            return
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        while not self._stop.is_set():
            self._set("démarrage", url="")
            try:
                self._proc = subprocess.Popen(
                    [str(binary_path()), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", creationflags=flags,
                )
            except OSError as e:
                self._set("erreur", f"Impossible de lancer cloudflared : {e}")
                return
            for line in self._proc.stdout:
                m = URL_RE.search(line)
                if m and not self.url:
                    self._set("prêt", url=m.group(0))
                if self._stop.is_set():
                    break
            self._proc.wait()
            if self._stop.is_set():
                break
            self._set("démarrage", "Le tunnel s'est coupé, nouvelle tentative…", url="")
            self._stop.wait(5)
        self._set("arrêté", url="")

    def stop(self) -> None:
        self._stop.set()
        p = self._proc
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        self.url = ""
