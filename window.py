"""Fenêtre principale de Jimmy et orchestration : écoute -> Claude Code -> voix."""
import os
import sys
import threading
import time

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QTextEdit,
    QGraphicsOpacityEffect,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import sessions
import usage
from chatview import ChatView
from claude_bridge import ClaudeBridge, ClaudeError
from remote_dialog import RemoteDialog
from remote_manager import RemoteManager
from config import ACCENTS, MODEL_NAMES, Config
from icon import make_icon
from listener import Listener
from models import whisper_progress
from orb import Orb
from settings_dialog import SettingsDialog
from speaker import DEFAULT_PRESET, VOICE_PRESETS, Speaker, resolve_preset
from textutils import describe_tool, parse_consent
import theme
from widgets import THEME, GlowButton, HudFrame, SweepOverlay

MODELS = [
    ("Modèle par défaut", ""),
    (f"{MODEL_NAMES['opus']} · le plus fort", "opus"),
    (f"{MODEL_NAMES['sonnet']} · équilibré", "sonnet"),
    (f"{MODEL_NAMES['haiku']} · économe", "haiku"),
    (f"{MODEL_NAMES['fable']}", "fable"),
]

TEST_SENTENCE = "Salut, c'est Jimmy. Voilà à quoi je ressemble avec cette voix. Tout est en ligne."
EFFORTS = [
    ("Effort auto", ""),
    ("Effort bas", "low"),
    ("Effort moyen", "medium"),
    ("Effort haut", "high"),
    ("Effort très haut", "xhigh"),
    ("Effort max", "max"),
]


