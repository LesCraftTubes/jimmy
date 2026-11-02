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


def _compute(device: str) -> str:
    return "int8" if device in ("cpu", "auto") else "float16"


def _add_cuda_dlls() -> None:
    """Rend visibles les bibliothèques CUDA installées par pip (nvidia-cublas-cu12, nvidia-cudnn-cu12)."""
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
        # ~1 min de son en attente : rien n'est perdu pendant qu'une phrase est transcrite.
        self._q = queue.Queue(maxsize=2000)
        self._thread = None
        self._model = None
        self._wake_model = None
        self._prefix = ""             # début de phrase entendu juste après « Jimmy »
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
                audio,
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
            for local_only in (True, False):
                try:
                    return WhisperModel(name, device=device, compute_type=compute, local_files_only=local_only)
                except Exception as e:  # noqa: BLE001
                    last = e
            self.status.emit(f"Le modèle vocal n'a pas pu s'ouvrir ({last}). Nouvelle tentative dans {2 * (attempt + 1)} s…")
            time.sleep(2 * (attempt + 1))
        raise last

    def _load_model(self) -> None:
        self._set_state("loading")
        self.status.emit(
            "Chargement de la reconnaissance vocale. Au tout premier lancement, le modèle se "
            "télécharge (5 à 10 minutes selon ta connexion) : laisse la fenêtre ouverte."
        )
        _add_cuda_dlls()
        from faster_whisper import WhisperModel

        device = self.cfg.get("whisper_device", "cpu")
        main_name = self.cfg.get("whisper_model", "small")
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

    def _run(self) -> None:
        try:
            self._load_model()
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Impossible de charger la reconnaissance vocale : {e}")
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

    def _loop(self) -> None:
        end_silence_cmd = float(self.cfg.get("silence_seconds", 1.2))
        end_silence_wake = float(self.cfg.get("wake_silence_seconds", 0.45))
        # Après une phrase, temps laissé pour reprendre avant l'envoi (plus long si elle semble coupée).
        grace = float(self.cfg.get("continue_seconds", 1.5))
        grace_unfinished = float(self.cfg.get("continue_unfinished_seconds", 4.0))
        sens = max(0.3, float(self.cfg.get("mic_sensitivity", 1.0)))
        noise = 0.006
        pre = deque(maxlen=10)
        buf = []
        in_speech = False
        silence = 0.0
        mode = "wake"
        cmd_started = 0.0
        was_muted = False
        last_partial = 0.0

        t_open, got_sound, warned = time.time(), False, False
        while not self._stop.is_set() and not self._restart.is_set():
            try:
                block = self._q.get(timeout=0.2)
            except queue.Empty:
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
        text = self._transcribe(audio, mode)
        if not text or is_hallucination(text):
            return mode, cmd_started

        words = self.cfg.get("wake_words") or ["jimmy"]
        woke, rest = extract_wake(text, words)
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
            self._set_state("listening")       # « Jimmy » seul : j'attends la suite
            return "command", time.time()

        command = rest if woke else text
        if woke:
            self._followup = False             # « Jimmy » dit : la phrase lui est bien adressée
        if len(command) < 2:
            return mode, time.time()
        # On garde la phrase et on continue d'écouter : si tu reprends après une pause,
        # la suite est ajoutée. L'envoi se fait après le délai de reprise (voir _loop).
        self._prefix = (self._prefix + " " + command).strip()
        return "command", time.time()

    def _emit_command(self, text: str, followup: bool = False) -> None:
        self._paused.set()  # on coupe l'écoute avant d'envoyer, pour ne pas capter la réponse
        if self.state == "listening":
            self.state = "sent"           # fin d'écoute immédiate (le prochain « listening » rebloupe)
            self.capture.emit(False)
        self.last_followup = followup
        self._followup, self._cmd_timeout = False, 10.0
        self.heard.emit(text)

    def _transcribe(self, audio, mode: str) -> str:
        if mode == "command":
            model, prompt = self._model, self.cfg.get("command_prompt")
        else:
            model, prompt = self._wake_model, "Jimmy."
        try:
            segments, _ = model.transcribe(
                audio,
                language=self.cfg.get("language", "fr"),
                beam_size=5 if mode == "command" else 1,   # plus précis pour la commande, rapide pour « Jimmy »
                temperature=(0.0, 0.2, 0.4),             # réessaie plus « libre » si Whisper boucle
                compression_ratio_threshold=2.2,
                condition_on_previous_text=False,
                vad_filter=False,
                initial_prompt=prompt or None,
            )
            parts = []
            for s in segments:
                if s.no_speech_prob > 0.7 and s.avg_logprob < -1.0:
                    continue
                parts.append(s.text.strip())
            return apply_corrections(collapse_repeats(" ".join(parts).strip()), self.cfg.get("corrections"))
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Erreur de transcription : {e}")
            return ""
