"""Fenêtre Réglages : audio, écoute, Claude (coût, étapes) et fenêtre."""
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import audio_devices
from config import ACCENTS, MODEL_NAMES

DEFAULT_LABEL = "Par défaut (Windows)"
ECO_MODELS = [
    (f"{MODEL_NAMES['sonnet']} (équilibré)", "sonnet"),
    (f"{MODEL_NAMES['haiku']} (le moins cher)", "haiku"),
]
PERMISSION_MODES = [
    ("Modifie les fichiers sans demander", "acceptEdits"),
    ("Aucune demande (tout autorisé)", "bypassPermissions"),
    ("Demande à chaque modification", "default"),
]
WHISPER_MODELS = ["tiny", "base", "small", "medium"]


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


def _combo(items, current) -> QComboBox:
    box = QComboBox()
    for label, value in items:
        box.addItem(label, value)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


class SettingsDialog(QDialog):
    def __init__(self, cfg, speaker, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.speaker = speaker
        self.setWindowTitle("Réglages de Jimmy")
        self.setMinimumWidth(620)

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._audio_tab(), "Audio")
        tabs.addTab(self._listen_tab(), "Écoute")
        tabs.addTab(self._claude_tab(), "Claude")
        tabs.addTab(self._window_tab(), "Fenêtre")
        tabs.addTab(self._look_tab(), "Apparence")
        lay.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Enregistrer")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ onglets
    @staticmethod
    def _form_page():
        page = QWidget()
        lay = QVBoxLayout(page)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        lay.addLayout(form)
        return page, lay, form

    def _audio_tab(self) -> QWidget:
        cfg = self.cfg
        page, lay, form = self._form_page()
        self.mic = self._device_box("input", cfg.get("mic_device"))
        form.addRow("Micro", self.mic)

        out_row = QHBoxLayout()
        self.out = self._device_box("output", cfg.get("speaker_device"))
        test = QPushButton("Tester")
        test.clicked.connect(self._test_output)
        out_row.addWidget(self.out, 1)
        out_row.addWidget(test)
        form.addRow("Sortie (voix de Jimmy)", out_row)

        sens_row = QHBoxLayout()
        self.sens = QSlider(Qt.Horizontal)
        self.sens.setRange(5, 30)   # x0.1
        self.sens.setValue(int(round(float(cfg.get("mic_sensitivity", 1.0)) * 10)))
        self.sens_lbl = QLabel()
        self.sens.valueChanged.connect(lambda v: self.sens_lbl.setText(f"x{v / 10:.1f}"))
        self.sens_lbl.setText(f"x{self.sens.value() / 10:.1f}")
        sens_row.addWidget(self.sens, 1)
        sens_row.addWidget(self.sens_lbl)
        form.addRow("Sensibilité du micro", sens_row)

        self.silence = self._spin(cfg.get("silence_seconds", 1.2), 0.6, 4.0)
        self.silence.setToolTip("Silence qui marque la fin d'un morceau de phrase.")
        form.addRow("Fin de phrase (s)", self.silence)
        self.grace = self._spin(cfg.get("continue_seconds", 1.5), 0.5, 6.0)
        self.grace.setToolTip("Après une pause, temps laissé pour reprendre avant l'envoi.")
        form.addRow("Temps pour reprendre (s)", self.grace)
        self.grace_unf = self._spin(cfg.get("continue_unfinished_seconds", 4.0), 1.0, 10.0)
        self.grace_unf.setToolTip("Pareil, quand la phrase semble coupée (« pour que je… »).")
        form.addRow("… si phrase coupée (s)", self.grace_unf)
        lay.addWidget(_hint(
            "Sensibilité plus haute = capte les voix basses (mais aussi plus de bruit). "
            "Plus de temps pour reprendre = jamais coupé, mais réponse un peu plus tardive."
        ))
        self.diag_btn = QPushButton("Diagnostic vocal (micro, modèle, reconnaissance)")
        self.diag_btn.setToolTip("Teste le micro, le modèle de reconnaissance et une phrase parlée de test (environ 30 secondes).")
        self.diag_btn.clicked.connect(self._run_diag)
        lay.addWidget(self.diag_btn)
        lay.addStretch(1)
        return page

    # ---------------------------------------------------------- diagnostic vocal
    def _run_diag(self) -> None:
        """Lance `Jimmy --selftest` dans un processus à part (il ne touche pas au micro de la fenêtre) et montre le résultat."""
        from config import data_dir

        class _Done(QObject):
            done = Signal(str)

        self._diag_sig = _Done()
        self._diag_sig.done.connect(self._show_diag)
        self.diag_btn.setEnabled(False)
        self.diag_btn.setText("Diagnostic en cours (environ 30 secondes)…")

        def work() -> None:
            cmd = [sys.executable, "--selftest"] if getattr(sys, "frozen", False) else [sys.executable, str(__import__("config").app_dir() / "main.py"), "--selftest"]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                subprocess.run(cmd, capture_output=True, timeout=240, creationflags=flags)
                text = (data_dir() / "selftest.txt").read_text(encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                text = f"Le diagnostic n'a pas pu se terminer : {e}"
            self._diag_sig.done.emit(text)

        threading.Thread(target=work, daemon=True).start()

    def _show_diag(self, text: str) -> None:
        self.diag_btn.setEnabled(True)
        self.diag_btn.setText("Diagnostic vocal (micro, modèle, reconnaissance)")
        bad = "[ERR]" in text
        box = QMessageBox(self)
        box.setWindowTitle("Diagnostic vocal")
        box.setIcon(QMessageBox.Warning if bad else QMessageBox.Information)
        box.setText("Un test a échoué." if bad else "Tout fonctionne : micro, modèle et reconnaissance.")
        box.setDetailedText(text)
        box.exec()

    def _listen_tab(self) -> QWidget:
        cfg = self.cfg
        page, lay, form = self._form_page()
        words = cfg.get("wake_words") or ["jimmy"]
        self.wake = QLineEdit(", ".join(str(w) for w in words))
        self.wake.setPlaceholderText("jimmy, hey jimmy")
        form.addRow("Mot d'éveil", self.wake)
        self.followup = QSpinBox()
        self.followup.setRange(0, 20)
        self.followup.setSuffix(" s")
        self.followup.setValue(int(cfg.get("followup_seconds", 4)))
        form.addRow("Réécoute après une réponse", self.followup)
        self.question = QSpinBox()
        self.question.setRange(0, 30)
        self.question.setSuffix(" s")
        self.question.setValue(int(cfg.get("question_listen_seconds", 8)))
        form.addRow("Réécoute après une question", self.question)
        self.wake_beep = QCheckBox("Petit bip quand le mot d'éveil est reconnu")
        self.wake_beep.setChecked(bool(cfg.get("wake_beep", True)))
        form.addRow("", self.wake_beep)
        self.capture = QCheckBox("« Bloup » au début et à la fin de l'écoute")
        self.capture.setChecked(bool(cfg.get("capture_sounds", True)))
        form.addRow("", self.capture)
        self.whisper = QComboBox()
        self.whisper.addItems(WHISPER_MODELS)
        self.whisper.setCurrentText(cfg.get("whisper_model", "small"))
        form.addRow("Précision de la reconnaissance", self.whisper)
        lay.addWidget(_hint(
            "La réécoute ne marche que si le bouton « Relance » est allumé. "
            "Reconnaissance : tiny = rapide, medium = précis mais lent (appliqué au prochain lancement)."
        ))
        lay.addStretch(1)
        return page

    def _claude_tab(self) -> QWidget:
        cfg = self.cfg
        page, lay, form = self._form_page()
        self.steps = QCheckBox("Afficher les étapes importantes (analyse, modifications) — sans les commandes")
        self.steps.setChecked(bool(cfg.get("show_steps", True)))
        form.addRow("", self.steps)
        self.eco = QCheckBox("Économie auto : bascule sur un modèle moins cher près de la limite")
        self.eco.setChecked(bool(cfg.get("eco_auto", False)))
        form.addRow("", self.eco)
        self.eco_threshold = QSpinBox()
        self.eco_threshold.setRange(30, 99)
        self.eco_threshold.setSuffix(" % de la session")
        self.eco_threshold.setValue(int(cfg.get("eco_threshold", 85)))
        form.addRow("Seuil d'économie", self.eco_threshold)
        self.eco_model = _combo(ECO_MODELS, cfg.get("eco_model", "sonnet"))
        form.addRow("Modèle d'économie", self.eco_model)
        self.perm = _combo(PERMISSION_MODES, cfg.get("permission_mode", "acceptEdits"))
        form.addRow("Permissions", self.perm)
        self.extra = QPlainTextEdit(str(cfg.get("extra_instructions", "")))
        self.extra.setPlaceholderText("Infos utiles pour Jimmy : ton serveur, ton site, tes habitudes…")
        self.extra.setFixedHeight(110)
        form.addRow("Consignes en plus", self.extra)
        self.projects = QPlainTextEdit(str(cfg.get("projects_text", "")))
        self.projects.setPlaceholderText(
            "Un projet par ligne : nom = chemin (à quoi il sert)\n"
            "ex : MonSite = C:\\Projets\\monsite (site web en PHP)")
        self.projects.setFixedHeight(110)
        form.addRow("Carte des dossiers", self.projects)
        self.ctx_auto = QCheckBox("Quand la discussion est presque pleine, reprendre le contexte dans une nouvelle")
        self.ctx_auto.setChecked(bool(cfg.get("ctx_auto", True)))
        form.addRow("", self.ctx_auto)
        self.ctx_th = QSpinBox()
        self.ctx_th.setRange(50, 98)
        self.ctx_th.setSuffix(" % de la limite")
        self.ctx_th.setValue(int(cfg.get("ctx_threshold", 70)))
        form.addRow("Seuil de reprise", self.ctx_th)
        self.ctx_limit = QSpinBox()
        self.ctx_limit.setRange(100_000, 1_000_000)
        self.ctx_limit.setSingleStep(50_000)
        self.ctx_limit.setSuffix(" tokens")
        self.ctx_limit.setValue(int(cfg.get("context_limit", 1000000)))
        form.addRow("Limite de contexte", self.ctx_limit)
        self.lean_mcp = QCheckBox("Économie : plugins (Playwright, DevTools…) chargés seulement si besoin")
        self.lean_mcp.setChecked(bool(cfg.get("lean_mcp", False)))
        form.addRow("", self.lean_mcp)
        lay.addWidget(_hint(
            "Le modèle et l'effort se changent directement en haut de la fenêtre. "
            "Haiku et un effort bas consomment beaucoup moins de ton quota Pro."
        ))
        lay.addStretch(1)
        return page

    def _window_tab(self) -> QWidget:
        page, lay, form = self._form_page()
        self.maximized = QCheckBox("Ouvrir Jimmy en grand au démarrage")
        self.maximized.setChecked(bool(self.cfg.get("start_maximized", True)))
        form.addRow("", self.maximized)
        lay.addStretch(1)
        return page

    def _look_tab(self) -> QWidget:
        cfg = self.cfg
        page, lay, form = self._form_page()
        self.accent = QComboBox()
        for name in ACCENTS:
            self.accent.addItem(name, name)
        self.accent.setCurrentIndex(max(0, self.accent.findData(cfg.get("accent", "Cyan néon"))))
        form.addRow("Couleur du thème", self.accent)
        self.fx = QCheckBox("Animations : balayages, éclairs sur les boutons, transitions")
        self.fx.setChecked(bool(cfg.get("effects", True)))
        form.addRow("", self.fx)
        self.orb_sides = QCheckBox("Flux de données à gauche et à droite de l'orbe")
        self.orb_sides.setChecked(bool(cfg.get("orb_sides", True)))
        form.addRow("", self.orb_sides)
        self.orb_sats = QCheckBox("Satellites lumineux autour de l'orbe")
        self.orb_sats.setChecked(bool(cfg.get("orb_sats", True)))
        form.addRow("", self.orb_sats)
        self.micro = QCheckBox("Glitchs de cyberpsychose qui apparaissent de temps en temps")
        self.micro.setChecked(bool(cfg.get("micro_glitch", True)))
        form.addRow("", self.micro)
        self.voice_glitch = QCheckBox("Petits glitchs dans la voix pendant la cyberpsychose")
        self.voice_glitch.setChecked(bool(cfg.get("voice_glitch", True)))
        form.addRow("", self.voice_glitch)
        self.glitch_freq = QComboBox()
        for name in ("Rare", "Moyenne", "Fréquente"):
            self.glitch_freq.addItem(name, name)
        self.glitch_freq.setCurrentIndex(max(0, self.glitch_freq.findData(cfg.get("glitch_freq", "Moyenne"))))
        form.addRow("Fréquence des glitchs", self.glitch_freq)
        self.psy_on = QCheckBox("Cyberpsychose quand le quota de session est presque épuisé")
        self.psy_on.setChecked(bool(cfg.get("psy_enabled", True)))
        form.addRow("", self.psy_on)
        self.psy_th = QSpinBox()
        self.psy_th.setRange(50, 99)
        self.psy_th.setSuffix(" % de la session")
        self.psy_th.setValue(int(cfg.get("psy_threshold", 80)))
        form.addRow("Seuil de la cyberpsychose", self.psy_th)
        self.chat_font = QSpinBox()
        self.chat_font.setRange(11, 24)
        self.chat_font.setSuffix(" px")
        self.chat_font.setValue(int(cfg.get("chat_font", 15)))
        form.addRow("Taille du texte", self.chat_font)
        self.live = QCheckBox("Écrire ce que je dis en direct dans la zone de saisie")
        self.live.setChecked(bool(cfg.get("live_preview", True)))
        form.addRow("", self.live)
        self.speed = QSpinBox()
        self.speed.setRange(-20, 40)
        self.speed.setSuffix(" %")
        self.speed.setValue(int(cfg.get("tts_speed_bonus", 24)))
        form.addRow("Vitesse de la voix", self.speed)
        lay.addWidget(_hint("Tout ça est de l'affichage : aucun effet ne consomme de tokens."))
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------ helpers
    def _device_box(self, kind: str, current) -> QComboBox:
        box = QComboBox()
        box.addItem(DEFAULT_LABEL, None)
        try:
            names = audio_devices.list_devices(kind)
        except Exception:  # noqa: BLE001
            names = []
        for n in names:
            box.addItem(n, n)
        if current and current not in names:
            box.addItem(f"{current} (débranché ?)", current)
        idx = box.findData(current) if current else 0
        box.setCurrentIndex(max(0, idx))
        return box

    @staticmethod
    def _spin(value, lo, hi) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(0.1)
        s.setDecimals(1)
        s.setValue(float(value))
        return s

    def _test_output(self) -> None:
        saved = self.cfg.get("speaker_device")
        self.cfg.data["speaker_device"] = self.out.currentData()
        self.speaker.beep(660, 120)
        self.cfg.data["speaker_device"] = saved

    def values(self) -> dict:
        words = [w.strip() for w in self.wake.text().split(",") if w.strip()] or ["jimmy"]
        return {
            "mic_device": self.mic.currentData(),
            "speaker_device": self.out.currentData(),
            "mic_sensitivity": self.sens.value() / 10,
            "silence_seconds": round(self.silence.value(), 1),
            "continue_seconds": round(self.grace.value(), 1),
            "continue_unfinished_seconds": round(self.grace_unf.value(), 1),
            "wake_words": words,
            "followup_seconds": self.followup.value(),
            "question_listen_seconds": self.question.value(),
            "wake_beep": self.wake_beep.isChecked(),
            "capture_sounds": self.capture.isChecked(),
            "whisper_model": self.whisper.currentText(),
            "show_steps": self.steps.isChecked(),
            "eco_auto": self.eco.isChecked(),
            "eco_threshold": self.eco_threshold.value(),
            "eco_model": self.eco_model.currentData(),
            "permission_mode": self.perm.currentData(),
            "extra_instructions": self.extra.toPlainText().strip(),
            "projects_text": self.projects.toPlainText().strip(),
            "accent": self.accent.currentData(),
            "effects": self.fx.isChecked(),
            "orb_sides": self.orb_sides.isChecked(),
            "orb_sats": self.orb_sats.isChecked(),
            "micro_glitch": self.micro.isChecked(),
            "glitch_freq": self.glitch_freq.currentData(),
            "voice_glitch": self.voice_glitch.isChecked(),
            "psy_enabled": self.psy_on.isChecked(),
            "psy_threshold": self.psy_th.value(),
            "chat_font": self.chat_font.value(),
            "live_preview": self.live.isChecked(),
            "tts_speed_bonus": self.speed.value(),
            "lean_mcp": self.lean_mcp.isChecked(),
            "ctx_auto": self.ctx_auto.isChecked(),
            "ctx_threshold": self.ctx_th.value(),
            "context_limit": self.ctx_limit.value(),
            "start_maximized": self.maximized.isChecked(),
        }
