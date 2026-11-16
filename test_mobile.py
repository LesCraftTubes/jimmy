"""Tests de l'appli mobile : autorisation des appareils, appareil conservé, voix Whisper, lien permanent.
Lancer : python -W ignore test_mobile.py   (le test Whisper demande Internet pour fabriquer la voix de test)"""
import asyncio
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jmobile_"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

import remote
import tunnel as TU

app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name, flush=True)
    if not cond:
        fails.append(name)


remote.data_dir = lambda: work
TU.data_dir = lambda: work


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def set(self, k, v):
        self[k] = v


def http(method, port, path, body=None, headers=None, raw=False):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data))
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            return e.code, json.loads(data)
        except ValueError:
            return e.code, data


# ---------------------------------------------------------------- serveur mobile : autoriser chaque nouvel appareil
asked = []
decision = {"ok": True}


class H:
    def remote_snapshot(self):
        return {"state": "idle"}

    def remote_send(self, t):
        pass

    def remote_stop(self):
        pass

    def remote_new(self):
        pass

    def remote_switch(self, s):
        pass

    def remote_approve(self, name, ip, ua):
        asked.append((name, ip, ua))
        return decision["ok"]

    def remote_transcribe(self, data):
        if data == b"BOOM":
            raise RuntimeError("modèle pas prêt")
        return f"texte reçu ({len(data)} octets)."


port = free_port()
cfg = Cfg(remote_port=port)
srv = remote.RemoteServer(cfg, H())
check("le serveur mobile démarre", srv.start(bind_all=False))
st, j = http("GET", port, "/api/ping")
check("ping : annonce que le PC sait transcrire avec Whisper", st == 200 and j.get("whisper") is True)


def pair(code, name="Android (Chrome)"):
    return http("POST", port, "/api/pair", json.dumps({"code": code, "name": name}).encode(), {"Content-Type": "application/json", "User-Agent": "TestPhone/1.0"})


code = srv.current_code()
decision["ok"] = False
st, j = pair(code)
check("appareil REFUSÉ sur le PC : jumelage impossible", st == 403 and "autorisé" in j["error"] and not srv.devices())
check("le PC a bien été interrogé avec le nom et l'adresse de l'appareil", asked and asked[0][0] == "Android (Chrome)" and asked[0][1] == "127.0.0.1" and "TestPhone" in asked[0][2])
decision["ok"] = True
st, j = pair(code)
check("appareil AUTORISÉ sur le PC : jumelage réussi, une clé est donnée", st == 200 and j["ok"] and len(j["token"]) > 30)
token = j["token"]
check("l'appareil est enregistré", len(srv.devices()) == 1 and srv.devices()[0]["name"] == "Android (Chrome)")
st, j2 = pair(code)
check("le code est à usage unique (déjà utilisé)", st == 403)
st, j3 = pair("ZZZZZZZZ")
check("mauvais code : refusé sans même déranger le PC", st == 403 and len(asked) == 2)

# ---------------------------------------------------------------- l'appareil reste relié, même après un redémarrage de Jimmy
srv.stop()
port2 = free_port()
srv2 = remote.RemoteServer(Cfg(remote_port=port2), H())
srv2.start(bind_all=False)
st, j = http("GET", port2, "/api/state", headers={"Authorization": "Bearer " + token})
check("après redémarrage : l'appareil déjà autorisé reste relié (aucun nouveau jumelage)", st == 200 and j["ok"])
st, _ = http("GET", port2, "/api/state", headers={"Authorization": "Bearer mauvaise-cle"})
check("une clé inconnue est refusée", st == 401)

# ---------------------------------------------------------------- la voix du téléphone est transcrite par le PC
st, _ = http("POST", port2, "/api/transcribe", b"x" * 100, {"Content-Type": "audio/webm"})
check("transcription sans clé : refusée", st == 401)
auth = {"Authorization": "Bearer " + token, "Content-Type": "audio/webm"}
st, j = http("POST", port2, "/api/transcribe", b"x" * 100, auth)
check("transcription avec clé : le texte revient", st == 200 and j["ok"] and j["text"] == "texte reçu (100 octets).")
st, j = http("POST", port2, "/api/transcribe", b"", auth)
check("audio vide : refusé proprement", st == 400)
st, j = http("POST", port2, "/api/transcribe", b"BOOM", auth)
check("le modèle plante : erreur claire, serveur toujours vivant", st == 500 and "pas prêt" in j["error"] and http("GET", port2, "/api/ping")[0] == 200)
srv2.stop()

