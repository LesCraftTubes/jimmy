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
        self.vision.setPlaceholderText("vide = automatique (un modèle de vision installé dans LM Studio) ; « off » = jamais")
        form.addRow("Modèle de vision", self.vision)
        form.addRow("", _hint("Pour qu'Aurélie REGARDE un rendu (couleurs, mise en page), elle utilise un modèle de vision installé dans LM Studio : "
                              "Qwen3-VL 4B (3,3 Go) est choisi automatiquement s'il est installé. Comme la carte graphique est souvent presque pleine, elle décharge "
                              "un moment le modèle de discussion (environ 20 s), regarde, puis le remet. Écris ici un autre nom pour en choisir un, ou « off » pour ne "
                              "jamais s'en servir. Sans modèle de vision, elle s'appuie sur les mesures exactes de la page et le dit."))
        vrow = QHBoxLayout()
        self.vision_btn = QPushButton("Installer le modèle de vision (3,3 Go)")
        self.vision_btn.clicked.connect(self._install_vision)
        self.vision_lbl = QLabel("")
        self.vision_lbl.setWordWrap(True)
        vrow.addWidget(self.vision_btn)
        vrow.addWidget(self.vision_lbl, 1)
        form.addRow("", vrow)
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

    def _install_vision(self) -> None:
        """Télécharge Qwen3-VL 4B depuis le catalogue officiel de LM Studio (seulement quand on clique)."""
        lms = engine.lms_cli()
        if not lms:
            self.vision_lbl.setText("LM Studio (commande « lms ») introuvable : installe LM Studio d'abord (lmstudio.ai).")
            return
        self.vision_btn.setEnabled(False)
        self.vision_lbl.setText("Téléchargement en cours (3,3 Go)… tu peux continuer à utiliser Jimmy.")

        def work() -> None:
            try:
                out = engine._run([lms, "get", "qwen/qwen3-vl-4b", "-y"], 3600)
                ok = "completed" in (out or "").lower() or "already" in (out or "").lower()
                self.sig.done.emit("VIS|" + ("Modèle de vision installé : Aurélie l'utilisera toute seule." if ok else "Téléchargement non confirmé : " + (out or "")[-160:]))
            except Exception as e:  # noqa: BLE001
                self.sig.done.emit("VIS|Échec du téléchargement : " + str(e)[:160])
        threading.Thread(target=work, daemon=True).start()

    def _show(self, text: str) -> None:
        kind, _, body = text.partition("|")
        if kind == "VIS":
            self.vision_lbl.setText(body)
            self.vision_btn.setEnabled(True)
            return
        (self.pc if kind == "PC" else self.engine_lbl).setText(body)
        if kind == "ENG" and "Modèles : " in body:
            for m in body.split("Modèles : ")[1].rstrip(".").split(", "):
                if m and self.model.findText(m) < 0 and not engine.is_embedding(m):
                    self.model.addItem(m)

    def values(self) -> dict:
        return {"local_enabled": self.enabled.isChecked(), "local_model": self.model.currentText().strip(),
                "local_url": self.url.text().strip(), "vision_model": self.vision.text().strip(),
                "captures_days": int(self.captures_days.text().strip() or 14) if self.captures_days.text().strip().isdigit() else 14}
