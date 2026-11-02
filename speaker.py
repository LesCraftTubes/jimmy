"""Voix de Jimmy : edge-tts (voix neuronale, nécessite Internet), pyttsx3 en secours.

Les voix « cyber » passent par un petit traitement audio maison (flanger, modulation,
écho, grain numérique) pour un rendu plus synthétique.
"""
import re
import asyncio
import json
import os
import queue
import tempfile
import threading
import time
import shutil
import urllib.request
import wave
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
from PySide6.QtCore import QObject, Signal

from audio_devices import resolve
from config import app_dir, data_dir
from textutils import clean_for_tts, split_for_speech

SR = 24000

# nom affiché -> (voix, débit, hauteur, effet)
#  - voix edge-tts (en ligne) : "fr-FR-...Neural", débit "+6%", hauteur "-3Hz"
#  - voix Piper (téléchargées sur ton PC, hors ligne) : "piper:<modèle>[:<locuteur>]", débit = vitesse
#    d'élocution ("1.0" normal, plus petit = plus rapide), hauteur ignorée.
VOICE_PRESETS = {
    # Voix naturelles (les plus « vraies ») avec juste une présence un peu futuriste.
    "Jimmy": ("fr-FR-HenriNeural", "+8%", "-8Hz", "cyber"),   # ex « Cyber (grave) »
    "Nova (naturelle)": ("fr-FR-VivienneMultilingualNeural", "+5%", "+0Hz", "aura"),
    "Netrunner": ("fr-FR-RemyMultilingualNeural", "+6%", "-3Hz", "netrunner"),
    "Hologramme": ("fr-FR-VivienneMultilingualNeural", "+5%", "+2Hz", "holo"),
    "Smasher": ("fr-FR-HenriNeural", "+0%", "-10Hz", "smasher"),
    "Néon (féminine)": ("fr-FR-DeniseNeural", "+6%", "+0Hz", "cyber"),
    "Androïde": ("fr-FR-RemyMultilingualNeural", "+4%", "-5Hz", "robot"),
    "Glitch": ("fr-FR-HenriNeural", "+10%", "-4Hz", "glitch"),
    "Naturelle": ("fr-FR-HenriNeural", "+8%", "+0Hz", ""),
    # Autres voix en ligne : Éloïse, Belgique, Suisse, Québec.
    "Éloïse": ("fr-FR-EloiseNeural", "+5%", "+0Hz", "aura"),
    "Charline (Belgique)": ("fr-BE-CharlineNeural", "+4%", "+0Hz", "aura"),
    "Gérard (Belgique)": ("fr-BE-GerardNeural", "+4%", "+0Hz", "aura"),
    "Ariane (Suisse)": ("fr-CH-ArianeNeural", "+4%", "+0Hz", "aura"),
    "Fabrice (Suisse)": ("fr-CH-FabriceNeural", "+4%", "+0Hz", "aura"),
    "Sylvie (Québec)": ("fr-CA-SylvieNeural", "+4%", "+0Hz", "aura"),
    "Jean (Québec)": ("fr-CA-JeanNeural", "+4%", "+0Hz", "aura"),
    "Antoine (Québec)": ("fr-CA-AntoineNeural", "+4%", "+0Hz", "aura"),
    "Thierry (Québec)": ("fr-CA-ThierryNeural", "+4%", "+0Hz", "aura"),
    # Voix locales Piper (téléchargées une fois, fonctionnent sans Internet, 0 token).
    "Siwis · locale": ("piper:fr_FR-siwis-medium", "0.95", "", ""),
    "Tom · locale": ("piper:fr_FR-tom-medium", "0.95", "", ""),
    "Jessica · locale": ("piper:fr_FR-upmc-medium:0", "0.95", "", ""),
    "Pierre · locale": ("piper:fr_FR-upmc-medium:1", "0.95", "", ""),
    "Gilles · locale": ("piper:fr_FR-gilles-low", "0.95", "", ""),
    "Tom · Cyber": ("piper:fr_FR-tom-medium", "0.92", "", "cyber"),
    "Tom · Smasher": ("piper:fr_FR-tom-medium", "1.0", "", "smasher"),
    "Siwis · Hologramme": ("piper:fr_FR-siwis-medium", "0.95", "", "holo"),
    "Jessica · Néon": ("piper:fr_FR-upmc-medium:0", "0.92", "", "cyber"),
    "Pierre · Netrunner": ("piper:fr_FR-upmc-medium:1", "0.95", "", "netrunner"),
    "Gilles · Androïde": ("piper:fr_FR-gilles-low", "0.95", "", "robot"),
    # Voix premium ElevenLabs : nécessite une clé (elevenlabs_api_key dans config.json).
    "ElevenLabs (premium)": ("elevenlabs", "", "", ""),
}
DEFAULT_PRESET = "Jimmy"
# Anciens noms de voix -> nom actuel (les réglages déjà enregistrés continuent de marcher).
LEGACY_PRESETS = {"Cyber (grave)": "Jimmy", "Jimmy (naturelle)": "Jimmy"}


