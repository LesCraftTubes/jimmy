"""Tunnel Internet gratuit (Cloudflare « quick tunnel ») pour joindre Jimmy depuis le téléphone hors du Wi-Fi.

Aucun compte nécessaire. `cloudflared` (programme officiel de Cloudflare) est téléchargé à la demande dans le
dossier de données de Jimmy, puis lancé vers le serveur local. Il donne une adresse https://xxxx.trycloudflare.com
qui change à chaque démarrage : il faut alors re-scanner le QR code (ou utiliser le mode « adresse perso »
avec Tailscale / ton propre domaine pour une adresse fixe).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
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


_HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TUNNEL_BASE = "jimmy-mobile"


def valid_hostname(host: str) -> bool:
    return bool(_HOST_RE.match((host or "").strip().lower()))


def named_dir() -> Path:
    d = data_dir() / "tunnel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_named_config(port: int, spec: dict) -> Path:
    """Fichier de réglage du tunnel à nom fixe (régénéré à chaque démarrage : le port peut avoir changé)."""
    path = named_dir() / "config.yml"
    path.write_text(
        f"tunnel: {spec['id']}\n"
        f"credentials-file: '{spec['cred']}'\n"
        "ingress:\n"
        f"  - hostname: {spec['host']}\n"
        f"    service: http://127.0.0.1:{int(port)}\n"
        "  - service: http_status:404\n", encoding="utf-8")
    return path


class Tunnel:
    def __init__(self, on_change=None):
        self._named = None            # tunnel à nom fixe : {"name", "id", "cred", "host"}
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
    def start(self, port: int, named: dict | None = None) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._named = named
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(port,), daemon=True, name="jimmy-tunnel")
        self._thread.start()

    def _run(self, port: int) -> None:
        if not self._ensure_binary():
            return
        if self._named:
            self._run_named(port)
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

    # ------------------------------------------------- tunnel à nom fixe (adresse permanente sur TON domaine)
    def setup_named(self, hostname: str, progress=None, home=None, login_timeout: float = 300.0) -> tuple:
        """Crée une fois pour toutes le tunnel et l'adresse https://<hostname> dans TON compte Cloudflare.
        Une seule action de ta part : te connecter à Cloudflare dans la page qui s'ouvre. -> (ok, message, spec)"""
        def say(t: str) -> None:
            if progress:
                progress(t)
        host = (hostname or "").strip().lower()
        if not valid_hostname(host):
            return False, "Adresse invalide. Exemple : jimmy.example.com", None
        if not self._ensure_binary():
            return False, self.error or "cloudflared est indisponible.", None
        exe = str(binary_path())
        home = Path(home) if home else Path.home() / ".cloudflared"
        home.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "TUNNEL_ORIGIN_CERT": str(home / "cert.pem")}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        def run(args, timeout=90):
            try:
                r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout, env=env, creationflags=flags)
            except subprocess.TimeoutExpired:
                return 1, "délai dépassé"
            return r.returncode, (r.stdout or "") + (r.stderr or "")

        # 1) connexion à Cloudflare (une page s'ouvre dans le navigateur : tu te connectes et tu choisis ton domaine)
        cert = home / "cert.pem"
        if not cert.exists():
            say("Connexion à Cloudflare : une page s'ouvre dans ton navigateur. Connecte-toi et choisis ton domaine…")
            try:
                proc = subprocess.Popen([exe, "tunnel", "login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        encoding="utf-8", errors="replace", env=env, creationflags=flags)
            except OSError as e:
                return False, f"Impossible de lancer cloudflared : {e}", None
            t0 = time.time()
            while time.time() - t0 < login_timeout and not cert.exists():
                if proc.poll() is not None and not cert.exists():
                    time.sleep(0.5)
                    if not cert.exists():
                        break
                time.sleep(1)
            if proc.poll() is None:
                proc.terminate()
            if not cert.exists():
                return False, "La connexion à Cloudflare n'a pas été terminée. Tu peux réessayer.", None
        # 2) le tunnel (un nom propre à ce PC : on n'écrase jamais un autre tunnel)
        name = f"{TUNNEL_BASE}-" + re.sub(r"[^a-z0-9]+", "-", socket.gethostname().lower()).strip("-")[:30]
        cred = home / f"{name}.json"
        say("Création du tunnel…")
        tid = ""
        rc, out = run(["tunnel", "list", "-o", "json", "-n", name])
        try:
            data = json.loads(out[out.index("["):out.rindex("]") + 1]) if "[" in out else []
            tid = str(data[0].get("id", "")) if data else ""
        except (ValueError, AttributeError, IndexError, KeyError):
            tid = ""
        if not tid or not cred.exists():
            rc, out = run(["tunnel", "create", "--credentials-file", str(cred), name])
            m = _UUID_RE.search(out)
            if rc != 0 or not m:
                return False, "Création du tunnel impossible : " + (out.strip().splitlines() or ["?"])[-1][:200], None
            tid = m.group(0)
        # 3) l'adresse fixe sur ton domaine
        say(f"Création de l'adresse {host}…")
        rc, out = run(["tunnel", "route", "dns", "-f", name, host])
        if rc != 0:
            return False, f"Adresse {host} impossible : " + (out.strip().splitlines() or ["?"])[-1][:200], None
        spec = {"name": name, "id": tid, "cred": str(cred), "host": host}
        return True, f"Lien permanent prêt : https://{host}", spec

    def _run_named(self, port: int) -> None:
        spec = self._named
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        while not self._stop.is_set():
            cfg = write_named_config(port, spec)
            self._set("démarrage", url=f"https://{spec['host']}")      # l'adresse est connue d'avance : elle ne change jamais
            try:
                self._proc = subprocess.Popen(
                    [str(binary_path()), "tunnel", "--no-autoupdate", "--config", str(cfg), "run", spec["name"]],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=flags)
            except OSError as e:
                self._set("erreur", f"Impossible de lancer cloudflared : {e}")
                return
            for line in self._proc.stdout:
                if "registered tunnel connection" in line.lower() or "connection registered" in line.lower():
                    self._set("prêt", url=f"https://{spec['host']}")
                if self._stop.is_set():
                    break
            self._proc.wait()
            if self._stop.is_set():
                break
            self._set("démarrage", "Le tunnel s'est coupé, nouvelle tentative…", url=f"https://{spec['host']}")
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
