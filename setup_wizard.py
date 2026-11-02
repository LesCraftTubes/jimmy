"""Assistant de premier lancement : installe Claude Code si besoin, connecte ton compte, choisit le dossier et la voix."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWizard, QWizardPage,
)

from claude_bridge import ClaudeBridge

NOWIN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

WHISPER_CHOICES = [
    ("Rapide : modèle « base » (environ 150 Mo, un peu moins précis)", "base"),
    ("Équilibré : modèle « small » (environ 500 Mo, recommandé)", "small"),
    ("Précis : modèle « medium » (environ 1,5 Go, plus lent sans carte graphique)", "medium"),
]


def _install_command() -> list:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]
    return ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]


class _Sig(QObject):
    line = Signal(str)
    done = Signal(bool)


def auth_status(cli: str) -> bool:
    """True si Claude Code est connecté à un compte."""
    try:
        r = subprocess.run([cli, "auth", "status"], capture_output=True, text=True, timeout=25, creationflags=NOWIN)
        return bool(json.loads(r.stdout or "{}").get("loggedIn"))
    except Exception:  # noqa: BLE001
        return False


class IntroPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Bienvenue dans Jimmy")
        lay = QVBoxLayout(self)
        t = QLabel(
            "Jimmy est un assistant vocal relié à <b>Claude Code</b> : tu lui parles, il lit, modifie et lance des "
            "choses sur ton ordinateur.<br><br>"
            "Cet assistant va :<ul>"
            "<li>vérifier que Claude Code est installé (et l'installer sinon) ;</li>"
            "<li>connecter ton compte Claude (un abonnement suffit, aucune clé API) ;</li>"
            "<li>choisir ton dossier de travail et la précision de la reconnaissance vocale.</li></ul>"
            "Tout reste sur ton ordinateur.")
        t.setWordWrap(True)
        lay.addWidget(t)


class ClaudePage(QWizardPage):
    def __init__(self, bridge: ClaudeBridge):
        super().__init__()
        self.bridge = bridge
        self.setTitle("Claude Code")
        self.sig = _Sig()
        self.sig.line.connect(self._append)
        self.sig.done.connect(self._installed)
        lay = QVBoxLayout(self)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.btn = QPushButton("Installer Claude Code")
        self.btn.clicked.connect(self._install)
        lay.addWidget(self.btn)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log.hide()
        lay.addWidget(self.log)

    def initializePage(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        cli = self.bridge.find_cli()
        if cli:
            self.lbl.setText(f"✔ Claude Code est installé.\n{cli}")
            self.btn.hide()
        else:
            self.lbl.setText("Claude Code n'est pas encore installé sur cet ordinateur. "
                             "Clique sur le bouton : Jimmy lance l'installateur officiel (claude.ai/install).")
            self.btn.show()
            self.btn.setEnabled(True)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self.bridge.find_cli())

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text.rstrip())

    def _install(self) -> None:
        self.btn.setEnabled(False)
        self.log.show()
        self.lbl.setText("Installation en cours, quelques instants…")

        def run() -> None:
            ok = False
            try:
                p = subprocess.Popen(_install_command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", creationflags=NOWIN)
                for ln in p.stdout:
                    self.sig.line.emit(ln)
                ok = p.wait() == 0
            except OSError as e:
                self.sig.line.emit(f"Erreur : {e}")
            self.sig.done.emit(ok)

        threading.Thread(target=run, daemon=True).start()

    def _installed(self, ok: bool) -> None:
        self._refresh()
        if not self.bridge.find_cli():
            self.lbl.setText("L'installation n'a pas abouti. Installe Claude Code à la main (code.claude.com), "
                             "puis clique sur « Précédent » puis « Suivant ».")
            self.btn.setEnabled(True)


class LoginPage(QWizardPage):
    def __init__(self, bridge: ClaudeBridge):
        super().__init__()
        self.bridge = bridge
        self.setTitle("Connexion à ton compte Claude")
        self._ok = False
        self._checking = False
        self.sig = _Sig()
        self.sig.done.connect(self._status)
        lay = QVBoxLayout(self)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.btn = QPushButton("Me connecter à Claude")
        self.btn.clicked.connect(self._login)
        lay.addWidget(self.btn)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)

    def initializePage(self) -> None:
        self._poll()
        self.timer.start(2500)

    def cleanupPage(self) -> None:
        self.timer.stop()

    def _poll(self) -> None:
        cli = self.bridge.find_cli()
        if self._checking or not cli:
            return
        self._checking = True

        def run() -> None:
            self.sig.done.emit(auth_status(cli))

        threading.Thread(target=run, daemon=True).start()

    def _status(self, ok: bool) -> None:
        self._checking = False
        self._ok = ok
        if ok:
            self.lbl.setText("✔ Ton compte Claude est connecté.")
            self.btn.hide()
            self.timer.stop()
        else:
            self.lbl.setText("Jimmy a besoin que tu te connectes à ton compte Claude (abonnement Pro ou Max). "
                             "Clique sur le bouton : une page de connexion s'ouvre dans ton navigateur. "
                             "Cette fenêtre se met à jour toute seule quand c'est fait.")
            self.btn.show()
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._ok

    def _login(self) -> None:
        cli = self.bridge.find_cli()
        if not cli:
            return
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        try:
            subprocess.Popen([cli, "auth", "login"], creationflags=flags)
        except OSError as e:
            self.lbl.setText(f"Impossible de lancer la connexion : {e}")


class FolderPage(QWizardPage):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setTitle("Dossier de travail")
        lay = QVBoxLayout(self)
        t = QLabel("Choisis le dossier sur lequel Claude Code travaille par défaut (ton projet, ton site…). "
                   "Tu pourras le changer à tout moment dans Jimmy.")
        t.setWordWrap(True)
        lay.addWidget(t)
        row = QHBoxLayout()
        self.edit = QLineEdit(cfg.get("workdir") or "")
        b = QPushButton("Parcourir…")
        b.clicked.connect(self._browse)
        row.addWidget(self.edit, 1)
        row.addWidget(b)
        lay.addLayout(row)

    def _browse(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Dossier de travail", self.edit.text())
        if p:
            self.edit.setText(p)


class VoicePage(QWizardPage):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setTitle("Voix et appli mobile")
        lay = QVBoxLayout(self)
        t = QLabel("La reconnaissance vocale se télécharge au premier lancement (une seule fois). "
                   "Plus le modèle est gros, plus Jimmy te comprend bien, mais plus le téléchargement est long.")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.combo = QComboBox()
        cur = cfg.get("whisper_model", "small")
        for label, key in WHISPER_CHOICES:
            self.combo.addItem(label, key)
        i = self.combo.findData(cur)
        self.combo.setCurrentIndex(i if i >= 0 else 1)
        lay.addWidget(self.combo)
        self.mobile = QCheckBox("Activer l'appli mobile (pour piloter Jimmy depuis ton téléphone, à régler ensuite)")
        lay.addWidget(self.mobile)


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Tout est prêt")
        lay = QVBoxLayout(self)
        t = QLabel("Jimmy va démarrer. Au tout premier lancement, le modèle vocal se télécharge : "
                   "l'avancement s'affiche dans la fenêtre. Ensuite, dis « Jimmy » ou clique sur Parler.<br><br>"
                   "Astuce : <b>Réglages › Appli mobile</b> affiche un QR code pour relier ton téléphone.")
        t.setWordWrap(True)
        lay.addWidget(t)


class SetupWizard(QWizard):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Installation de Jimmy")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(560, 400)
        bridge = ClaudeBridge(cfg)
        self.intro = IntroPage()
        self.claude = ClaudePage(bridge)
        self.login = LoginPage(bridge)
        self.folder = FolderPage(cfg)
        self.voice = VoicePage(cfg)
        for p in (self.intro, self.claude, self.login, self.folder, self.voice, DonePage()):
            self.addPage(p)
        self.setButtonText(QWizard.NextButton, "Suivant")
        self.setButtonText(QWizard.BackButton, "Précédent")
        self.setButtonText(QWizard.CancelButton, "Plus tard")
        self.setButtonText(QWizard.FinishButton, "Lancer Jimmy")
        self.bridge = bridge

    def accept(self) -> None:
        cli = self.bridge.find_cli()
        if cli:
            self.cfg.data["claude_path"] = cli
        wd = self.folder.edit.text().strip()
        if wd:
            self.cfg.data["workdir"] = wd
        self.cfg.data["whisper_model"] = self.voice.combo.currentData()
        if self.voice.mobile.isChecked():
            self.cfg.data["remote_enabled"] = True
        self.cfg.data["setup_done"] = True
        self.cfg.save()
        super().accept()


def needs_setup(cfg) -> bool:
    if not cfg.get("setup_done"):
        bridge = ClaudeBridge(cfg)
        cli = bridge.find_cli()
        # Installation déjà en place et connectée (ex. développeur) : pas d'assistant.
        if cli and auth_status(cli):
            cfg.set("setup_done", True)
            return False
        return True
    return False


def run_if_needed(cfg) -> bool:
    """Ouvre l'assistant si nécessaire. Renvoie False si l'utilisateur l'a refermé (Jimmy peut quand même s'ouvrir)."""
    if not needs_setup(cfg):
        return True
    return bool(SetupWizard(cfg).exec())