def resolve_preset(name):
    return LEGACY_PRESETS.get(name, name) or DEFAULT_PRESET


# ------------------------------------------------------------------ effets audio
def _flanger(x, depth_ms=2.5, rate_hz=0.35, mix=0.55):
    n = np.arange(len(x))
    delay = (depth_ms / 1000 * SR) * (0.5 + 0.5 * np.sin(2 * np.pi * rate_hz * n / SR)) + 1
    return (1 - mix) * x + mix * np.interp(n - delay, n, x, left=0.0)


def _echo(x, ms=90, gain=0.22):
    d = int(SR * ms / 1000)
    y = x.copy()
    y[d:] += gain * x[:-d]
    return y


def _ring(x, freq, mix):
    t = np.arange(len(x)) / SR
    return (1 - mix) * x + mix * x * np.sin(2 * np.pi * freq * t)


def _crush(x, bits=9, hold=2):
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    return np.repeat(y[::hold], hold)[: len(x)]


def _glitch(x):
    rng = np.random.default_rng(7)
    y = x.copy()
    block = int(SR * 0.06)
    for start in range(0, len(y) - 2 * block, block * 7):
        if rng.random() < 0.35:
            y[start + block:start + 2 * block] = y[start:start + block]  # micro-répétition
    return y


def _comb(x, ms, gain):
    """Résonance métallique courte (voix « dans une armure »)."""
    d = max(1, int(SR * ms / 1000))
    y = x.copy()
    for i in range(1, 4):
        if d * i < len(x):
            y[d * i:] += (gain ** i) * x[: -d * i]
    return y


def _saturate(x, drive):
    return np.tanh(x * drive) / np.tanh(drive)


def apply_effect(x: np.ndarray, effect: str) -> np.ndarray:
    if effect == "aura":
        # Quasi naturelle : léger chorus et petite pièce « métallique », sans effet robot.
        y = 0.88 * x + 0.12 * _flanger(x, depth_ms=1.0, rate_hz=0.25, mix=1.0)
        y = _echo(_echo(y, ms=45, gain=0.10), ms=95, gain=0.06)
    elif effect == "smasher":
        # Grave et cuirassé, mais sans la saturation façon « voice mod ».
        y = x * 0.9 / (float(np.max(np.abs(x))) or 1.0)
        y = _saturate(y, 1.4)
        y = 0.88 * y + 0.12 * _comb(y, 7, 0.4)
        y = _echo(y, ms=150, gain=0.07)
    elif effect == "netrunner":
        # Presque naturelle, avec juste un voile holographique.
        y = _flanger(x, depth_ms=1.8, rate_hz=0.18, mix=0.22)
        y = _echo(y, ms=120, gain=0.12)
    elif effect == "cyber":
        y = _flanger(x)
        y = _ring(y, 38, 0.18)
        y = _echo(_crush(y, bits=10, hold=1), ms=70, gain=0.18)
    elif effect == "robot":
        y = _ring(x, 62, 0.65)
        y = _echo(_flanger(y, depth_ms=1.2, rate_hz=0.8, mix=0.4), ms=12, gain=0.35)
    elif effect == "holo":
        y = _flanger(x, depth_ms=4.0, rate_hz=0.2, mix=0.5)
        y = _echo(_echo(y, ms=110, gain=0.25), ms=230, gain=0.12)
    elif effect == "glitch":
        y = _crush(_ring(_glitch(x), 45, 0.25), bits=8, hold=2)
        y = _echo(y, ms=60, gain=0.2)
    else:
        return x
    peak = float(np.max(np.abs(y))) or 1.0
    return y * (0.92 / peak)


