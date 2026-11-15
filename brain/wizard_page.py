"""Page « IA locale » de l'assistant d'installation : analyse le PC, explique ce qui est requis, laisse l'utilisateur décider.

Rien n'est téléchargé ni installé sans son accord : cette page ne fait que lire le PC et expliquer. Le moteur (LM Studio,
Ollama...) est une application à part, installée par l'utilisateur ; Jimmy s'y branche ensuite.
"""
from __future__ import annotations

import threading
import webbrowser

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QRadioButton, QVBoxLayout, QWizardPage

from . import engine, hardware


class _Sig(QObject):
    done = Signal(object)


class LocalAIPage(QWizardPage):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.rec = None
        self.found = {"base": ""}
        self.sig = _Sig()
        self.sig.done.connect(self._on_done)
        self.setTitle("IA locale (facultative)")
        lay = QVBoxLayout(self)
        intro = QLabel(
            "Jimmy peut utiliser, en plus de Claude, une <b>IA qui tourne sur ton propre PC</b> : gratuite, privée (rien ne "
            "sort de ton ordinateur), capable d'aller sur Internet et de lire tes fichiers. Elle prend les demandes simples "
            "et passe la main à Claude quand ça dépasse ses moyens, ce qui économise ton abonnement.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.report = QLabel("Analyse de ton PC en cours…")
        self.report.setWordWrap(True)
        lay.addWidget(self.report)
        self.need = QLabel("")
        self.need.setWordWrap(True)
        lay.addWidget(self.need)
        self.btn_site = QPushButton("Télécharger LM Studio (gratuit)")
        self.btn_site.clicked.connect(lambda: webbrowser.open("https://lmstudio.ai"))
        self.btn_site.hide()
        lay.addWidget(self.btn_site)
        self.r_yes = QRadioButton("Oui, activer l'IA locale")
        self.r_no = QRadioButton("Non, Claude seul (tu pourras l'activer plus tard dans Réglages › IA locale)")
        self.r_no.setChecked(True)
        lay.addWidget(self.r_yes)
        lay.addWidget(self.r_no)
        self.r_yes.setEnabled(False)

    def initializePage(self) -> None:
        def work() -> None:
            rec = hardware.recommendation()
            found = engine.discover(self.cfg)
            self.sig.done.emit((rec, found, engine.installed_engines()))
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, data) -> None:
        rec, found, installed = data
        self.rec, self.found = rec, found
        txt = f"<b>Ton PC :</b> {rec['pc']}.<br><b>Profil conseillé :</b> {rec['name']}. {rec['why']}"
        self.report.setText(txt)
        if rec["profile"] == "none":
            self.need.setText("Ton PC est un peu juste : l'IA locale n'est pas proposée. Jimmy fonctionne très bien avec Claude seul.")
            return
        lines = [f"<b>Ce qui est requis :</b> un moteur d'IA locale (LM Studio, Bionic ou Ollama, gratuit) et le modèle "
                 f"<b>{rec['model']}</b> (environ {rec['size_gb']:g} Go à télécharger depuis ce moteur, une seule fois). "
                 "Les modèles ont chacun leur licence, visible dans le moteur avant le téléchargement. "
                 "Jimmy ne télécharge rien sans toi."]
        if found.get("base"):
            lines.append(f"<b>Moteur détecté :</b> prêt ({', '.join(found.get('models', [])[:3]) or 'aucun modèle chargé'}).")
        elif installed:
            lines.append(f"<b>Moteur installé :</b> {', '.join(installed)}. Jimmy le démarrera quand il en aura besoin.")
        else:
            lines.append("<b>Aucun moteur trouvé.</b> Installe LM Studio, télécharge le modèle conseillé, puis reviens ici ou "
                         "active l'IA plus tard dans Réglages.")
            self.btn_site.show()
        if rec["profile"] in ("standard", "comfort"):
            lines.append("<i>Pour jouer pendant que Jimmy tourne, le modèle « standard » est le plus sage : il laisse de la place au jeu.</i>")
        self.need.setText("<br><br>".join(lines))
        self.r_yes.setEnabled(True)
        if found.get("base") or installed:
            self.r_yes.setChecked(True)

    def apply(self) -> None:
        """À appeler quand l'assistant se termine : enregistre le choix."""
        if self.r_yes.isChecked() and self.rec and self.rec["profile"] != "none":
            self.cfg.data["local_enabled"] = True
            self.cfg.data["route"] = "auto"
            model = self.found.get("chat") or ""
            self.cfg.data["local_model"] = model or ""
        else:
            self.cfg.data["local_enabled"] = False