class PromptEdit(QPlainTextEdit):
    """Zone de saisie multi-lignes : Entrée envoie, Maj+Entrée va à la ligne. Grandit avec le texte."""

    send = Signal()

    def __init__(self):
        super().__init__()
        self.setTabChangesFocus(True)
        self._base = None   # texte déjà écrit avant l'aperçu (None = pas d'aperçu en cours)
        self.textChanged.connect(self._fit)
        self._fit()

    def set_preview(self, text: str) -> None:
        """Texte en cours de reconnaissance : s'écrit à la suite, en bleu italique, et se corrige tout seul."""
        if not text:
            self.end_preview()
            return
        if self._base is None:
            self._base = self.toPlainText()
        base = self._base.rstrip()
        full = f"{base} {text}" if base else text
        self.setPlainText(full)
        self.moveCursor(QTextCursor.End)
        cur = self.textCursor()
        cur.setPosition(len(base) + (1 if base else 0))
        cur.setPosition(len(full), QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#7dd3fc"))
        fmt.setFontItalic(True)
        sel = QTextEdit.ExtraSelection()
        sel.cursor, sel.format = cur, fmt
        self.setExtraSelections([sel])

    def end_preview(self) -> None:
        """Efface l'aperçu et remet le texte d'avant (le texte final est ajouté ensuite)."""
        if self._base is not None:
            self.setPlainText(self._base)
            self.moveCursor(QTextCursor.End)
            self._base = None
        self.setExtraSelections([])

    def keyPressEvent(self, e) -> None:
        if self._base is not None and e.text():
            self._base = None            # tu tapes pendant l'aperçu : le texte affiché devient le tien
            self.setExtraSelections([])
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.send.emit()
            return
        super().keyPressEvent(e)

    def _fit(self) -> None:
        lines = max(1, min(10, int(self.document().size().height())))
        line_h = self.fontMetrics().lineSpacing()
        self.setFixedHeight(line_h * lines + 26)

    def append_text(self, text: str) -> None:
        cur = self.toPlainText().rstrip()
        self.setPlainText((cur + " " + text).strip() if cur else text)
        self.moveCursor(QTextCursor.End)
        self.setFocus()

STYLE = """
QMainWindow, QWidget#root {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0b0c16, stop:0.55 #090a12, stop:1 #071019);
}
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI"; }
QLabel { color: #9aa1bd; }
QLabel#title { color: #f1f2f8; font-size: 26px; font-weight: 800; }
QLabel#subtitle { color: #22d3ee; font-size: 11px; font-family: "Cascadia Mono", "Consolas"; }
QLabel#status { color: #cbd5e1; font-size: 14px; font-weight: 600; }
QLabel#folder, QLabel#hint { color: #646b86; font-size: 11px; }
QLabel#section { color: #646b86; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#usage { color: #aab1cc; font-size: 12px; }
QTextBrowser {
    background-color: rgba(10, 12, 22, 225); border: none; border-radius: 3px;
    color: #e6e8f2; padding: 8px 16px; font-size: 15px; selection-background-color: #155e75;
}
QFrame#sidebar { background: rgba(12, 13, 22, 240); border-right: 1px solid #1a1d2c; }
QFrame#toolbar {
    background: rgba(17,19,31,215);
    border: 1px solid rgba(34, 211, 238, 55); border-radius: 3px;
}
QPushButton#icon { font-size: 17px; padding: 0; }
QFrame#chatframe { background: transparent; border: none; }
QFrame#sep { background: #232842; max-width: 1px; min-width: 1px; }
QListWidget {
    background: transparent; border: none; color: #c3c8dc; font-size: 13px; outline: none;
}
QListWidget::item { padding: 9px 10px; margin: 2px 0; border-radius: 3px; }
QListWidget::item:hover { background: #161a2a; color: #ffffff; }
QListWidget::item:selected {
    background: rgba(34,211,238,55);
    border-left: 3px solid #22d3ee; color: #ffffff;
}
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background: #10121d; border: 1px solid #23283d; border-radius: 3px;
    padding: 8px 12px; color: #eef0f7; font-size: 14px;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #22d3ee;
}
QComboBox:hover { border-color: #3b4363; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #10121d; color: #eef0f7; border: 1px solid #2b3150; border-radius: 3px;
    selection-background-color: #164e63; outline: none; padding: 4px;
}
QPushButton {
    background: #171a2b;
    border: 1px solid #252a40; border-radius: 3px;
    padding: 8px 15px; color: #c3c8dc; font-weight: 600; font-size: 13px;
}
QPushButton:hover { border-color: #22d3ee; color: #ffffff; background: #1a2036; }
QPushButton:pressed { background: #0f1120; }
QPushButton:checked { background: rgba(34, 211, 238, 26); border-color: rgba(34, 211, 238, 150); color: #a5f3fc; }
QPushButton:checked:hover { background: rgba(34, 211, 238, 40); }
QPushButton:disabled { color: #3a3f55; border-color: #191c2a; }
QPushButton#primary {
    background: #0891b2;
    border: none; color: #ffffff;
}
QPushButton#primary:hover {
    background: #06b6d4;
}
QPushButton#talk[active="true"] {
    background: #22d3ee; border-color: #67e8f9; color: #062029;
}
QPushButton#mute:checked { background: rgba(244, 63, 94, 30); border-color: #f43f5e; color: #fda4af; }
QPushButton#stop { color: #fbbf24; }
QPushButton#stop:hover { border-color: #fbbf24; background: rgba(251, 191, 36, 22); }
QPushButton#danger { color: #fda4af; }
QPushButton#danger:hover { border-color: #f43f5e; background: rgba(244, 63, 94, 22); }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #2a3048; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #22d3ee; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QToolTip { background: #10121d; color: #e6e8f2; border: 1px solid #2b3150; padding: 6px; }
QProgressBar { background: #1a1d2c; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #22d3ee; border-radius: 3px; }
QMenu { background: #10121d; color: #e6e8f2; border: 1px solid #2b3150; padding: 6px; border-radius: 3px; }
QMenu::item { padding: 7px 20px; border-radius: 3px; }
QMenu::item:selected { background: #1f2540; }
QTabWidget::pane { border: 1px solid #1d2133; border-radius: 3px; top: -1px; padding: 10px; }
QTabBar::tab {
    background: transparent; color: #8a91ad; padding: 8px 18px; margin-right: 4px;
    border-bottom: 2px solid transparent; font-weight: 600;
}
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #22d3ee; }
QTabBar::tab:hover { color: #ffffff; }
QCheckBox { color: #c3c8dc; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; border: 1px solid #3b4363; background: #10121d; }
QCheckBox::indicator:checked { background: #22d3ee; border-color: #22d3ee; }
QSlider::groove:horizontal { height: 4px; background: #23283d; border-radius: 3px; }
QSlider::handle:horizontal { background: #22d3ee; width: 14px; margin: -6px 0; border-radius: 3px; }
QDialog { background: #0c0d16; }
"""

def themed_style(cfg) -> str:
    """STYLE avec la couleur d'accent choisie et la taille de texte des réglages."""
    main, _second = ACCENTS.get(cfg.get("accent"), ACCENTS["Cyan néon"])
    c = QColor(main)
    s = theme.themed_text(STYLE)
    return s.replace("font-size: 15px; selection", f"font-size: {int(cfg.get('chat_font', 15))}px; selection")


STATUS_TEXT = {
    "loading": "Chargement de la reconnaissance vocale… (1er lancement : téléchargement, patiente)",
    "wake": "En veille. Dis « Jimmy ».",
    "listening": "Je t'écoute…",
    "thinking": "Jimmy travaille…",
    "speaking": "Jimmy parle…",
    "idle": "Écoute automatique coupée.",
    "muted": "Micro coupé.",
    "error": "Erreur.",
}


RESTART_KEYS = ("whisper_model", "whisper_device", "wake_whisper_model", "language")


QUEUE_NOTE = (
    "[Précision ajoutée par l'utilisateur pendant que tu travaillais : tiens-en compte, "
    "poursuis ou corrige ton travail en conséquence, sans tout recommencer.] "
)


FOLLOWUP_NOTE = (
    "[Phrase captée au micro sans le mot Jimmy, juste après ta réponse. Si elle ne t'est "
    "visiblement pas adressée (l'utilisateur parle à quelqu'un d'autre, bruit, télé), réponds "
    "uniquement le mot IGNORER. Sinon réponds normalement.] "
)


class _Signals(QObject):
    reply = Signal(str)
    failure = Signal(str)
    usage = Signal(object)
    step = Signal(str)
    perm = Signal(object)   # demande d'autorisation à afficher (dict)
    remote_send = Signal(str)   # ordres venus du téléphone (traités dans le thread de la fenêtre)
    remote_stop = Signal()
    remote_new = Signal()
    remote_switch = Signal(str)


class JimmyWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.busy = False
        self.thinking = False
        self.speaking = False
        self.sig = _Signals()
        self.sig.reply.connect(self._on_reply)
        self.sig.failure.connect(self._on_failure)
        self.sig.usage.connect(self._on_usage)
        self.sig.step.connect(self._on_step)
        self.sig.perm.connect(self._show_permission)
        self.sig.remote_send.connect(self._on_remote_send)
        self.sig.remote_stop.connect(self.on_stop)
        self.sig.remote_new.connect(self.on_new)
        self.sig.remote_switch.connect(self._on_remote_switch)
        self._remote_quiet = False  # pendant un réaffichage local (thème) : rien n'est renvoyé au téléphone
        self._sessions_cache = []   # discussions connues (envoyées au téléphone) : [{id, title, when, full}]
        self._remote_turn = False   # la demande en cours vient du téléphone : le PC ne lit pas la réponse à voix haute
        self.remote = None
        self._steps_this_turn = 0
        self._eco_on = False
        self._queued = []          # messages écrits pendant que Jimmy travaille
        self._handoff_note = ""    # résumé à joindre au prochain message (reprise de contexte)
        self._long_retry = False

        self.bridge = ClaudeBridge(cfg)
        self.bridge.on_step = self.sig.step.emit
        self.bridge.perm_ask = self._ask_permission
        self.speaker = Speaker(cfg)
        self.listener = Listener(cfg)
        self.speaker.finished.connect(self._on_speech_done)
        self.speaker.chunk_started.connect(self.chat_live_chunk)
        self._live_text = None   # réponse en cours d'écriture/lecture
        self._last_reply = ""   # dernière réponse (pour savoir si Jimmy attend une réponse)
        self._last_request = ""  # dernière demande envoyée à Claude (hors accords)
        self.speaker.error.connect(lambda m: self.add_system(m))
        self.listener.state_changed.connect(self._on_listener_state)
        self.listener.level.connect(self._on_level)
        self.listener.heard.connect(self.on_heard)
        self.listener.status.connect(self.add_system)
        self.listener.error.connect(self._on_listener_error)
        self.listener.woke.connect(self._on_woke)
        self.listener.capture.connect(self._on_capture)

        self._build_ui()
        self.listener.partial.connect(self._on_partial)
        self._glitch_timer = QTimer(self)
        self._glitch_timer.setSingleShot(True)
        self._glitch_timer.timeout.connect(self._micro_glitch)
        self._apply_look()
        self._arm_glitch()
        self._refresh_subtitle()
        self.set_state("loading")

        if not self.bridge.find_cli():
            self.add_system(
                "Claude Code est introuvable sur cet ordinateur. Installe-le (voir le README), "
                "tape « claude » une fois dans un terminal pour te connecter, puis relance Jimmy."
            )
        else:
            pass
        if not self.cfg.get("workdir"):
            self.add_system(
                "Aucun dossier de travail choisi : clique sur « Dossier de travail » pour indiquer "
                "où se trouve ton projet."
            )
        self.remote = RemoteManager(cfg, self)
        self.remote.apply()
        self.refresh_sessions()
        if self.bridge.session_id:
            for role, text in sessions.load_messages(self.bridge.workdir(), self.bridge.session_id)[-30:]:
                self.add_message(role, text)
        self.listener.start()
        # Premier lancement : le modèle vocal se télécharge, on montre l'avancement.
        self._dl_timer = QTimer(self)
        self._dl_timer.timeout.connect(self._show_download)
        self._dl_timer.start(1500)
        # Utilisation de l'abonnement : au démarrage, toutes les 5 minutes et après chaque réponse
        # (usage.py limite de toute façon à un appel par minute : le service bloque sinon).
        self.refresh_usage()
        self._usage_timer = QTimer(self)
        self._usage_timer.timeout.connect(self.refresh_usage)
        self._usage_timer.start(300_000)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setWindowTitle("Jimmy")
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------------------------------------------------- barre latérale
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(290)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 20, 16, 16)
        sl.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        self.logo = QLabel()
        self.logo.setPixmap(make_icon(44).pixmap(44, 44))
        brand.addWidget(self.logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("JIMMY")
        title.setObjectName("title")
        f = QFont(title.font())
        f.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        title.setFont(f)
        self.subtitle = QLabel("● en ligne")
        self.subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle)
        brand.addLayout(title_box)
        brand.addStretch(1)
        sl.addLayout(brand)
        sl.addSpacing(6)

        self.btn_new = GlowButton("Nouvelle discussion", "#22d3ee")
        self.btn_new.set_icon("plus")
        self.btn_new.setObjectName("primary")
        self.btn_new.clicked.connect(self.on_new)
        sl.addWidget(self.btn_new)

        sec = QLabel("DISCUSSIONS")
        sec.setObjectName("section")
        sec.setToolTip("Partagées avec Claude Code. Clic droit ou Suppr pour supprimer.")
        sl.addWidget(sec)
        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self.on_session_clicked)
        self.session_list.setWordWrap(True)
        self.session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._session_menu)
        sl.addWidget(self.session_list, 1)

        self.usage_title = QLabel("ABONNEMENT")
        self.usage_title.setObjectName("section")
        sl.addWidget(self.usage_title)
        self.usage_session = QProgressBar()
        self.usage_week = QProgressBar()
        self.usage_labels = {}
        for bar_ in (self.usage_session, self.usage_week):
            lbl = QLabel("—")
            lbl.setObjectName("usage")
            self.usage_labels[bar_] = lbl
            bar_.setRange(0, 100)
            bar_.setValue(0)
            bar_.setTextVisible(False)
            bar_.setFixedHeight(6)
            sl.addWidget(lbl)
            sl.addWidget(bar_)
        self.usage_session.setToolTip("Limite de session (fenêtre de 5 heures)")
        self.usage_week.setToolTip("Limite hebdomadaire")
        sl.addSpacing(4)

        self.btn_cc = GlowButton("Ouvrir dans Claude Code")
        self.btn_cc.set_icon("terminal")
        self.btn_cc.setToolTip("Ouvre la discussion en cours dans le terminal Claude Code")
        self.btn_cc.clicked.connect(self.on_open_cc)
        sl.addWidget(self.btn_cc)
        self.btn_mobile = GlowButton("Appli mobile")
        self.btn_mobile.set_icon("wave")
        self.btn_mobile.setToolTip("Pilote Jimmy depuis ton téléphone (QR code)")
        self.btn_mobile.clicked.connect(self.on_remote_settings)
        sl.addWidget(self.btn_mobile)
        self.btn_folder = GlowButton("Dossier de travail")
        self.btn_folder.set_icon("folder")
        self.btn_folder.clicked.connect(self.on_folder)
        sl.addWidget(self.btn_folder)
        self.folder_lbl = QLabel()
        self.folder_lbl.setObjectName("folder")
        self.folder_lbl.setWordWrap(True)
        sl.addWidget(self.folder_lbl)
        self._refresh_folder_label()
        outer.addWidget(side)

        # ---------------------------------------------------- zone principale
        main = QWidget()
        lay = QVBoxLayout(main)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(12)

        toolbar = HudFrame()
        toolbar.setObjectName("toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(10, 8, 10, 8)
        bar.setSpacing(8)

        def sep() -> QFrame:
            s = QFrame()
            s.setObjectName("sep")
            s.setFixedHeight(22)
            return s

        def toggle(text: str, key: str, default: bool, tip: str, icon: str = "") -> GlowButton:
            b = GlowButton(text)
            if icon:
                b.set_icon(icon)
            b.setObjectName("icon")
            b.setFixedSize(42, 36)
            b.setCheckable(True)
            b.setChecked(bool(self.cfg.get(key, default)))
            b.setToolTip(tip)
            return b

        # Voix
        self.btn_voice = toggle("", "voice_enabled", True, "Voix : Jimmy lit ses réponses à voix haute", "speaker")
        self.btn_voice.toggled.connect(self.on_voice_toggle)
        self.voice_box = QComboBox()
        self.voice_box.addItems(list(VOICE_PRESETS))
        current = resolve_preset(self.cfg.get("voice_preset"))
        self.voice_box.setCurrentText(current if current in VOICE_PRESETS else DEFAULT_PRESET)
        self.voice_box.currentTextChanged.connect(self.on_voice_preset)
        self.voice_box.setMaxVisibleItems(18)
        self.voice_box.setMinimumWidth(190)
        self.voice_box.setToolTip("Voix de Jimmy. « locale » = voix téléchargée sur ton PC, sans Internet")
        self.btn_test = GlowButton("")
        self.btn_test.set_icon("play")
        self.btn_test.setObjectName("icon")
        self.btn_test.setFixedSize(42, 36)
        self.btn_test.setToolTip("Écoute un exemple avec la voix choisie (reclique pour couper)")
        self.btn_test.clicked.connect(self.on_voice_test)
        bar.addWidget(self.btn_voice)
        bar.addWidget(self.voice_box)
        bar.addWidget(self.btn_test)
        bar.addWidget(sep())

        # Modèle et effort : moins cher = moins de quota consommé
        self.model_box = QComboBox()
        for label, value in MODELS:
            self.model_box.addItem(label, value)
        self.model_box.setCurrentIndex(max(0, self.model_box.findData(self.cfg.get("model") or "")))
        self.model_box.setToolTip("Haiku consomme le moins de quota, Opus le plus")
        self.model_box.currentIndexChanged.connect(
            lambda _i: self._set_cost("model", self.model_box.currentData())
        )
        self.effort_box = QComboBox()
        for label, value in EFFORTS:
            self.effort_box.addItem(label, value)
        self.effort_box.setCurrentIndex(max(0, self.effort_box.findData(self.cfg.get("effort") or "")))
        self.effort_box.setToolTip("Effort bas = réponses plus rapides et moins de tokens")
        self.effort_box.currentIndexChanged.connect(
            lambda _i: self._set_cost("effort", self.effort_box.currentData())
        )
        bar.addWidget(self.model_box)
        bar.addWidget(self.effort_box)
        bar.addWidget(sep())

        # Écoute et modes
        self.btn_auto = toggle("", "wake_words_enabled", True,
                               "Écoute auto : écoute en permanence le mot d'éveil", "radar")
        self.btn_auto.toggled.connect(self.on_auto_toggle)
        self.btn_relisten = toggle("", "auto_relisten", True,
                                   "Relance : après une réponse, Jimmy se remet à t'écouter quelques secondes", "repeat")
        self.btn_relisten.toggled.connect(lambda on: self.cfg.set("auto_relisten", bool(on)))
        self.btn_long = toggle("", "long_mode", False,
                               "Mode long : réponses complètes et détaillées à l'écran", "long")
        self.btn_long.toggled.connect(lambda on: self.cfg.set("long_mode", bool(on)))
        self.btn_dict = toggle("", "dictation", False,
                               "Dictée : ta voix s'écrit dans la zone de texte, tu relis puis tu envoies", "pen")
        self.btn_dict.toggled.connect(lambda on: self.cfg.set("dictation", bool(on)))
        for b in (self.btn_auto, self.btn_relisten, self.btn_long, self.btn_dict):
            bar.addWidget(b)
        bar.addStretch(1)
        self.btn_settings = GlowButton("")
        self.btn_settings.set_icon("gear")
        self.btn_settings.setObjectName("icon")
        self.btn_settings.setFixedSize(42, 36)
        self.btn_settings.setToolTip("Réglages : audio, écoute, quota, apparence, fenêtre")
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_restart = GlowButton("", "#fbbf24")
        self.btn_restart.set_icon("power")
        self.btn_restart.setObjectName("icon")
        self.btn_restart.setFixedSize(42, 36)
        self.btn_restart.setToolTip("Ferme et rouvre Jimmy pour appliquer les réglages")
        self.btn_restart.clicked.connect(self.restart_app)
        self.btn_restart.hide()
        bar.addWidget(self.btn_restart)
        bar.addWidget(self.btn_settings)
        lay.addWidget(toolbar)

        self.orb = Orb()
        self.orb.setMinimumSize(170, 170)
        self.orb.setMaximumHeight(220)
        lay.addWidget(self.orb)

        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("status")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status_lbl)

        self.chat = ChatView()
        self.chat.copied.connect(lambda _c: self.status_lbl.setText("Code copié dans le presse-papiers."))
        self.chat_frame = HudFrame()
        self.chat_frame.setObjectName("chatframe")
        cl = QVBoxLayout(self.chat_frame)
        cl.setContentsMargins(3, 3, 3, 3)
        cl.addWidget(self.chat)
        lay.addWidget(self.chat_frame, 1)

        ctx_row = QHBoxLayout()
        ctx_row.setContentsMargins(0, 0, 4, 0)
        ctx_row.addStretch(1)
        self.ctx_lbl = QLabel("Contexte 0 %")
        self.ctx_lbl.setObjectName("hint")
        self.ctx_bar = QProgressBar()
        self.ctx_bar.setRange(0, 100)
        self.ctx_bar.setTextVisible(False)
        self.ctx_bar.setFixedSize(84, 4)
        ctx_row.addWidget(self.ctx_lbl)
        ctx_row.addWidget(self.ctx_bar)
        lay.addLayout(ctx_row)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = PromptEdit()
        self.input.send.connect(self.on_send)
        self._refresh_placeholder()
        self.btn_send = GlowButton("Envoyer")
        self.btn_send.set_icon("send")
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self.on_send)
        self.btn_talk = GlowButton("Parler", "#22d3ee")
        self.btn_talk.set_icon("wave")
        self.btn_talk.setObjectName("talk")
        self.btn_talk.setToolTip("Clique pour parler (même pendant que Jimmy travaille), reclique pour valider ce que tu as dit (Ctrl+Espace)")
        self.btn_talk.clicked.connect(self.on_talk)
        self.btn_mute = GlowButton("Micro", "#f43f5e")
        self.btn_mute.set_icon("mic")
        self.btn_mute.setObjectName("mute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setToolTip("Arrête de capter ta voix, sans perdre ce que tu étais en train de dire (Ctrl+M)")
        self.btn_mute.toggled.connect(self.on_mute)
        self.btn_stop = GlowButton("Stop", "#fbbf24")
        self.btn_stop.set_icon("stop")
        self.btn_stop.setObjectName("stop")
        self.btn_stop.setToolTip("Annule la tâche ou coupe la voix (Échap)")
        self.btn_stop.clicked.connect(self.on_stop)
        row.addWidget(self.input, 1)
        for b in (self.btn_send, self.btn_talk, self.btn_mute, self.btn_stop):
            b.setMinimumWidth(118)
            b.setMinimumHeight(40)
            row.addWidget(b, 0, Qt.AlignBottom)
        lay.addLayout(row)
        outer.addWidget(main, 1)
        self.sweep = SweepOverlay(root)     # glitchs par-dessus toute la fenêtre

        QShortcut(QKeySequence("Escape"), self, activated=self.on_stop)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self.on_talk)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.on_new)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self.btn_mute.toggle)
        QShortcut(QKeySequence("Delete"), self.session_list, activated=self._delete_selected_session)
        self._place_window()

    def show_animated(self) -> None:
        """Ouverture en grand (fenêtre maximisée, pas plein écran) avec un léger fondu."""
        self.setWindowOpacity(0.0)
        if self.cfg.get("start_maximized", True):
            self.showMaximized()
        else:
            self.show()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(350)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.start()

    def _place_window(self) -> None:
        """Grande fenêtre centrée (88 % de l'écran), sans plein écran."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.resize(1280, 860)
            return
        geo = screen.availableGeometry()
        w, h = int(geo.width() * 0.88), int(geo.height() * 0.9)
        self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 2, w, h)

    # -------------------------------------------------------------- discussions
    def refresh_sessions(self) -> None:
        wd = self.bridge.workdir()
        self.session_list.clear()
        full = sessions.full_ids()
        cache = []
        for sid, title_, when in sessions.list_sessions(wd):
            is_full = sid in full
            cache.append({"id": sid, "title": title_, "when": when, "full": bool(is_full)})
            item = QListWidgetItem(f"{title_}\n{when}" + ("  ·  pleine" if is_full else ""))
            item.setData(Qt.UserRole, sid)
            if is_full:
                # discussion trop grosse pour continuer : grisée, la lecture reste possible
                item.setForeground(QColor(96, 102, 128))
                f = item.font()
                f.setItalic(True)
                item.setFont(f)
                item.setToolTip(f"{title_}\nDiscussion pleine : trop longue pour continuer. "
                                "Ton prochain message ira dans une nouvelle discussion avec un résumé.")
            else:
                item.setToolTip(title_)
            self.session_list.addItem(item)
            if sid == self.bridge.session_id:
                item.setSelected(True)
        self._sessions_cache = cache
        self._remote_emit(self._sessions_event())

    def on_session_clicked(self, item) -> None:
        self.switch_session(item.data(Qt.UserRole))

    def switch_session(self, sid: str) -> None:
        """Ouvre une discussion (clic dans la liste du PC ou choix sur le téléphone : les deux restent synchronisés)."""
        if self.busy:
            self.add_system("Attends la fin de la tâche en cours (ou appuie sur Stop).")
            self.refresh_sessions()
            return
        if not sid or sid == self.bridge.session_id:
            return
        self.bridge.set_session(sid)
        was_full = sid in sessions.full_ids()
        if was_full:
            self._handoff_note = sessions.recap(self.bridge.workdir(), sid)
            self.bridge.reset()   # lecture seule : la suite ira dans une nouvelle discussion
        self._clear_chat()
        msgs = sessions.load_messages(self.bridge.workdir(), sid)
        if len(msgs) > 60:
            self.add_system(f"{len(msgs) - 60} messages plus anciens masqués.")
        for role, text in msgs[-60:]:
            self.add_message(role, text)
        self.add_system("Discussion pleine : tu peux la relire. Ton prochain message ira dans une nouvelle "
                        "discussion, avec un résumé." if was_full
                        else "Discussion reprise : tu peux continuer ici ou dans Claude Code.")
        self._refresh_ctx()
        self._swap_anim()
        self.refresh_sessions()
        self.session_list.clearSelection()
        for i in range(self.session_list.count()):
            if self.session_list.item(i).data(Qt.UserRole) == sid:
                self.session_list.item(i).setSelected(True)

    def _session_menu(self, pos) -> None:
        item = self.session_list.itemAt(pos)
        if not item:
            return
        self.session_list.setCurrentItem(item)
        menu = QMenu(self)
        act_open = menu.addAction("Ouvrir")
        act_cc = menu.addAction("Ouvrir dans Claude Code")
        menu.addSeparator()
        act_del = menu.addAction("Supprimer la discussion")
        chosen = menu.exec(self.session_list.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self.on_session_clicked(item)
        elif chosen is act_cc:
            self.on_session_clicked(item)
            if self.bridge.session_id == item.data(Qt.UserRole):
                self.on_open_cc()
        elif chosen is act_del:
            self._delete_session(item)

    def _delete_selected_session(self) -> None:
        item = self.session_list.currentItem()
        if item:
            self._delete_session(item)

    def _delete_session(self, item) -> None:
        sid = item.data(Qt.UserRole)
        if not sid:
            return
        current = sid == self.bridge.session_id
        if current and self.busy:
            self.add_system("Attends la fin de la tâche en cours avant de supprimer cette discussion.")
            return
        title_ = item.toolTip() or "cette discussion"
        box = QMessageBox(self)
        box.setWindowTitle("Supprimer la discussion")
        box.setText(f"Supprimer « {title_} » ?")
        box.setInformativeText("Elle disparaîtra aussi de Claude Code. C'est définitif.")
        yes = box.addButton("Supprimer", QMessageBox.DestructiveRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.setStyleSheet(STYLE)
        box.exec()
        if box.clickedButton() is not yes:
            return
        if not sessions.delete_session(self.bridge.workdir(), sid):
            self.add_system("Impossible de supprimer cette discussion (fichier utilisé ?).")
            return
        if current:
            self.bridge.reset()
            self._clear_chat()
        self.refresh_sessions()
        self.add_system(f"Discussion supprimée : {title_}")

    # ------------------------------------------------------------ abonnement
    def refresh_usage(self) -> None:
        threading.Thread(target=lambda: self.sig.usage.emit(usage.fetch()), daemon=True).start()

    def _on_usage(self, data) -> None:
        if not data:
            return
        if data.get("plan"):
            self.usage_title.setText(f"ABONNEMENT {data['plan'].upper()}")
        for key, bar_, name in (("session", self.usage_session, "Session"),
                                ("week", self.usage_week, "Semaine")):
            if key not in data:
                continue
            pct, reset = data[key]
            bar_.setValue(int(round(pct)))
            self.usage_labels[bar_].setText(
                f"{name} : {pct:.0f} % · reset {reset}" if reset else f"{name} : {pct:.0f} %")
            color = "#f43f5e" if pct >= 90 else "#fbbf24" if pct >= 70 else THEME["accent"]
            bar_.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
        if "session" in data:
            self.bridge.usage_pct = float(data["session"][0])
            self._update_eco()
            # Cyberpsychose dès 80 % de la session : elle reste jusqu'au reset (0 % = effet coupé).
            self._apply_psychosis()
        # Rafraîchit juste après le prochain reset (ou dans 1 min si un reset vient de passer),
        # sans attendre une nouvelle requête ni le minuteur de 5 min.
        delay = None
        if data.get("next_reset"):
            delay = max(5, int(data["next_reset"] - time.time()) + 10)
        elif data.get("stale"):
            delay = 60
        if delay is not None and delay < 6 * 3600:
            if getattr(self, "_reset_timer", None):
                self._reset_timer.stop()
            self._reset_timer = QTimer(self)
            self._reset_timer.setSingleShot(True)
            self._reset_timer.timeout.connect(self.refresh_usage)
            self._reset_timer.start(delay * 1000)

    # ------------------------------------------------------------ taille du contexte
    def _ctx_pct(self) -> float:
        limit = max(10_000, int(self.cfg.get("context_limit", 1000000)))
        return 100.0 * self.bridge.context_tokens / limit

    def _refresh_ctx(self) -> None:
        pct = min(100.0, self._ctx_pct())
        self.ctx_lbl.setText(f"Contexte {pct:.0f} %")
        self.ctx_bar.setValue(int(round(pct)))
        th = float(self.cfg.get("ctx_threshold", 70))
        color = "#f43f5e" if pct >= th else "#fbbf24" if pct >= th - 20 else THEME["accent"]
        self.ctx_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 0px; }}")
        self.ctx_lbl.setToolTip(
            f"{self.bridge.context_tokens:,} sur {int(self.cfg.get('context_limit', 1000000)):,} tokens.\n"
            f"À {th:.0f} %, Jimmy reprend le contexte dans une nouvelle discussion "
            "(l'ancienne reste lisible, en gris dans la liste).".replace(",", " "))

    def _handoff(self, forced: bool = False) -> None:
        """Discussion presque pleine : on repart dans une nouvelle avec un petit résumé, l'ancienne est grisée."""
        sid = self.bridge.session_id
        if not sid:
            return
        self._handoff_note = sessions.recap(self.bridge.workdir(), sid)
        sessions.mark_full(sid)
        self.bridge.reset()
        self.add_system("Discussion presque pleine : je reprends le contexte dans une nouvelle discussion."
                        if not forced else "Discussion trop longue : je reprends ta demande dans une nouvelle discussion.")
        self.refresh_sessions()
        self._refresh_ctx()

    def _chat_region(self) -> QRectF:
        tl = self.chat_frame.mapTo(self.centralWidget(), QPoint(0, 0))
        return QRectF(tl.x(), tl.y(), self.chat_frame.width(), self.chat_frame.height())

    def _swap_anim(self) -> None:
        """Transition entre deux discussions : fondu + léger glissement de la zone de texte."""
        if getattr(self, "_swap", None) is not None:
            self._swap.stop()      # changement de page rapide : l'ancien fondu s'arrête
        fx = QGraphicsOpacityEffect(self.chat)
        self.chat.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity", self)
        self.sweep.play("switch", self._chat_region())
        a.setDuration(650)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: self.chat.setGraphicsEffect(None))
        self._swap = a
        a.start()

    def _apply_look(self) -> None:
        """Applique couleurs, effets et taille du texte (au démarrage et après les réglages)."""
        main, second = ACCENTS.get(self.cfg.get("accent"), ACCENTS["Cyan néon"])
        changed = THEME.get("accent") != main
        THEME.update(accent=main, accent2=second, effects=bool(self.cfg.get("effects", True)))
        theme.set_accent(main)
        self.setStyleSheet(themed_style(self.cfg))
        self.orb.set_palette(theme.orb_colors(second))
        custom = main.lower() != "#22d3ee"
        logo_icon = make_icon(44, second if custom else None, main if custom else None)
        self.logo.setPixmap(logo_icon.pixmap(44, 44))
        QApplication.setWindowIcon(make_icon(256, second if custom else None, main if custom else None))
        self.chat.apply_theme()
        if changed and hasattr(self, "_glitch_timer") and not self.busy and self._live_text is None:
            self._reload_chat()
        for b in self.findChildren(GlowButton):
            b.refresh_theme()
        self.orb.set_options(self.cfg.get("orb_sides", True), self.cfg.get("orb_sats", True))
        self.chat_frame.update()
        self.findChild(QFrame, "toolbar").update()
        self._apply_psychosis()
        self._refresh_ctx()

    def _reload_chat(self) -> None:
        """Réaffiche la discussion en cours avec les couleurs du nouveau thème."""
        sid = self.bridge.session_id
        if not sid:
            return
        self.chat.clear()
        self._remote_quiet = True
        try:
            for role, text in sessions.load_messages(self.bridge.workdir(), sid)[-60:]:
                self.add_message(role, text)
        finally:
            self._remote_quiet = False

    def _arm_glitch(self) -> None:
        """Prochain glitch aléatoire (la fréquence se règle dans Apparence)."""
        import random as _r
        lo, hi = {"Rare": (40, 100), "Fréquente": (4, 12)}.get(self.cfg.get("glitch_freq"), (9, 28))
        level = self._psy_level()
        if level > 0:          # quota presque épuisé (ou thème Cyberpsychose) : glitchs bien plus présents
            lo, hi = 1.2 + 1.3 * (1 - level), 3.5 + 3.0 * (1 - level)
        self._glitch_timer.start(int(_r.uniform(lo, hi) * 1000))

    def _micro_glitch(self) -> None:
        level = self._psy_level()
        allowed = (self.cfg.get("micro_glitch", True) or level > 0) and self.cfg.get("effects", True)
        if allowed and self.isVisible() and not self.isMinimized() and (self._live_text is None or level > 0):
            self.sweep.play("micro", QRectF(self.centralWidget().rect()), 1.0 + 0.9 * level)
        self._arm_glitch()

    def _on_partial(self, text: str) -> None:
        if self.cfg.get("live_preview", True):
            self.input.set_preview(text)
        elif not text:
            self.input.end_preview()

    def _psy_level(self) -> float:
        """0 = calme. Thème « Cyberpsychose » : toujours à fond. Sinon dépend du quota de session."""
        if self.cfg.get("accent") == "Cyberpsychose":
            return 1.0
        pct = self.bridge.usage_pct
        th = float(self.cfg.get("psy_threshold", 80))
        if not (bool(self.cfg.get("psy_enabled", True)) and pct >= th):
            return 0.0
        return 0.35 + 0.65 * (pct - th) / max(1.0, 100 - th)

    def _apply_psychosis(self) -> None:
        level = self._psy_level()
        self.orb.set_psychosis(level)
        self.speaker.glitch_level = level if self.cfg.get("voice_glitch", True) else 0.0

    def restart_app(self) -> None:
        """Ferme Jimmy et le rouvre (pour appliquer les réglages qui demandent un redémarrage)."""
        from PySide6.QtCore import QProcess
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, args, os.getcwd())
        self.close()
        QApplication.quit()

    def _update_eco(self) -> None:
        """Mode économie auto : annonce le changement de modèle quand le seuil est franchi."""
        eco = self.bridge.eco_active()
        if eco != self._eco_on:
            self._eco_on = eco
            name = MODEL_NAMES.get(self.cfg.get("eco_model"), self.cfg.get("eco_model") or "")
            if eco:
                self.add_system(
                    f"Session à {self.bridge.usage_pct:.0f} % : je passe en {name} pour économiser."
                )
            else:
                self.add_system("Économie désactivée : retour au modèle choisi.")
        self._refresh_subtitle()

    def _refresh_subtitle(self) -> None:
        alias = self.bridge.effective_model()
        model = MODEL_NAMES.get(alias, alias) or "modèle par défaut"
        eco = "  ·  éco" if self._eco_on else ""
        self.subtitle.setText(f"● en ligne  ·  {model}{eco}")

    def _set_cost(self, key: str, value: str) -> None:
        self.cfg.set(key, value or "")
        self._refresh_subtitle()

    def _refresh_placeholder(self) -> None:
        self.input.setPlaceholderText(
            f"Écris ici (Entrée = envoyer, Maj+Entrée = nouvelle ligne), ou dis « {self._wake_label()} »"
        )

    def chat_live_chunk(self, text: str, duration: float, words) -> None:
        self.chat.live_chunk(text, duration, words)

    def on_open_cc(self) -> None:
        if not self.bridge.open_in_terminal():
            self.add_system("Claude Code est introuvable sur cet ordinateur.")

    def _refresh_folder_label(self) -> None:
        wd = self.cfg.get("workdir") or ""
        if wd:
            shown = wd if len(wd) < 70 else "…" + wd[-68:]
            self.folder_lbl.setText("Dossier de travail : " + shown)
        else:
            self.folder_lbl.setText("Dossier de travail : dossier personnel (par défaut)")

    # ------------------------------------------------------------- affichage
    def _wake_words(self) -> list:
        words = self.cfg.get("wake_words") or ["jimmy"]
        return [str(w).strip() for w in words if str(w).strip()] or ["jimmy"]

    def _wake_label(self) -> str:
        return self._wake_words()[0].title()

    # --------------------------------------------------------- appli mobile
    def _remote_emit(self, event: dict) -> None:
        if self.remote is not None and not self._remote_quiet:
            self.remote.emit(event)

    def _clear_chat(self) -> None:
        self.chat.clear()
        self._remote_emit({"type": "clear"})

    def _sessions_event(self) -> dict:
        return {"type": "sessions", "items": self._sessions_cache, "current": self.bridge.session_id or ""}

    def remote_snapshot(self) -> dict:
        import platform
        st = "thinking" if self.thinking else "speaking" if self.speaking else "idle"
        return {"state": st, "busy": bool(self.busy), "pc": platform.node(), "workdir": self.bridge.workdir(),
                "sessions": self._sessions_cache, "current": self.bridge.session_id or ""}

    # Appelés depuis le thread du serveur : ils se contentent d'émettre un signal Qt.
    def remote_send(self, text: str) -> None:
        self.sig.remote_send.emit(text)

    def remote_stop(self) -> None:
        self.sig.remote_stop.emit()

    def remote_new(self) -> None:
        self.sig.remote_new.emit()

    def remote_switch(self, sid: str) -> None:
        self.sig.remote_switch.emit(sid)

    def _on_remote_switch(self, sid: str) -> None:
        # seules les discussions affichées dans la liste peuvent être ouvertes (le téléphone ne choisit pas un chemin)
        if any(it["id"] == sid for it in self._sessions_cache):
            self.switch_session(sid)

    def _on_remote_send(self, text: str) -> None:
        if not self.busy:
            self._remote_turn = True
        self.submit(text)

    def on_remote_settings(self) -> None:
        dlg = RemoteDialog(self.cfg, self.remote, self)
        dlg.setStyleSheet(themed_style(self.cfg))
        dlg.exec()

    def _show_download(self) -> None:
        if self.listener.state != "loading":
            return
        prog = whisper_progress(str(self.cfg.get("whisper_model", "small")))
        if prog and prog[0] > 1 and prog[0] < prog[1] * 0.97:
            self.status_lbl.setText(f"Téléchargement du modèle vocal : {int(prog[0] * 100 / prog[1])} % (une seule fois)")

    def set_state(self, state: str) -> None:
        self._remote_emit({"type": "state", "state": "thinking" if self.thinking else
                           "speaking" if state == "speaking" else "idle", "busy": bool(self.busy)})
        self.orb.set_state(state)
        if state == "wake":
            self.status_lbl.setText(f"En veille. Dis « {self._wake_label()} ».")
        else:
            self.status_lbl.setText(STATUS_TEXT.get(state, ""))

    def add_message(self, role: str, text: str) -> None:
        self._remote_emit({"type": "message", "role": role, "text": text})
        if role == "user":
            self.chat.add_user(text)
        else:
            self.chat.add_assistant(text)

    def add_system(self, text: str) -> None:
        self._remote_emit({"type": "system", "text": text})
        self.chat.add_system(text)

    # --------------------------------------------------------- signaux listener
    def _on_listener_state(self, state: str) -> None:
        listening = state == "listening"
        self.btn_talk.set_active(listening)
        self.btn_talk.setText("J'écoute…" if listening else "Parler")
        self.btn_talk.set_icon("stop" if listening else "wave")
        if not self.busy:
            self.set_state(state)

    def _on_step(self, text: str) -> None:
        """Étape de travail en direct : écrite dans la discussion et dans la ligne d'état."""
        if not self.thinking:
            return
        self._remote_emit({"type": "step", "text": text})
        shown = text if len(text) <= 80 else text[:79] + "…"
        self.status_lbl.setText(f"Jimmy travaille…  ·  {shown}")
        if self.cfg.get("show_steps", True):
            self.chat.add_step(text, first=self._steps_this_turn == 0)
            self._steps_this_turn += 1

    def _on_woke(self) -> None:
        """Retour immédiat dès que « Jimmy » est reconnu."""
        if not self.busy:
            self.set_state("listening")
        if self.cfg.get("wake_beep", True):
            self.speaker.beep()

    def _on_capture(self, started: bool) -> None:
        """Petit « bloup » discret : montant quand ta voix est captée, descendant à la fin."""
        if self.cfg.get("capture_sounds", True) and not self.speaking:
            if started:
                self.speaker.beep(520, 70, volume=0.13, to_freq=700)
            else:
                self.speaker.beep(620, 90, volume=0.13, to_freq=420)

    def _on_level(self, rms: float) -> None:
        self.orb.set_level(rms)

    def _on_listener_error(self, msg: str) -> None:
        self.add_system(msg)
        if not self.busy:
            self.set_state("error")

    # ------------------------------------------------------------ autorisations à l'écran
    def _ask_permission(self, tool: str, tool_input):
        """Appelé depuis le thread de travail : affiche la question dans Jimmy et attend la réponse."""
        req = {"tool": tool, "input": tool_input, "done": threading.Event(), "answer": (False, False)}
        self.sig.perm.emit(req)
        req["done"].wait(600)
        return req["answer"]

    def _show_permission(self, req) -> None:
        try:
            what = describe_tool(req["tool"], req["input"])
            self.raise_()
            self.activateWindow()
            box = QMessageBox(self)
            box.setWindowTitle("Autorisation demandée")
            box.setText("Jimmy veut faire ceci :")
            box.setInformativeText(what)
            yes = box.addButton("Autoriser", QMessageBox.AcceptRole)
            always = box.addButton(f"Toujours ({req['tool']}, cette session)", QMessageBox.AcceptRole)
            box.addButton("Refuser", QMessageBox.RejectRole)
            box.setStyleSheet(STYLE)
            box.exec()
            clicked = box.clickedButton()
            req["answer"] = (clicked in (yes, always), clicked is always)
            self.add_system(f"{'Autorisé' if clicked in (yes, always) else 'Refusé'} : {what}")
        finally:
            req["done"].set()

    # ------------------------------------------------------------ envoi / réponse
    def submit(self, text: str, followup: bool = False, echo: bool = True) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self.busy:
            self.add_message("user", text)
            if self.thinking and self.bridge.inject(text):
                # Vraiment ajouté à la tâche en cours : Claude le prend en compte dès sa prochaine étape.
                self.add_system("Ajouté à la tâche en cours.")
            else:
                # Pas de tâche à qui l'envoyer (il parle, ou attend un accord) : ça part juste après.
                self._queued.append(text)
            if self.thinking:
                self.listener.resume()   # le micro reste ouvert : tu peux continuer à ajouter des précisions
            return
        if self.bridge.blocked_tools:
            # Jimmy a proposé d'ouvrir Claude Code pour valider à l'écran.
            self.bridge.blocked_tools = []
            ok, _always = parse_consent(text)
            if ok:
                self.add_message("user", text)
                prompt = (
                    "Depuis Jimmy, cette demande a été bloquée faute de validation à l'écran. "
                    "Refais-la ici et demande-moi la validation : " + self._last_request
                )
                if self.bridge.open_in_terminal(prompt):
                    self._on_reply("J'ouvre Claude Code avec ta demande, valide à l'écran.")
                else:
                    self._on_reply("Je ne trouve pas Claude Code sur cet ordinateur.")
                return
            if ok is False:
                self.add_message("user", text)
                self._on_reply("D'accord, on laisse tomber.")
                return
        consent = None
        if self.bridge.pending_tools:
            ok, always = parse_consent(text)
            if ok:
                consent = always
            else:
                self.bridge.deny()
                if ok is False:
                    self.add_message("user", text)
                    self._on_reply("D'accord, je n'y touche pas.")
                    return
        if (consent is None and self.cfg.get("ctx_auto", True) and self.bridge.session_id
                and self._ctx_pct() >= float(self.cfg.get("ctx_threshold", 70))):
            self._handoff()     # discussion déjà trop grosse : ce message part dans une nouvelle discussion
        self.busy = True
        self.thinking = True
        self.listener.pause()
        if echo:
            self.add_message("user", text)
        self.set_state("thinking")
        self._steps_this_turn = 0
        self._last_step = None
        prompt = text
        if consent is None:
            self._last_request = text   # reprise dans Claude Code si l'action est bloquée
        if followup and consent is None:
            # Phrase captée sans « Jimmy » juste après une réponse : peut-être pas pour lui.
            prompt = FOLLOWUP_NOTE + text
        if self._handoff_note and consent is None:
            prompt = self._handoff_note + "\n\n" + prompt
            self._handoff_note = ""
        threading.Thread(target=self._work, args=(prompt, consent), daemon=True).start()

    def _work(self, text: str, consent=None) -> None:
        try:
            if consent is not None:
                self.sig.reply.emit(self.bridge.approve(remember=consent))
            else:
                self.sig.reply.emit(self.bridge.ask(text))
        except ClaudeError as e:
            self.sig.failure.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.sig.failure.emit(f"Erreur inattendue : {e}")

    def _on_reply(self, text: str) -> None:
        if (self.listener.state == "listening" and not self.bridge.pending_tools and not self._queued
                and text.strip().upper().strip(".! ") != "IGNORER"):
            # Tu es en train de parler : on n'écrase pas ta phrase. La réponse s'affiche sans être lue,
            # le micro reste ouvert et ta phrase part normalement dans la foulée.
            self.thinking = False
            self._long_retry = False
            self.refresh_sessions()
            self.refresh_usage()
            self._refresh_ctx()
            self.add_message("assistant", text)
            self._last_reply = ""
            self.busy = False
            self.speaking = False
            self.set_state("listening")
            return
        self.busy = True
        self.listener.pause()
        self.thinking = False
        self._long_retry = False
        self.refresh_sessions()
        self.refresh_usage()
        self._refresh_ctx()
        if text.strip().upper().strip(".! ") == "IGNORER":
            self.add_system("Phrase ignorée : elle ne m'était pas adressée.")
            self._last_reply = ""
            self._finish()
            return
        if self._queued and not self.bridge.pending_tools:
            # Un message est en attente : on affiche la réponse sans la lire, puis on enchaîne.
            self.add_message("assistant", text)
            self._last_reply = ""
            self._finish()
            return
        if self.bridge.pending_tools:
            text += (
                f"\n\nJ'ai besoin de ton accord pour utiliser {', '.join(self.bridge.pending_tools)}."
                " Tu autorises ? Réponds oui, ou oui toujours."
            )
        self._last_reply = text
        if self.btn_voice.isChecked() and text and not self._remote_turn:
            # Le texte s'écrit au rythme de la voix, puis le message complet s'affiche.
            self._remote_emit({"type": "message", "role": "assistant", "text": text})
            self._live_text = text
            self.chat.begin_live()
            self.speaking = True
            self.set_state("speaking")
            self.speaker.speak(text)
        else:
            self.add_message("assistant", text)
            self._finish()

    def _on_speech_done(self) -> None:
        if self._live_text is not None:
            self.chat.end_live(self._live_text)
            self._live_text = None
        self._finish()

    def _on_failure(self, msg: str) -> None:
        self.thinking = False
        if "too long" in msg.lower() and not self._long_retry and self._last_request and self.bridge.session_id:
            self._long_retry = True
            req = self._last_request
            self._handoff(forced=True)
            self._last_reply = ""
            self._finish()
            QTimer.singleShot(0, lambda: self.submit(req))
            return
        self.add_system(msg)
        self.refresh_sessions()
        self._last_reply = ""
        self._finish()

    def _finish(self) -> None:
        self.busy = False
        self.thinking = False
        self.speaking = False
        if not self._queued:
            self._remote_turn = False
        self._remote_emit({"type": "state", "state": "idle", "busy": False})
        self.listener.resume()
        if self._queued:
            nxt, self._queued = "\n".join(self._queued), []
            self._last_reply = ""
            QTimer.singleShot(0, lambda: self.submit(QUEUE_NOTE + nxt, echo=False))
            return
        if self._ctx_pct() >= float(self.cfg.get("ctx_threshold", 70)) and self.cfg.get("ctx_auto", True):
            self._handoff()
        reply, self._last_reply = self._last_reply, ""
        if not self.btn_relisten.isChecked() or self.listener.muted:
            pass   # Relance coupée : Jimmy ne se remet pas à écouter tout seul
        elif self.bridge.pending_tools or reply.rstrip().endswith("?"):
            # Jimmy attend une réponse : on écoute directement, sans « Jimmy ».
            self.listener.listen_now(float(self.cfg.get("question_listen_seconds", 8)), followup=True)
        elif reply and self.cfg.get("followup_seconds", 4) > 0:
            # Petite fenêtre pour enchaîner sans redire « Jimmy ».
            self.listener.listen_now(float(self.cfg.get("followup_seconds", 4)), followup=True)
        self.set_state(self.listener.state if self.listener.state not in ("loading", "sent") else "wake")

    # ------------------------------------------------------------------ boutons
    def on_heard(self, text: str) -> None:
        """Phrase reconnue au micro : envoyée directement, ou écrite dans la zone en mode Dictée."""
        self.input.end_preview()
        if self.btn_dict.isChecked() and not self.bridge.pending_tools:
            self.input.append_text(text)
            self.listener.resume()
            return
        self.submit(text, followup=self.listener.last_followup)

    def on_send(self) -> None:
        text = self.input.toPlainText()
        self.input.clear()
        self.submit(text)

    def on_talk(self) -> None:
        """1er clic : Jimmy écoute (bouton allumé). 2e clic : ce qui est dit est validé.

        Marche aussi pendant que Jimmy travaille : la phrase s'ajoute à la file (ou s'écrit en Dictée).
        """
        if self.speaking:
            self.speaker.stop()
        elif self.listener.state == "listening":
            self.listener.flush_now()   # ce qui est déjà dit est gardé (envoyé ou écrit en dictée)
            return
        if self.btn_mute.isChecked():
            self.btn_mute.setChecked(False)
        self.listener.listen_now()

    def on_stop(self) -> None:
        self._queued = []
        if self.thinking:
            self.bridge.cancel()
        if self.speaking:
            self.speaker.stop()

    def on_new(self) -> None:
        if self.busy:
            self.add_system("Attends la fin de la tâche en cours (ou appuie sur Stop).")
            return
        self.bridge.reset()
        self._handoff_note = ""
        self._refresh_ctx()
        self._clear_chat()
        self.session_list.clearSelection()
        self.refresh_sessions()
        self.add_system("Nouvelle discussion.")
        self._swap_anim()
        self.input.setFocus()

    def on_folder(self) -> None:
        start = self.cfg.get("workdir") or ""
        path = QFileDialog.getExistingDirectory(self, "Dossier de travail de Claude Code", start)
        if path:
            self.cfg.set("workdir", path)
            self.bridge.reset()
            self._refresh_folder_label()
            self._clear_chat()
            self.refresh_sessions()
            self.add_system(f"Dossier de travail : {path}. Nouvelle conversation démarrée.")

    def on_voice_preset(self, name: str) -> None:
        self.cfg.set("voice_preset", name)

    def on_voice_test(self) -> None:
        """Lit une phrase d'exemple avec la voix choisie : le texte s'écrit en direct comme d'habitude."""
        if self.speaking and self._live_text is not None:
            self.speaker.stop()   # 2e clic : on coupe
            return
        if self.busy:
            self.add_system("Attends la fin de la tâche en cours pour tester une voix.")
            return
        self.busy = self.speaking = True
        self.listener.pause()
        self._live_text = TEST_SENTENCE
        self._last_reply = ""
        self.chat.begin_live()
        self.set_state("speaking")
        self.speaker.speak(TEST_SENTENCE)

    def on_voice_toggle(self, on: bool) -> None:
        self.cfg.set("voice_enabled", bool(on))
        if not on:
            self.speaker.stop()

    def on_auto_toggle(self, on: bool) -> None:
        self.cfg.set("wake_words_enabled", bool(on))
        self.listener.set_wake_enabled(bool(on))

    def on_mute(self, on: bool) -> None:
        self.listener.set_muted(bool(on))
        self.btn_mute.setText("Muet" if on else "Micro")
        self.btn_mute.set_icon("mic_off" if on else "mic")
        if on and not self.busy:
            self.set_state("muted")

    def on_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self.speaker, self)
        dlg.setStyleSheet(themed_style(self.cfg))
        if not dlg.exec():
            return
        old_whisper = self.cfg.get("whisper_model")
        old_restart = {k: self.cfg.get(k) for k in RESTART_KEYS}
        for key, value in dlg.values().items():
            self.cfg.data[key] = value
        self.cfg.save()
        self._apply_look()
        self.listener.restart()
        self._refresh_placeholder()
        self._update_eco()
        if self.listener.state == "wake" and not self.busy:
            self.set_state("wake")
        if any(self.cfg.get(k) != v for k, v in old_restart.items()):
            self.btn_restart.show()   # redémarrage nécessaire : le bouton ⏻ apparaît en haut

    def closeEvent(self, event) -> None:
        if self.remote is not None:
            self.remote.shutdown()
        self.bridge.cancel()
        self.speaker.stop()
        self.listener.stop()
        super().closeEvent(event)
