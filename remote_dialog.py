"""Fenêtre « Appli mobile » : activer, choisir le mode de connexion, scanner le QR code, gérer les téléphones."""
from __future__ import annotations

import io

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QRadioButton, QVBoxLayout, QButtonGroup,
)

try:
    import segno
except ImportError:      # le QR est un confort : sans lui, le code et le lien restent affichés
    segno = None


def qr_pixmap(text: str, scale: int = 6) -> QPixmap | None:
    if not segno or not text:
        return None
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=scale, border=2, dark="#06080f", light="#ffffff")
    img = QImage.fromData(buf.getvalue(), "PNG")
    return QPixmap.fromImage(img) if not img.isNull() else None


class RemoteDialog(QDialog):
    def __init__(self, cfg, manager, parent=None):
        super().__init__(parent)
        self.cfg, self.m = cfg, manager
        self.setWindowTitle("Appli mobile")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        intro = QLabel(
            "Pilote Jimmy depuis ton téléphone, même quand tu n'es pas devant le PC. "
            "Ça ne marche que si le PC reste allumé avec Jimmy ouvert.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.chk = QCheckBox("Activer l'appli mobile")
        self.chk.setChecked(bool(cfg.get("remote_enabled")))
        self.chk.toggled.connect(self._toggle)
        lay.addWidget(self.chk)

        warn = QLabel("⚠ Un téléphone relié peut donner des ordres à Jimmy sur ce PC (fichiers, commandes). "
                      "Ne scanne le QR code qu'avec ton propre téléphone.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#fbbf24;")
        lay.addWidget(warn)

        self.modes = QButtonGroup(self)
        self.r_lan = QRadioButton("Wi-Fi : le téléphone et le PC sont sur le même réseau")
        self.r_tun = QRadioButton("Internet : tunnel gratuit Cloudflare (marche partout, micro du téléphone compris)")
        self.r_cus = QRadioButton("Mon adresse : Tailscale, ZeroTier, domaine perso…")
        for i, r in enumerate((self.r_lan, self.r_tun, self.r_cus)):
            self.modes.addButton(r, i)
            lay.addWidget(r)
        self.url_edit = QLineEdit(str(cfg.get("remote_custom_url", "")))
        self.url_edit.setPlaceholderText("https://jimmy.mondomaine.fr")
        self.url_edit.editingFinished.connect(self._url_changed)
        lay.addWidget(self.url_edit)
        cur = {"lan": self.r_lan, "tunnel": self.r_tun, "custom": self.r_cus}[manager.mode()]
        cur.setChecked(True)
        self.modes.idToggled.connect(self._mode_changed)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.qr = QLabel()
        self.qr.setFixedSize(230, 230)
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet("background:#ffffff;border-radius:10px;")
        row.addWidget(self.qr)
        side = QVBoxLayout()
        side.addWidget(QLabel("Ou tape ce code sur le téléphone :"))
        self.code = QLabel("")
        self.code.setStyleSheet("font:700 22px 'Consolas','Courier New',monospace;letter-spacing:3px;")
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        side.addWidget(self.code)
        self.left = QLabel("")
        side.addWidget(self.left)
        self.link = QLabel("")
        self.link.setWordWrap(True)
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link.setStyleSheet("color:#8a97b4;font-size:11px;")
        side.addWidget(self.link)
        b_new = QPushButton("Nouveau code")
        b_new.clicked.connect(lambda: (self.m.server.new_pair_code(), self.refresh()))
        side.addWidget(b_new)
        b_copy = QPushButton("Copier le lien")
        b_copy.clicked.connect(self._copy)
        side.addWidget(b_copy)
        side.addStretch(1)
        row.addLayout(side, 1)
        lay.addLayout(row)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#8a97b4;font-size:11px;")
        lay.addWidget(self.hint)

        lay.addWidget(QLabel("Téléphones reliés :"))
        self.devs = QListWidget()
        self.devs.setMaximumHeight(90)
        lay.addWidget(self.devs)
        b_rev = QPushButton("Délier le téléphone sélectionné")
        b_rev.clicked.connect(self._revoke)
        lay.addWidget(b_rev)

        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        lay.addWidget(close)

        self.m.changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self.refresh)
        self._tick.start(1000)
        self.refresh()

    # ---------------------------------------------------------------- actions
    def _toggle(self, on: bool) -> None:
        self.cfg.set("remote_enabled", bool(on))
        self.m.apply()
        self.refresh()

    def _mode_changed(self, idx: int, checked: bool) -> None:
        if not checked:
            return
        self.cfg.set("remote_mode", ("lan", "tunnel", "custom")[idx])
        self.m.apply()
        self.refresh()

    def _url_changed(self) -> None:
        self.cfg.set("remote_custom_url", self.url_edit.text().strip())
        self.refresh()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.m.pair_url())

    def _revoke(self) -> None:
        it = self.devs.currentItem()
        if it:
            self.m.server.revoke(it.data(Qt.UserRole))
            self.refresh()

    # --------------------------------------------------------------- affichage
    def refresh(self) -> None:
        on = bool(self.cfg.get("remote_enabled"))
        self.url_edit.setEnabled(on and self.m.mode() == "custom")
        self.url_edit.setVisible(self.m.mode() == "custom")
        self.status.setText(self.m.status_text())
        url = self.m.pair_url() if on and self.m.server.running else ""
        pm = qr_pixmap(url) if url else None
        if pm:
            self.qr.setPixmap(pm.scaled(220, 220, Qt.KeepAspectRatio, Qt.FastTransformation))
        else:
            self.qr.clear()
            self.qr.setText("" if url else "QR code indisponible\n(active l'appli et attends l'adresse)")
        self.code.setText(self.m.server.current_code() if on and self.m.server.running else "")
        left = self.m.server.pair_seconds_left()
        self.left.setText(f"Valable encore {left // 60} min {left % 60:02d} s" if on and left else "")
        self.link.setText(url)
        if self.m.mode() == "lan":
            self.hint.setText("En Wi-Fi, le téléphone n'autorise pas le micro (adresse http) : tu peux écrire à Jimmy, "
                              "mais pour lui parler choisis le mode Internet.")
        elif self.m.mode() == "tunnel":
            self.hint.setText("L'adresse Internet change à chaque démarrage de Jimmy : il faudra alors re-scanner le QR "
                              "code. Pour une adresse fixe, utilise « Mon adresse » (Tailscale, domaine…).")
        else:
            self.hint.setText("Avec ton propre domaine ou Tailscale, l'adresse reste la même : un seul jumelage suffit. "
                              "Utilise une adresse https pour pouvoir parler (micro).")
        cur = self.devs.currentItem().data(Qt.UserRole) if self.devs.currentItem() else None
        self.devs.clear()
        import time
        for d in self.m.server.devices():
            seen = d.get("last_seen") or 0
            when = time.strftime("%d/%m %H:%M", time.localtime(seen)) if seen else "jamais"
            it = QListWidgetItem(f"{d['name']}  ·  vu le {when}")
            it.setData(Qt.UserRole, d["id"])
            self.devs.addItem(it)
            if d["id"] == cur:
                self.devs.setCurrentItem(it)

    def done(self, r) -> None:
        self._tick.stop()
        try:
            self.m.changed.disconnect(self.refresh)
        except (TypeError, RuntimeError):
            pass
        super().done(r)