PIPER_REPO = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"


def voices_dir() -> Path:
    d = data_dir() / "voices"
    d.mkdir(exist_ok=True)
    return d


def piper_ready(model: str) -> bool:
    return (voices_dir() / f"{model}.onnx").exists() and (voices_dir() / f"{model}.onnx.json").exists()


def piper_download(model: str) -> None:
    """Télécharge une voix Piper (ex. fr_FR-tom-medium) depuis Hugging Face, une seule fois."""
    lang, name, quality = model.split("-")
    base = f"{PIPER_REPO}{lang.split('_')[0]}/{lang}/{name}/{quality}/{model}"
    for ext in (".onnx.json", ".onnx"):
        dest = voices_dir() / (model + ext)
        if dest.exists():
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(base + ext, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dest)


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR or len(x) < 2:
        return x
    n = int(len(x) * SR / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _decode(path: str) -> np.ndarray:
    import av

    out = []
    with av.open(path) as container:
        res = av.AudioResampler(format="flt", layout="mono", rate=SR)
        for frame in container.decode(audio=0):
            for f in res.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out).astype(np.float32) if out else np.zeros(1, np.float32)


def _write_wav(x: np.ndarray, path: str) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def glitch_voice(x, level: float):
    """Cyberpsychose : petits accrocs dans la voix (bégaiement, grésillement numérique, parasite, micro-coupure).

    Chaque accroc dure 20 à 120 ms et remplace le son sur place : la durée ne change pas et la phrase reste
    compréhensible. `level` de 0 à 1 règle la fréquence (un accroc toutes les ~4 s au plus bas, ~1,2 s au plus haut).
    """
    if level <= 0 or len(x) < SR // 2:
        return x
    rng = np.random.default_rng()
    y = np.array(x, dtype=np.float32, copy=True)
    rate = 0.25 + 0.55 * min(1.0, level)
    t = int(0.35 * SR)
    end = len(y) - int(0.2 * SR)
    while True:
        t += int(rng.exponential(1.0 / rate) * SR)
        if t >= end:
            break
        kind = int(rng.integers(0, 4))
        if kind == 0:                                   # bégaiement : un bout de 45 ms répété 3 fois
            n = int(rng.uniform(0.035, 0.055) * SR)
            seg = y[t:t + n].copy()
            for k in range(1, 4):
                dst = y[t + k * n:t + (k + 1) * n]
                dst[:] = seg[:len(dst)]
            n *= 4
        elif kind == 1:                                 # grésillement numérique (son « écrasé »)
            n = int(rng.uniform(0.06, 0.12) * SR)
            seg = y[t:t + n]
            step = int(rng.integers(4, 9))
            crushed = np.repeat(seg[::step], step)[:len(seg)]
            q = 2 ** int(rng.integers(4, 7))
            y[t:t + n] = np.round(crushed * q) / q
        elif kind == 2:                                 # souffle de parasite par-dessus la voix
            n = int(rng.uniform(0.03, 0.07) * SR)
            seg = y[t:t + n]
            seg += rng.normal(0.0, 0.035 + 0.04 * level, len(seg)).astype(np.float32)
        else:                                           # micro-coupure : la voix baisse brièvement
            n = int(rng.uniform(0.02, 0.04) * SR)
            seg = y[t:t + n]
            seg *= 0.12
        t += n
    return np.clip(y, -1.0, 1.0).astype(np.float32)


