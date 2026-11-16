"""Onglet « IA locale » des réglages : activer, voir ce que le PC permet, tester le moteur, choisir le modèle."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import engine, hardware, packs


class _Sig(QObject):
    done = Signal(str)


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


class LocalTab(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.sig = _Sig()
        self.sig.done.connect(self._show)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        lay.addLayout(form)

        lay.insertWidget(0, _hint(
            "Une IA qui tourne sur ton propre PC : gratuite, privée (rien ne sort), capable d'aller sur Internet, de lire "
            "tes fichiers et de se souvenir. Elle répond aux demandes simples et passe la main à Claude quand ça dépasse ses moyens. "
            "Elle est facultative."))

        self.enabled = QCheckBox("Activer l'IA locale (un sélecteur « Claude / IA locale / Auto » apparaît près de la zone de texte)")
        self.enabled.setChecked(bool(cfg.get("local_enabled", False)))
        form.addRow("", self.enabled)

        self.pc = QLabel("Clique sur « Analyser mon PC ».")
        self.pc.setWordWrap(True)
        form.addRow("Ton PC", self.pc)
        self.engine_lbl = QLabel("")
        self.engine_lbl.setWordWrap(True)
        form.addRow("Moteur", self.engine_lbl)

        row = QHBoxLayout()
        b1 = QPushButton("Analyser mon PC")
        b1.clicked.connect(self._survey)
        b2 = QPushButton("Tester le moteur local")
        b2.clicked.connect(self._test)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        form.addRow("", row)

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItem(str(cfg.get("local_model") or ""))
        self.model.setCurrentText(str(cfg.get("local_model") or ""))
        form.addRow("Modèle", self.model)
        form.addRow("", _hint("Laisse vide pour utiliser le modèle déjà chargé dans LM Studio / Bionic / Ollama."))
        self.url = QLineEdit(str(cfg.get("local_url") or ""))
        self.url.setPlaceholderText("détection automatique (ex. http://127.0.0.1:1234/v1)")
        form.addRow("Adresse (avancé)", self.url)

        self.vision = QLineEdit(str(cfg.get("vision_model") or ""))
        self.vision.setPlaceholderText("aucun : Aurélie lit le texte et les couleurs d'une image")
        form.addRow("Modèle de vision", self.vision)
        form.addRow("", _hint("Facultatif. Pour qu'Aurélie DÉCRIVE aussi l'aspect d'une capture (mise en page, éléments qui se chevauchent), "
                              "télécharge dans LM Studio un petit modèle qui sait voir (« vision » ou « VL ») et écris ici son nom exact. "
                              "Sans lui, elle ne devine rien : elle te dit ce qu'elle a lu et ce qu'elle ne peut pas juger."))
        self.captures_days = QLineEdit(str(cfg.get("captures_days", 14)))
        form.addRow("Garder les captures (jours)", self.captures_days)

        found = packs.load_all(cfg)
        form.addRow("Packs", QLabel(", ".join(p.title for p in found) if found else "aucun (voir README : dossier packs)"))

    # ------------------------------------------------------------------ actions
    def _survey(self) -> None:
        self.pc.setText("Analyse en cours…")

        def work() -> None:
            r = hardware.recommendation()
            self.sig.done.emit(f"PC|{r['pc']}\nProfil conseillé : {r['name']}. {r['why']}"
                               + (f"\nModèle conseillé : {r['model']} (≈ {r['size_gb']:g} Go à télécharger)" if r["model"] else ""))
        threading.Thread(target=work, daemon=True).start()

    def _test(self) -> None:
        self.engine_lbl.setText("Test en cours…")

        def work() -> None:
            found = engine.discover(self.cfg)
            if found["base"]:
                self.sig.done.emit(f"ENG|Moteur trouvé ({found['base']}). Modèles : {', '.join(found['models']) or 'aucun'}.")
            else:
                inst = engine.installed_engines()
                self.sig.done.emit("ENG|Aucun moteur ne répond." + (f" Installé sur ce PC : {', '.join(inst)} (lance son serveur local)." if inst
                                   else " Installe LM Studio (lmstudio.ai), Bionic ou Ollama, puis télécharge un modèle."))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, text: str) -> None:
        kind, _, body = text.partition("|")
        (self.pc if kind == "PC" else self.engine_lbl).setText(body)
        if kind == "ENG" and "Modèles : " in body:
            for m in body.split("Modèles : ")[1].rstrip(".").split(", "):
                if m and self.model.findText(m) < 0 and not engine.is_embedding(m):
                    self.model.addItem(m)

    def values(self) -> dict:
        return {"local_enabled": self.enabled.isChecked(), "local_model": self.model.currentText().strip(),
                "local_url": self.url.text().strip(), "vision_model": self.vision.text().strip(),
                "captures_days": int(self.captures_days.text().strip() or 14) if self.captures_days.text().strip().isdigit() else 14}
