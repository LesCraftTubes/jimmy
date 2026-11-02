"""Diagnostic de Jimmy : `Jimmy.exe --selftest` écrit selftest.txt (dans le dossier de données) avec le résultat de chaque brique.

Sert à comprendre un souci de reconnaissance vocale chez quelqu'un sans lui demander de parler : le test fabrique lui-même
une phrase, la passe dans le modèle de reconnaissance et vérifie qu'elle est bien comprise.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
import traceback
from pathlib import Path

from config import data_dir


def run() -> Path:
    out = data_dir() / "selftest.txt"
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        out.write_text("\n".join(lines), encoding="utf-8")

    def step(name: str, fn):
        t0 = time.time()
        try:
            res = fn()
            log(f"[OK ] {name} ({time.time() - t0:.1f}s) {res if res is not None else ''}")
            return res
        except Exception:  # noqa: BLE001
            log(f"[ERR] {name}\n{traceback.format_exc()}")
            return None

    from version import __version__
    import sys
    log(f"Jimmy {__version__} · frozen={getattr(sys, 'frozen', False)} · données : {data_dir()}")

    def audio_devices():
        import sounddevice as sd
        d = sd.query_devices()
        ins = [x["name"] for x in d if x["max_input_channels"] > 0]
        return f"{len(ins)} micro(s) ; défaut : {sd.query_devices(kind='input')['name']}"

    step("sounddevice (micros)", audio_devices)

    def mic_open():
        import sounddevice as sd
        with sd.InputStream(samplerate=16000, channels=1, blocksize=1600):
            time.sleep(0.4)
        return "micro ouvert 0,4 s"

    step("ouverture du micro", mic_open)

    def load_model():
        from faster_whisper import WhisperModel
        return WhisperModel("tiny", device="cpu", compute_type="int8")

    model = step("chargement du modèle vocal « tiny » (CPU)", load_model)

    def synth_speech():
        import edge_tts
        mp3 = Path(tempfile.gettempdir()) / "jimmy_selftest.mp3"
        asyncio.run(edge_tts.Communicate("Bonjour Jimmy, ouvre le fichier index point p h p", "fr-FR-HenriNeural").save(str(mp3)))
        return mp3

    mp3 = step("synthèse vocale (edge-tts, internet)", synth_speech)

    def decode(mp3path):
        import av
        import numpy as np
        chunks = []
        with av.open(str(mp3path)) as c:
            rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for fr in c.decode(audio=0):
                for r in rs.resample(fr):
                    chunks.append(r.to_ndarray().reshape(-1))
        return (np.concatenate(chunks).astype("float32") / 32768.0)

    audio = step("décodage audio (av)", lambda: decode(mp3)) if mp3 else None

    if model is not None and audio is not None:
        def transcribe():
            segs, _ = model.transcribe(audio, language="fr", beam_size=1)
            return "« " + " ".join(s.text.strip() for s in segs) + " »"
        step("reconnaissance d'une phrase de test", transcribe)

    def pipeline():
        """Chaîne complète d'écoute avec un faux micro qui « dit » une phrase : mot d'éveil, détection de voix, transcription."""
        import threading
        import numpy as np
        import sounddevice as sd
        from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
        from config import DEFAULTS, Config
        import listener as L

        app = QCoreApplication.instance() or QCoreApplication([])
        import edge_tts
        mp3b = Path(tempfile.gettempdir()) / "jimmy_selftest2.mp3"
        asyncio.run(edge_tts.Communicate("Jimmy, ouvre le fichier index point p h p.", "fr-FR-HenriNeural").save(str(mp3b)))
        speech = decode(mp3b)
        rate = L.SR
        sig = np.concatenate([np.zeros(int(rate * 1.0), "float32"), speech * 0.6, np.zeros(int(rate * 5.0), "float32")]).astype("float32")

        class FakeStream:
            def __init__(self, samplerate=16000, channels=1, dtype="float32", blocksize=512, device=None, callback=None):
                self.cb, self.bs, self.stop = callback, blocksize, threading.Event()

            def __enter__(self):
                def feed():
                    i = 0
                    while not self.stop.is_set():
                        blk = sig[i:i + self.bs]
                        if len(blk) < self.bs:
                            blk = np.concatenate([blk, np.zeros(self.bs - len(blk), "float32")])
                        i += self.bs
                        self.cb(blk.reshape(-1, 1), self.bs, None, None)
                        time.sleep(self.bs / rate)
                threading.Thread(target=feed, daemon=True).start()
                return self

            def __exit__(self, *a):
                self.stop.set()

        real = sd.InputStream
        sd.InputStream = FakeStream
        cfg = Config(dict(DEFAULTS), Path(tempfile.gettempdir()) / "jimmy_selftest_cfg.json")   # réglages d'usine, rien n'est écrit chez toi
        lis = L.Listener(cfg)
        heard, errs, status = [], [], []
        lis.heard.connect(heard.append)
        lis.error.connect(errs.append)
        lis.status.connect(status.append)
        t0 = time.time()
        lis.start()
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if (heard or errs or time.time() - t0 > 120) else None)
        poll.start(300)
        loop.exec()
        lis.stop()
        sd.InputStream = real
        info = f"état={lis.state} ; statuts={status[-3:]} ; erreurs={errs} ; entendu={heard}"
        if errs or not heard:
            raise RuntimeError("Jimmy n'a rien compris : " + info)
        return f"phrase reconnue en {time.time() - t0:.0f}s : {heard[0]!r}"

    step("chaîne d'écoute complète (réglages d'usine, faux micro)", pipeline)
    step("piper (voix locales)", lambda: __import__("piper") and "importé")
    step("pyttsx3", lambda: __import__("pyttsx3") and "importé")
    step("pygame", lambda: __import__("pygame") and "importé")
    log("Fin du diagnostic.")
    return out