# ---------------------------------------------------------------- décodage audio réel (webm/opus, ogg, wav 44,1 kHz stéréo)
import numpy as np
from listener import decode_audio_bytes

try:
    import av
except ImportError:
    av = None
check("PyAV disponible", av is not None)


def make_audio(fmt, codec, rate, layout, seconds=1.0):
    buf = io.BytesIO()
    with av.open(buf, "w", format=fmt) as out:
        st = out.add_stream(codec, rate=rate)
        st.layout = layout
        n = 960 if codec == "libopus" else 1024
        t = 0
        total = int(rate * seconds)
        ch = 2 if layout == "stereo" else 1
        while t < total:
            samples = (0.4 * np.sin(2 * np.pi * 440 * (np.arange(n) + t) / rate) * 32767).astype(np.int16)
            data = np.repeat(samples, ch).reshape(1, -1) if ch == 1 else np.stack([samples, samples], 1).reshape(1, -1)
            fr = av.AudioFrame.from_ndarray(data, format="s16", layout=layout)
            fr.sample_rate = rate
            fr.pts = t
            for p in st.encode(fr):
                out.mux(p)
            t += n
        for p in st.encode(None):
            out.mux(p)
    return buf.getvalue()


for label, fmt, codec, rate, layout in (("webm/opus (Android, Chrome)", "webm", "libopus", 48000, "mono"), ("ogg/opus", "ogg", "libopus", 48000, "mono"),
                                         ("wav 44,1 kHz stéréo", "wav", "pcm_s16le", 44100, "stereo")):
    try:
        data = make_audio(fmt, codec, rate, layout)
        a = decode_audio_bytes(data)
        check(f"décodage {label} : mono 16 kHz, ~1 s, sans dépassement", a.dtype == np.float32 and 14000 < a.size < 18500 and float(np.max(np.abs(a))) <= 1.0 and float(np.max(np.abs(a))) > 0.2)
    except Exception as e:  # noqa: BLE001
        check(f"décodage {label} ({e})", False)

