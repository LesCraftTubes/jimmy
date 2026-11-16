"""Écoute permanente du micro : mot d'éveil « Jimmy », puis transcription de ta commande.

Principe : on découpe le flux micro en phrases (détection de silence), on transcrit chaque
phrase avec Whisper en local, et on cherche « Jimmy » au début. Aucun modèle de mot
d'éveil à entraîner, et rien n'est envoyé sur Internet pour l'écoute.
"""
import glob
import os
import queue
import sys
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

from audio_devices import resolve
from textutils import apply_corrections, collapse_repeats, extract_wake, is_hallucination, looks_unfinished

SR = 16000
BLOCK = 512
BLOCK_S = BLOCK / SR
REFINE_MAX_S = 45     # jusqu'à cette durée, une phrase reprise après une pause est retranscrite d'un bloc


def _compute(device: str) -> str:
    return "int8" if device == "cpu" else "float16"


def _cuda_ok() -> bool:
    """Vrai seulement si la carte NVIDIA est là ET que les bibliothèques CUDA se chargent vraiment (sinon la reconnaissance
    échouerait en plein usage : « cublas64_12.dll introuvable »)."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:  # noqa: BLE001
        return False
    _add_cuda_dlls()
    if os.name != "nt":
        return True
    import ctypes
    try:
        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn64_9.dll")
        return True
    except OSError:
        return False


def auto_choice(cfg) -> tuple:
    """(modèle, matériel) conseillés pour ce PC quand les réglages disent « auto » : carte NVIDIA -> large-v3-turbo (précis ET rapide),
    sinon processeur -> small."""
    if _cuda_ok():
        try:
            from brain import hardware
            if hardware.survey()["vram_gb"] >= 5.5:
                return "large-v3-turbo", "cuda"
        except Exception:  # noqa: BLE001
            pass
        return "medium", "cuda"
    return "small", "cpu"


def decode_audio_bytes(data: bytes):
    """Son envoyé par un téléphone (webm/opus, mp4/aac, ogg...) -> tableau float32 mono 16 kHz, prêt pour Whisper."""
    import io

    import av
    parts = []
    with av.open(io.BytesIO(data)) as c:
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in c.decode(audio=0):
            out = res.resample(frame)
            for o in (out if isinstance(out, list) else [out]):
                if o is not None:
                    parts.append(o.to_ndarray().reshape(-1))
        out = res.resample(None)
        for o in (out if isinstance(out, list) else [out]):
            if o is not None:
                parts.append(o.to_ndarray().reshape(-1))
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32) / 32768.0


def prep_audio(audio):
    """Nettoie le son avant la reconnaissance : enlève le décalage continu et remonte les voix trop basses (micro de casque
    sans fil, voix posée) jusqu'à un niveau où Whisper est le plus précis. Gain limité pour ne pas gonfler le bruit."""
    a = np.asarray(audio, dtype=np.float32)
    if a.size == 0:
        return a
    a = a - float(np.mean(a))
    peak = float(np.max(np.abs(a)))
    if 1e-4 < peak < 0.6:
        a = a * min(8.0, 0.7 / peak)
    return np.clip(a, -1.0, 1.0)


def _own_model_dir(name: str) -> str:
    """Dossier des modèles vocaux propre à Jimmy (vrais fichiers, pas de liens symboliques)."""
    base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Jimmy", "models", name)
    os.makedirs(base, exist_ok=True)
    return base


def _heal_model_cache(name: str) -> None:
    """Supprime l'entrée du cache Hugging Face d'un modèle si elle contient des liens cassés (0 octet).

    Elle ne contient alors aucune donnée utile : le modèle sera simplement retéléchargé.
    """
    import shutil
    root = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    for d in glob.glob(os.path.join(root, f"models--*--faster-whisper-{name}")):
        broken = False
        for sub in ("blobs", "snapshots"):
            for dirpath, _dirs, files in os.walk(os.path.join(d, sub)):
                for f in files:
                    p = os.path.join(dirpath, f)
                    if os.path.islink(p) and not os.path.exists(p):
                        broken = True
        if broken:
            shutil.rmtree(d, ignore_errors=True)