class Speaker(QObject):
    """Lit le texte phrase par phrase : la 1re phrase part dès qu'elle est prête,
    les suivantes se préparent pendant qu'elle est jouée (beaucoup moins d'attente)."""

    finished = Signal()
    error = Signal(str)
    # morceau lu à l'instant + sa durée (s) + [(instant, mot)] pour écrire chaque mot quand il est dit
    chunk_started = Signal(str, float, object)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._stop = threading.Event()
        self._piper_cache = {}
        self._piper_lock = threading.Lock()
        self.glitch_level = 0.0   # cyberpsychose : 0 = voix normale (réglé par la fenêtre)
        self._gen = 0   # numéro de la lecture en cours (une ancienne lecture s'arrête d'elle-même)

    def preset(self):
        name = resolve_preset(self.cfg.get("voice_preset"))
        if name in VOICE_PRESETS:
            voice, rate, pitch, effect = VOICE_PRESETS[name]
        else:
            voice, rate, pitch, effect = (self.cfg.get("tts_voice", "fr-FR-HenriNeural"),
                                          self.cfg.get("tts_rate", "+0%"), "+0Hz", "")
        # Vitesse en plus (en points de %) pour les voix en ligne ; les voix Piper gardent la leur.
        m = re.fullmatch(r"([+-]\d+)%", str(rate))
        if m:
            bonus = int(self.cfg.get("tts_speed_bonus", 0) or 0)
            rate = f"{max(-50, min(60, int(m.group(1)) + bonus)):+d}%"
        return voice, rate, pitch, effect

    def speak(self, text: str) -> None:
        chunks = split_for_speech(clean_for_tts(text))
        if not chunks:
            self.finished.emit()
            return
        self._stop.clear()
        self._gen += 1
        threading.Thread(target=self._run, args=(chunks, self._gen), daemon=True).start()

    def stop(self) -> None:
        self._stop.set()  # la boucle de _play coupe le son dans les 20 ms

    def output_device(self):
        return resolve(self.cfg.get("speaker_device"), "output")

    def beep(self, freq: float = 988, ms: int = 90, volume: float = 0.3, to_freq: float = 0) -> None:
        """Petit bip sur la sortie choisie (mot d'éveil, début/fin de capture, test des réglages).

        to_freq : glissement vers cette fréquence (petit « bloup » montant ou descendant).
        """
        import sounddevice as sd

        t = np.arange(int(SR * ms / 1000)) / SR
        f = np.linspace(freq, to_freq or freq, len(t))
        env = np.minimum(1, np.minimum(t, t[::-1]) * 150)   # attaque et fin douces
        x = (volume * np.sin(2 * np.pi * np.cumsum(f) / SR) * env).astype(np.float32)
        try:
            sd.play(x, SR, device=self.output_device())
        except Exception:  # noqa: BLE001
            try:
                sd.play(x, SR)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ internes
    def _run(self, chunks: list, gen: int) -> None:
        q = queue.Queue(maxsize=3)
        threading.Thread(target=self._produce, args=(chunks, q, gen), daemon=True).start()
        played = 0
        try:
            while not self._stop.is_set():
                item = q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    self.error.emit(f"Voix en ligne indisponible ({item}), voix locale utilisée.")
                    rest = " ".join(chunks[played:])
                    self.chunk_started.emit(rest, len(rest) * 0.065, [])
                    self._fallback(rest)
                    break
                text, path, duration, words = item
                self.chunk_started.emit(text, duration, words)
                self._play(path)
                _remove(path)
                played += 1
        finally:
            if gen == self._gen:
                self._stop.set()
            while True:  # nettoie ce qui a été préparé mais pas lu
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, tuple):
                    _remove(item[1])
            self.finished.emit()

    def _produce(self, chunks: list, q: queue.Queue, gen: int) -> None:
        for text in chunks:
            if self._stop.is_set() or gen != self._gen:
                break
            try:
                item = (text,) + self._render(text)
            except Exception as e:  # noqa: BLE001
                item = e
            while not self._stop.is_set():
                try:
                    q.put(item, timeout=0.2)
                    break
                except queue.Full:
                    continue
            else:
                if isinstance(item, tuple):
                    _remove(item[1])
            if isinstance(item, Exception):
                return
        while not self._stop.is_set():
            try:
                q.put(None, timeout=0.2)
                return
            except queue.Full:
                continue

    def _render(self, text: str):
        """Synthèse + effet -> (fichier wav, durée en secondes, instants des mots)."""
        voice, rate, pitch, effect = self.preset()
        words = []
        if voice.startswith("piper:"):
            try:
                x, words = self._piper(text, voice, rate)
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"Voix locale indisponible ({e}), voix Jimmy utilisée.")
                voice, rate, pitch, effect = VOICE_PRESETS[DEFAULT_PRESET]
                mp3, words = self._synthesize(text, voice, rate, pitch)
                try:
                    x = _decode(mp3)
                finally:
                    _remove(mp3)
            if effect:
                x = apply_effect(x, effect)
            x = glitch_voice(x, self.glitch_level)
            fd, wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(x, wav)
            return wav, len(x) / SR, words
        if voice == "elevenlabs":
            try:
                mp3 = self._elevenlabs(text)
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"ElevenLabs indisponible ({e}), voix Jimmy utilisée.")
                voice, rate, pitch, effect = VOICE_PRESETS[DEFAULT_PRESET]
                mp3, words = self._synthesize(text, voice, rate, pitch)
        else:
            mp3, words = self._synthesize(text, voice, rate, pitch)
        try:
            x = _decode(mp3)
        finally:
            _remove(mp3)
        if effect:
            x = apply_effect(x, effect)
        x = glitch_voice(x, self.glitch_level)
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        _write_wav(x, wav)
        return wav, len(x) / SR, words

    def _piper(self, text: str, voice: str, rate: str):
        """Voix Piper locale -> (signal à SR, instants des mots estimés d'après la longueur)."""
        from piper import PiperVoice, SynthesisConfig

        _, model, *spk = voice.split(":")
        if not piper_ready(model):
            self.error.emit("Téléchargement de la voix locale (une seule fois, ~60 Mo)…")
            piper_download(model)
        with self._piper_lock:
            pv = self._piper_cache.get(model)
            if pv is None:
                pv = self._piper_cache[model] = PiperVoice.load(str(voices_dir() / f"{model}.onnx"))
            try:
                length = float(rate or 1.0)
            except ValueError:
                length = 1.0
            conf = SynthesisConfig(speaker_id=int(spk[0]) if spk else None, length_scale=length)
            parts = [c.audio_float_array for c in pv.synthesize(text, syn_config=conf)]
            sr = pv.config.sample_rate
        x = _resample(np.concatenate(parts).astype(np.float32), sr) if parts else np.zeros(1, np.float32)
        # Piper ne donne pas les instants des mots : on les répartit selon le poids de chaque mot
        # (le texte s'écrit donc mot à mot, calé sur la voix).
        dur = len(x) / SR
        toks = text.split()
        weights = [len(t) + 1.5 for t in toks]
        total, acc, words = sum(weights) or 1.0, 0.0, []
        for tok, w in zip(toks, weights):
            words.append((dur * acc / total, tok))
            acc += w
        return x, words

    def _synthesize(self, text: str, voice: str, rate: str, pitch: str):
        """-> (fichier mp3, [(début en s, mot), ...]) : les instants exacts de chaque mot."""
        import edge_tts

        async def go():
            audio, words = bytearray(), []
            comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    words.append((chunk["offset"] / 1e7, chunk["text"]))
            return bytes(audio), words

        try:
            audio, words = asyncio.run(go())
        except Exception:  # noqa: BLE001
            audio, words = asyncio.run(go())  # erreur passagère du service : 2e essai
        fd, path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return path, words

    def _elevenlabs(self, text: str) -> str:
        key = (self.cfg.get("elevenlabs_api_key") or "").strip()
        if not key:
            raise RuntimeError("aucune clé elevenlabs_api_key dans config.json")
        voice_id = self.cfg.get("elevenlabs_voice_id") or "pNInz6obpgDQGcFmaJgB"
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            data=json.dumps({
                "text": text,
                "model_id": self.cfg.get("elevenlabs_model") or "eleven_flash_v2_5",
            }).encode("utf-8"),
            headers={"xi-api-key": key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        fd, path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    def _play(self, path: str) -> None:
        import sounddevice as sd

        with wave.open(path, "rb") as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        try:
            sd.play(x, sr, device=self.output_device())
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Sortie audio choisie indisponible ({e}), sortie par défaut utilisée.")
            self.cfg.set("speaker_device", None)
            sd.play(x, sr)
        end = time.time() + len(x) / sr + 0.5
        while time.time() < end and not self._stop.is_set():
            stream = sd.get_stream()
            if not stream.active:
                break
            time.sleep(0.02)
        sd.stop()

    def _fallback(self, text: str) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                if "fr" in (str(v.id) + str(v.name)).lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Aucune voix disponible : {e}")


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