# ---------------------------------------------------------------- voix réelle -> texte (même chemin que le téléphone : décodage puis Whisper)
try:
    import edge_tts
    from faster_whisper import WhisperModel
    from listener import prep_audio
    mp3 = work / "voix.mp3"
    asyncio.run(edge_tts.Communicate("Bonjour Jimmy, ouvre le fichier index point p h p", "fr-FR-HenriNeural").save(str(mp3)))
    audio = decode_audio_bytes(mp3.read_bytes())
    import listener as L
    try:
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
    except Exception:                       # cache Windows cassé (WinError 448) : même repli que l'application
        L._heal_model_cache("tiny")
        from faster_whisper.utils import download_model
        model = WhisperModel(download_model("tiny", output_dir=L._own_model_dir("tiny")), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(prep_audio(audio), language="fr", beam_size=5)
    heard = " ".join(s.text.strip() for s in segs).lower()
    check(f"voix réelle -> texte via le pipeline du téléphone : « {heard.strip()[:60]} »", "jimmy" in heard and "fichier" in heard)
except Exception as e:  # noqa: BLE001
    check(f"voix réelle -> texte ({type(e).__name__}: {str(e)[:80]})", False)

# ---------------------------------------------------------------- lien permanent : tunnel à nom fixe (faux cloudflared)
fake_dir = work / "fakecf"
fake_dir.mkdir()
bat = fake_dir / "cloudflared.bat"
bat.write_text(f'@echo off\r\n"{sys.executable}" "{Path(__file__).parent / "fake_cloudflared.py"}" %*\r\n', encoding="utf-8")
calls_log = work / "cf_calls.log"
os.environ["FAKE_CF_LOG"] = str(calls_log)
TU.binary_path = lambda: bat
TU.Tunnel._ensure_binary = lambda self: True
home = work / "cfhome"

check("adresse valide acceptée", TU.valid_hostname("jimmy.example.com") and TU.valid_hostname("a-b.example.com"))
check("adresses dangereuses ou invalides refusées", not any(TU.valid_hostname(h) for h in ("", "jimmy", "x y.fr", "a.fr; calc", "http://jimmy.fr", "-a.fr", "jimmy..fr")))

t = TU.Tunnel()
ok, msg, spec = t.setup_named("pas valide", home=home)
check("hôte invalide : refusé AVANT de lancer quoi que ce soit", not ok and not calls_log.exists())
steps = []
ok, msg, spec = t.setup_named("Jimmy.Example.com", progress=steps.append, home=home, login_timeout=20)
check("création du lien permanent réussie", ok and spec and spec["host"] == "jimmy.example.com" and "https://jimmy.example.com" in msg)
calls = [json.loads(line) for line in calls_log.read_text().splitlines()]
kinds = [c[:3] if c[:2] == ["tunnel", "route"] else c[:2] for c in calls]
check("ordre : connexion Cloudflare, liste, création, route DNS", kinds == [["tunnel", "login"], ["tunnel", "list"], ["tunnel", "create"], ["tunnel", "route", "dns"]])
check("l'adresse demandée est bien la route DNS (jimmy.example.com)", calls[-1][-1] == "jimmy.example.com")
check("l'utilisateur est prévenu de la connexion Cloudflare à faire", any("navigateur" in s for s in steps))
check("les clés du tunnel sont créées dans le dossier Cloudflare de l'utilisateur", Path(spec["cred"]).exists() and (home / "cert.pem").exists())
calls_log.unlink()
ok2, _, spec2 = TU.Tunnel().setup_named("jimmy.example.com", home=home)
calls2 = [json.loads(line) for line in calls_log.read_text().splitlines()]
check("2e fois : pas de nouvelle connexion Cloudflare (déjà connecté)", ok2 and ["tunnel", "login"] not in [c[:2] for c in calls2])

cfgfile = TU.write_named_config(8765, spec)
txt = cfgfile.read_text(encoding="utf-8")
check("réglage du tunnel : bon nom de domaine et bon port local, 404 pour le reste", "hostname: jimmy.example.com" in txt and "http://127.0.0.1:8765" in txt and "http_status:404" in txt and spec["id"] in txt)

t3 = TU.Tunnel()
changes = []
t3.on_change = lambda: changes.append((t3.status, t3.url))
t3.start(8765, named=spec)
t0 = time.time()
while t3.status != "prêt" and time.time() - t0 < 20:
    app.processEvents()
    time.sleep(0.1)
check("le tunnel permanent démarre et devient « prêt »", t3.status == "prêt")
check("son adresse est fixe, connue dès le démarrage (même avant d'être prêt)", all(u == "https://jimmy.example.com" for s, u in changes if s in ("démarrage", "prêt")) and t3.url == "https://jimmy.example.com")
t3.stop()

# ---------------------------------------------------------------- le gestionnaire : adresse permanente enregistrée
from remote_manager import RemoteManager

mcfg = Cfg(remote_enabled=True, remote_mode="permanent", remote_port=free_port(), remote_perm_host=spec["host"], remote_perm_id=spec["id"],
           remote_perm_cred=spec["cred"], remote_perm_name=spec["name"])
mgr = RemoteManager(mcfg, H())
check("mode permanent : l'adresse du lien est toujours https://<ton domaine>", mgr.base_url() == "https://jimmy.example.com" and mgr.secure())
check("le lien de jumelage contient le code (à copier, ou en QR)", mgr.pair_url().startswith("https://jimmy.example.com/#pair="))
mgr.cfg["remote_perm_host"] = ""
mgr.server.running = True            # (le serveur n'est pas démarré dans ce test : on regarde seulement le message)
check("lien permanent pas encore créé : le bouton est proposé", "pas encore créé" in mgr.status_text() and mgr.base_url() == "")

# ---------------------------------------------------------------- la fenêtre : « Autoriser cet appareil ? » sur le PC
import window as W


def ask(choice):
    host = QWidget()
    req = {"name": "iPhone (Safari)", "ip": "82.1.2.3", "ua": "x", "ev": threading.Event(), "ok": False}
    texts = []

    def click():
        box = QApplication.activeModalWidget()
        if isinstance(box, QMessageBox):
            texts.append(box.text())
            for b in box.buttons():
                if b.text().replace("&", "") == choice:
                    b.click()
                    return
        QTimer.singleShot(100, click)
    QTimer.singleShot(300, click)
    W.JimmyWindow._on_remote_ask(host, req)
    return req, texts


req, texts = ask("Autoriser")
check("PC : « Autoriser » -> appareil accepté", req["ok"] is True and req["ev"].is_set())
check("la fenêtre dit quel appareil demande et depuis quelle adresse", "iPhone (Safari)" in texts[0] and "82.1.2.3" in texts[0])
req, _ = ask("Refuser")
check("PC : « Refuser » -> appareil refusé", req["ok"] is False and req["ev"].is_set())

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.stdout.flush()
os._exit(1 if fails else 0)