def _add_cuda_dlls() -> None:
    """Rend visibles les bibliothèques CUDA installées par pip (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
    try:
        import gpupack
        gpupack.register()       # bibliothèques téléchargées par Jimmy (version installée)
    except Exception:  # noqa: BLE001
        pass
    base = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
    for d in glob.glob(os.path.join(base, "*", "bin")):
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


class Listener(QObject):
    state_changed = Signal(str)   # loading | wake | listening | idle
    level = Signal(float)         # volume du micro (0..1 environ)
    heard = Signal(str)           # commande complète reconnue
    status = Signal(str)          # messages d'information
    error = Signal(str)
    woke = Signal()               # mot d'éveil reconnu
    capture = Signal(bool)        # True : ta voix est captée, False : fin de la capture
    partial = Signal(str)         # texte en cours de reconnaissance (aperçu en direct, "" = effacer)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.state = "loading"
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._force = threading.Event()
        self._reset = threading.Event()
        self._restart = threading.Event()
        self._flush = threading.Event()   # « valide ce qui a été dit » (2e clic sur Parler)
        self._muted = threading.Event()   # micro coupé : rien n'est écouté, même pas « Jimmy »
        self._wake_on = bool(cfg.get("wake_words_enabled", True))
        self._phone_lock = threading.Lock()       # une voix de téléphone à la fois
        self.last_wake = ""          # "local" si tu as dit « Hey Aurélie », "claude" si « Hey Jimmy »
        # ~1 min de son en attente : rien n'est perdu pendant qu'une phrase est transcrite.
        self._q = queue.Queue(maxsize=2000)
        self._thread = None
        self._model = None
        self._wake_model = None
        self._prefix = ""             # début de phrase entendu juste après « Jimmy »
        self._cmd_audio = []          # son de ce début de phrase (pour tout retranscrire d'un bloc à la reprise)
        self._cmd_refinable = True
        self._partial_gen = 0         # change à chaque fin de phrase : écarte les aperçus périmés
        self._partial_busy = False
        self._followup = False        # écoute de suite de conversation (sans mot d'éveil)
        self._force_followup = False
        self._force_timeout = 10.0
        self._cmd_timeout = 10.0
        self.last_followup = False    # la dernière phrase envoyée venait d'une écoute de suite

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def pause(self) -> None:
        """Ignore le micro (pendant que Jimmy réfléchit ou parle)."""
        self._force.clear()
        self._paused.set()

    def resume(self) -> None:
        self._reset.set()
        self._paused.clear()

    def listen_now(self, timeout: float = 10.0, followup: bool = False) -> None:
        """Équivalent d'avoir dit « Jimmy » (bouton Parler).

        followup=True : écoute courte juste après une réponse de Jimmy, sans mot d'éveil ;
        la phrase captée est marquée (last_followup) pour vérifier qu'elle lui est adressée.
        """
        self._force_timeout = float(timeout)
        self._force_followup = bool(followup)
        self._force.set()
        self._paused.clear()

    def cancel_listen(self) -> None:
        """Arrête l'écoute en cours (2e clic sur Parler) : retour en veille, rien n'est envoyé."""
        self._force.clear()
        self._reset.set()

    def flush_now(self) -> None:
        """Arrête d'écouter mais GARDE ce qui a déjà été dit : c'est envoyé (ou écrit en dictée)."""
        self._flush.set()

    def set_muted(self, on: bool) -> None:
        if on:
            self._force.clear()
            self._muted.set()
        else:
            self._muted.clear()
            self._reset.set()

    @property
    def muted(self) -> bool:
        return self._muted.is_set()

    def set_wake_enabled(self, on: bool) -> None:
        self._wake_on = bool(on)

    def restart(self) -> None:
        """Rouvre le micro avec les réglages actuels (nouveau périphérique, sensibilité...)."""
        self._restart.set()

    # ------------------------------------------------------------ internes
    def _set_state(self, s: str) -> None:
        if s != self.state:
            was, self.state = self.state, s
            # Bloups calés sur l'affichage « Je t'écoute » : début et fin de l'écoute.
            if s == "listening":
                self.capture.emit(True)
            elif was == "listening":
                self.capture.emit(False)
            self.state_changed.emit(s)

    def _clear_partial(self) -> None:
        self._partial_gen += 1
        self.partial.emit("")

    def _partial_job(self, audio, gen: int) -> None:
        """Aperçu en direct : transcription rapide (petit modèle) de ce qui a été dit jusqu'ici."""
        text = ""
        try:
            model = self._wake_model or self._model
            segments, _ = model.transcribe(
                prep_audio(audio),
                language=self.cfg.get("language", "fr"),
                beam_size=1,
                temperature=(0.0, 0.2, 0.4),
                compression_ratio_threshold=2.2,
                condition_on_previous_text=False,
                vad_filter=False,
                initial_prompt=self.cfg.get("command_prompt") or None,
            )
            parts = [seg.text.strip() for seg in segments
                     if not (seg.no_speech_prob > 0.7 and seg.avg_logprob < -1.0)]
            text = apply_corrections(collapse_repeats(" ".join(parts).strip()), self.cfg.get("corrections"))
        except Exception:  # noqa: BLE001
            text = ""
        finally:
            self._partial_busy = False
        if text and gen == self._partial_gen and not is_hallucination(text):
            self.partial.emit((self._prefix + " " + text).strip())

    def _on_audio(self, indata, frames, time_info, status) -> None:
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def _open_model(self, name: str, device: str, compute: str):
        """Ouvre un modèle Whisper en réessayant : un autre programme (ou un antivirus) peut verrouiller le fichier un instant.

        D'abord uniquement depuis le cache local (rapide, sans réseau, sans réécrire les liens du cache), puis avec
        téléchargement si le modèle n'est pas encore là.
        """
        from faster_whisper import WhisperModel

        last = None
        for attempt in range(4):
            _heal_model_cache(name)
            for local_only in (True, False):
                try:
                    return WhisperModel(name, device=device, compute_type=compute, local_files_only=local_only)
                except Exception as e:  # noqa: BLE001
                    last = e
            # Le cache de Windows pose problème (liens cassés, « point de montage non approuvé »...) :
            # on télécharge le modèle dans le dossier de Jimmy, en vrais fichiers, sans liens.
            try:
                from faster_whisper.utils import download_model
                folder = _own_model_dir(name)
                path = download_model(name, output_dir=folder)
                return WhisperModel(path, device=device, compute_type=compute)
            except Exception as e:  # noqa: BLE001
                last = e
            self.status.emit(f"Le modèle vocal n'a pas pu s'ouvrir ({last}). Nouvelle tentative dans {2 * (attempt + 1)} s…")
            time.sleep(2 * (attempt + 1))
        raise last

    def _load_model(self) -> None:
        if self._model is not None:
            return          # déjà chargé (relance du micro seulement)
        self._set_state("loading")
        self.status.emit(
            "Chargement de la reconnaissance vocale. Au tout premier lancement, le modèle se "
            "télécharge (5 à 10 minutes selon ta connexion) : laisse la fenêtre ouverte."
        )
        _add_cuda_dlls()
        # Téléchargement classique et sans liens symboliques : plus fiable sous Windows (antivirus, réseaux filtrés).
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from faster_whisper import WhisperModel

        device = self.cfg.get("whisper_device", "cpu")
        main_name = self.cfg.get("whisper_model", "small")
        if main_name == "auto" or device == "auto":
            auto_model, auto_dev = auto_choice(self.cfg)
            if main_name == "auto":
                main_name = auto_model
            if device == "auto":
                device = auto_dev
            self.status.emit(f"Reconnaissance vocale : modèle « {main_name} » sur {'la carte graphique' if device == 'cuda' else 'le processeur'}.")
        if device == "cuda" and not _cuda_ok():
            self.status.emit("Carte graphique non utilisable (bibliothèques NVIDIA absentes) : reconnaissance sur le processeur. "
                             "Réglages › Audio permet de télécharger l'accélération carte graphique.")
            device = "cpu"
            if main_name == "large-v3-turbo":
                main_name = "medium"      # trop lent sur processeur
        try:
            self._model = self._open_model(main_name, device, _compute(device))
        except Exception as e:  # noqa: BLE001
            if device == "cpu":
                raise
            # Carte graphique indisponible (pilote, bibliothèques CUDA...) : on retombe sur le processeur.
            self.status.emit(f"Carte graphique non utilisable ({e}) : reconnaissance vocale sur le processeur.")
            device, main_name = "cpu", "small"
            self._model = self._open_model(main_name, device, _compute(device))
        compute = _compute(device)
        wake_name = self.cfg.get("wake_whisper_model") or main_name
        self._wake_model = self._model
        if wake_name != main_name:
            try:
                self._wake_model = self._open_model(wake_name, device, compute)
            except Exception:  # noqa: BLE001
                self._wake_model = self._model
        self.status.emit("Reconnaissance vocale prête.")

    @property
    def ready(self) -> bool:
        return self._model is not None

    def retry(self) -> bool:
        """Relance le chargement du modèle vocal s'il a échoué (clic sur Parler). Renvoie True si relancé."""
        if (self._model is None or getattr(self, "_wd_giveup", False)) and not (self._thread and self._thread.is_alive()):
            self._wd_giveup = False
            self.start()
            return True
        return False

    def _run(self) -> None:
        # Le téléchargement peut échouer (réseau coupé, antivirus, disque plein) : on réessaie plusieurs fois,
        # le téléchargement reprend là où il s'était arrêté.
        last = None
        for attempt in range(5):
            if self._stop.is_set():
                return
            try:
                self._load_model()
                last = None
                break
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < 4:
                    wait = 5 * (attempt + 1)
                    self.status.emit(f"Chargement vocal interrompu ({type(e).__name__}: {e}). Nouvel essai dans {wait} s…")
                    time.sleep(wait)
        if last is not None:
            self.error.emit(
                f"Impossible de charger la reconnaissance vocale : {type(last).__name__}: {last}. "
                "Vérifie ta connexion internet, puis clique sur « Parler » pour réessayer."
            )
            self._set_state("idle")
            return
        while not self._stop.is_set():
            self._restart.clear()
            name = self.cfg.get("mic_device")
            device = resolve(name, "input")
            try:
                with sd.InputStream(
                    samplerate=SR,
                    channels=1,
                    dtype="float32",
                    blocksize=BLOCK,
                    device=device,
                    callback=self._on_audio,
                ):
                    if not getattr(self, "_announced", False):   # une seule fois par lancement
                        self._announced = True
                        self.status.emit(f"Micro actif : {name or 'micro par défaut de Windows'}.")
                    self._loop()
            except Exception as e:  # noqa: BLE001
                if device is not None:
                    self.error.emit(f"Micro « {name} » indisponible ({e}), micro par défaut utilisé.")
                    self.cfg.set("mic_device", None)
                    continue
                self.error.emit(f"Problème de micro : {e}")
                self._set_state("idle")
                return
            while not self._q.empty():  # vide le son de l'ancien micro
                self._q.get_nowait()
            if getattr(self, "_wd_giveup", False):
                return          # micro mort : on s'arrête là (un clic sur « Parler » relance, voir retry)

    def _loop(self) -> None:
        end_silence_cmd = float(self.cfg.get("silence_seconds", 1.2))
        end_silence_wake = float(self.cfg.get("wake_silence_seconds", 0.45))
        # Après une phrase, temps laissé pour reprendre avant l'envoi (plus long si elle semble coupée).
        grace = float(self.cfg.get("continue_seconds", 1.5))
        grace_unfinished = float(self.cfg.get("continue_unfinished_seconds", 4.0))
        sens = max(0.3, float(self.cfg.get("mic_sensitivity", 1.0)))
        noise = 0.006
        pre = deque(maxlen=20)      # ≈ 0,65 s gardées avant le début détecté : plus de premières syllabes perdues
        buf = []
        in_speech = False
        silence = 0.0
        mode = "wake"
        cmd_started = 0.0
        was_muted = False
        last_partial = 0.0

        t_open, got_sound, warned = time.time(), False, False
        last_block = time.time()
        while not self._stop.is_set() and not self._restart.is_set():
            try:
                block = self._q.get(timeout=0.2)
                last_block = time.time()
                self._wd_fail = 0
            except queue.Empty:
                if time.time() - last_block > 3.0 and not self._paused.is_set():
                    # Plus aucun son depuis 3 s : le micro (ou son pilote, un casque sans fil endormi...) ne répond plus.
                    self._wd_fail = getattr(self, "_wd_fail", 0) + 1
                    if self._wd_fail <= 4:
                        self.status.emit("Le micro ne transmet plus de son : je le rouvre.")
                        self._restart.set()
                    else:
                        self.error.emit("Le micro ne répond plus. Vérifie qu'il est branché / allumé, ou choisis-en un autre dans Réglages › Audio, puis clique sur Parler.")
                        self._set_state("idle")
                        self._wd_fail = 0
                        self._wd_giveup = True
                        self._restart.set()
                    last_block = time.time()
                continue
            # Micro muet côté Windows (confidentialité, mauvais périphérique) : le flux ne contient que des zéros exacts.
            if not got_sound and float(np.max(np.abs(block))) > 0:
                got_sound = True
            if not got_sound and not warned and time.time() - t_open > 6:
                warned = True
                self.error.emit(
                    "Le micro ne transmet aucun son. Vérifie Paramètres Windows › Confidentialité › Microphone "
                    "(« Autoriser les applications de bureau »), ou choisis un autre micro dans Réglages › Audio."
                )

            if self._paused.is_set():
                self._partial_gen += 1
                in_speech, buf, silence = False, [], 0.0
                if self.state == "listening":
                    # l'écoute en cours est coupée par la pause (Jimmy se met au travail) : le bouton ne reste pas sur « J'écoute »
                    mode, self._prefix = "wake", ""
                    self._set_state("wake" if self._wake_on else "idle")
                pre.clear()
                continue

            if not self._muted.is_set():
                was_muted = False
            if self._flush.is_set() or (self._muted.is_set() and not was_muted):
                # Micro coupé / 2e clic sur Parler : on ne capte plus rien de nouveau, mais ce qui a
                # déjà été dit n'est pas perdu (phrase en cours + texte déjà reconnu).
                self._flush.clear()
                self._partial_gen += 1
                was_muted = self._muted.is_set()
                if mode == "command":
                    if in_speech and buf and (len(buf) * BLOCK_S - silence) >= 0.35:
                        self._handle(np.concatenate(buf), "command", cmd_started)
                    if self._prefix:
                        text, self._prefix = self._prefix, ""
                        in_speech, buf, silence = False, [], 0.0
                        pre.clear()
                        mode = "wake"
                        self._emit_command(text, followup=self._followup)
                        continue
                in_speech, buf, silence = False, [], 0.0
                pre.clear()
                mode, self._prefix = "wake", ""
                self._followup, self._cmd_timeout = False, 10.0
                self._clear_partial()

            if self._muted.is_set():
                in_speech, buf, silence = False, [], 0.0
                pre.clear()
                mode, self._prefix = "wake", ""
                self._set_state("muted")
                continue

            if self._reset.is_set():
                self._reset.clear()
                in_speech, buf, silence = False, [], 0.0
                pre.clear()
                mode = "wake"
                self._prefix = ""
                self._followup, self._cmd_timeout = False, 10.0
                self._clear_partial()

            if self._force.is_set():
                self._force.clear()
                self._prefix = ""
                self._followup = self._force_followup
                self._cmd_timeout = self._force_timeout
                mode = "command"
                cmd_started = time.time()
                in_speech, buf, silence = False, [], 0.0
                pre.clear()

            if mode == "wake":
                self._set_state("wake" if self._wake_on else "idle")
                if not self._wake_on:
                    continue
            else:
                self._set_state("listening")

            rms = float(np.sqrt(np.mean(block * block)))
            self.level.emit(rms)
            thr = max(0.010, noise * 3.2) / sens
            # Une fois lancé, on reste en « parole » même quand la voix baisse en fin de mot.
            is_speech = rms > (thr * 0.6 if in_speech else thr)
            if not in_speech:
                noise = 0.97 * noise + 0.03 * min(rms, 0.05)

            if not in_speech:
                pre.append(block)
                if is_speech:
                    in_speech = True
                    buf = list(pre)
                    pre.clear()
                    silence = 0.0
                elif mode == "command" and self._prefix:
                    # Phrase entendue puis un vrai silence : on n'envoie qu'après le délai de reprise.
                    wait = grace_unfinished if looks_unfinished(self._prefix) else grace
                    if time.time() - cmd_started > wait:
                        command, self._prefix = self._prefix, ""
                        self._emit_command(command, followup=self._followup)
                        mode = "wake"
                elif mode == "command" and time.time() - cmd_started > self._cmd_timeout:
                    mode = "wake"
                    self._clear_partial()
                    if not self._followup:
                        self.status.emit("Je n'ai rien entendu, retour en veille.")
                    self._followup, self._cmd_timeout = False, 10.0
                continue

            buf.append(block)
            silence = 0.0 if is_speech else silence + BLOCK_S
            total = len(buf) * BLOCK_S
            if (mode == "command" and not self._partial_busy and total >= 0.5
                    and time.time() - last_partial >= 0.7):
                last_partial = time.time()
                self._partial_busy = True
                threading.Thread(target=self._partial_job, args=(np.concatenate(buf), self._partial_gen),
                                 daemon=True).start()
            end_sil = end_silence_cmd if mode == "command" else end_silence_wake
            max_len = 120.0 if mode == "command" else 12.0
            if silence >= end_sil or total >= max_len:
                speech_len = total - silence
                audio = np.concatenate(buf)
                in_speech, buf, silence = False, [], 0.0
                if speech_len >= 0.35:
                    self._partial_gen += 1
                    mode, cmd_started = self._handle(audio, mode, cmd_started)
                    if mode == "command":
                        self.partial.emit(self._prefix)   # le texte validé reste affiché

    def _handle(self, audio, mode: str, cmd_started: float):
        # Phrase reprise après une pause : on retranscrit TOUT ce qui a été dit depuis le début avec le modèle
        # précis (le contexte corrige les mots mal compris) au lieu de recoller des morceaux déjà interprétés.
        if mode == "command" and not self._prefix:
            self._cmd_audio, self._cmd_refinable = [], True
        refine = (mode == "command" and self._cmd_refinable and bool(self._cmd_audio)
                  and sum(len(a) for a in self._cmd_audio) + len(audio) <= REFINE_MAX_S * SR)
        text = self._transcribe(np.concatenate(self._cmd_audio + [audio]) if refine else audio, mode)
        if not text or is_hallucination(text):
            return mode, cmd_started

        words = self.cfg.get("wake_words") or ["jimmy"]
        woke, rest = extract_wake(text, words)
        if woke:
            self.last_wake = self._wake_kind(text, words)
        if mode == "wake":
            if not woke:
                return mode, cmd_started
            self.woke.emit()
            if len(rest) >= 2:                 # « Jimmy, mets de la musique »
                # Le petit modèle a repéré « Jimmy » : on retranscrit avec le modèle précis.
                if self._wake_model is not self._model:
                    full = self._transcribe(audio, "command")
                    w2, r2 = extract_wake(full, words)
                    if w2 and len(r2) >= 2:
                        rest = r2
                # On n'envoie pas tout de suite : si tu reprends ta phrase après une courte
                # pause, la suite y est ajoutée (plus de coupure en plein milieu).
                self._prefix = rest
                self._cmd_audio, self._cmd_refinable = [audio], True
            self._set_state("listening")       # « Jimmy » seul : j'attends la suite
            return "command", time.time()

        command = rest if woke else text
        if woke:
            self._followup = False             # « Jimmy » dit : la phrase lui est bien adressée
        if len(command) < 2:
            return mode, time.time()
        # On garde la phrase et on continue d'écouter : si tu reprends après une pause,
        # la suite est ajoutée. L'envoi se fait après le délai de reprise (voir _loop).
        if refine:
            self._prefix = command                       # tout a été réécouté d'un bloc : ce texte remplace l'ancien
            self._cmd_audio.append(audio)
        else:
            self._prefix = (self._prefix + " " + command).strip()
            if self._cmd_refinable and sum(len(a) for a in self._cmd_audio) + len(audio) <= REFINE_MAX_S * SR:
                self._cmd_audio.append(audio)
            else:
                self._cmd_refinable = False              # trop long (ou texte venu d'ailleurs) : on recolle les morceaux
        return "command", time.time()

    def _emit_command(self, text: str, followup: bool = False) -> None:
        self._paused.set()  # on coupe l'écoute avant d'envoyer, pour ne pas capter la réponse
        if self.state == "listening":
            self.state = "sent"           # fin d'écoute immédiate (le prochain « listening » rebloupe)
            self.capture.emit(False)
        self.last_followup = followup
        self._followup, self._cmd_timeout = False, 10.0
        self.heard.emit(text)

    def _fallback_cpu(self) -> bool:
        """La carte graphique ne marche pas pour de vrai : on repasse sur le processeur (une seule fois)."""
        if getattr(self, "_cpu_fallback_done", False):
            return False
        self._cpu_fallback_done = True
        try:
            self.status.emit("La carte graphique n'a pas pu transcrire : je passe sur le processeur.")
            self._model = self._open_model("medium", "cpu", "int8")
            self._wake_model = self._model
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _wake_kind(text: str, words) -> str:
        """Quel mot d'éveil a été dit : le prénom de l'IA locale (Aurélie) ou celui de Jimmy."""
        from textutils import fold
        for w in words:
            ok, _ = extract_wake(text, [w])
            if ok:
                return "local" if fold(str(w)).replace(" ", "").endswith("aurelie") else "claude"
        return "claude"

    def transcribe_bytes(self, data: bytes) -> str:
        """Voix du téléphone -> texte, avec le MÊME modèle précis, le même vocabulaire et les mêmes corrections que le micro du PC."""
        if self._model is None:
            raise RuntimeError("La reconnaissance vocale du PC n'est pas encore prête.")
        audio = decode_audio_bytes(data)
        if audio.size < 1600:                       # moins de 0,1 s
            return ""
        with self._phone_lock:
            text = self._transcribe(audio, "command")
        if not text or is_hallucination(text):
            return ""
        from textutils import ensure_final_punct
        return ensure_final_punct(text)

    def _vocab(self) -> str:
        """Mots à privilégier : mots d'éveil, vocabulaire de l'utilisateur (réglage « vocab », séparé par des virgules)."""
        words = [str(w).strip() for w in (self.cfg.get("wake_words") or []) if str(w).strip()]
        extra = self.cfg.get("vocab") or ""
        words += [w.strip() for w in (extra if isinstance(extra, list) else str(extra).split(",")) if str(w).strip()]
        seen, out = set(), []
        for w in ["Jimmy", "Claude"] + words:
            if w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
        return ", ".join(out)[:240]

    def _transcribe(self, audio, mode: str) -> str:
        if mode == "command":
            model, prompt = self._model, self.cfg.get("command_prompt")
        else:
            model, prompt = self._wake_model, "Jimmy."
        try:
            audio = prep_audio(audio)
            cmd = mode == "command"
            kw = {}
            vocab = self._vocab()
            if cmd and vocab:
                kw["hotwords"] = vocab           # noms propres et mots techniques de l'utilisateur : mieux reconnus
            if cmd:
                kw.update(best_of=5, patience=1.2, vad_filter=True,
                          vad_parameters=dict(threshold=0.4, min_silence_duration_ms=600, speech_pad_ms=350))
            segments, _ = model.transcribe(
                audio,
                language=self.cfg.get("language", "fr"),
                beam_size=5 if cmd else 1,               # plus précis pour la commande, rapide pour « Jimmy »
                temperature=(0.0, 0.2, 0.4),             # réessaie plus « libre » si Whisper boucle
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                initial_prompt=prompt or None,
                **kw,
            )
            parts = []
            for s in segments:
                if s.no_speech_prob > 0.7 and s.avg_logprob < -1.0:
                    continue
                parts.append(s.text.strip())
            return apply_corrections(collapse_repeats(" ".join(parts).strip()), self.cfg.get("corrections"))
        except Exception as e:  # noqa: BLE001
            if any(k in str(e).lower() for k in ("cublas", "cudnn", "cuda")) and self._fallback_cpu():
                return self._transcribe(audio, mode)
            self.error.emit(f"Erreur de transcription : {e}")
            return ""
