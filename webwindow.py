"""Fenêtre web de Jimmy : l'interface est une vraie page HTML / CSS / JavaScript (dossier webui) affichée dans l'appli
par Qt WebEngine, avec un pont (QWebChannel) vers le même cerveau que l'ancienne fenêtre.

JimmyWindow garde toute la logique (écoute, Claude, voix, IA locale, discussions). Ici on remplace seulement les
« widgets » par des adaptateurs qui envoient des événements à la page, et la page rappelle Python par des slots.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

import sessions
import theme
import window as W
from config import ACCENTS, app_dir
from speaker import DEFAULT_PRESET, VOICE_PRESETS, resolve_preset
from version import __version__
from widgets import THEME

TOGGLES = ("voice_enabled", "wake_words_enabled", "auto_relisten", "long_mode", "dictation")


class _Null:
    """Tout appel est accepté et ne fait rien : pour les éléments de l'ancienne interface qui n'existent plus."""

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Item:
    """Une discussion vue comme un élément de liste (l'ancien code lit data() et toolTip())."""

    def __init__(self, sid: str, title: str = ""):
        self.sid, self.title = sid, title

    def data(self, _role=None):
        return self.sid

    def toolTip(self) -> str:
        return self.title


def web_dir() -> str:
    return str(app_dir() / "webui")


def available() -> bool:
    return os.path.isfile(os.path.join(web_dir(), "index.html"))


# ------------------------------------------------------------------ pont page <-> Python
class Bridge(QObject):
    event = Signal(str)

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._ready = False
        self._buffer = []

    @staticmethod
    def _later(fn) -> None:
        """Une fenêtre ouverte DANS l'appel venu de la page bloque la page (et ses clics) : on l'ouvre juste après."""
        QTimer.singleShot(0, fn)

    @Slot(bool)
    def setLocal(self, on: bool) -> None:
        self._later(lambda: (self.win.set_local_enabled(bool(on)), self.win._push_prefs()))

    def emit(self, ev: dict) -> None:
        raw = json.dumps(ev, ensure_ascii=False)
        if self._ready:
            self.event.emit(raw)
        else:
            self._buffer.append(raw)        # la page se charge : on garde les événements pour elle

    @Slot()
    def ready(self) -> None:
        self._ready = True
        self.win._push_prefs()
        for raw in self._buffer:
            self.event.emit(raw)
        self._buffer = []
        self.win._push_all()

    @Slot(str)
    def send(self, text: str) -> None:
        self.win.submit(text)

    @Slot()
    def talk(self) -> None:
        self.win.on_talk()

    @Slot(bool)
    def mute(self, on: bool) -> None:
        self.win.btn_mute.checked = bool(on)
        self.win.on_mute(bool(on))

    @Slot()
    def stop(self) -> None:
        self.win.on_stop()

    @Slot()
    def newChat(self) -> None:
        self.win.on_new()

    @Slot(str)
    def openSession(self, sid: str) -> None:
        self.win.switch_session(sid)

    @Slot(str)
    def renameSession(self, sid: str) -> None:
        self._later(lambda: self.win._rename_session(_Item(sid, self.win._title_of(sid))))

    @Slot(str)
    def deleteSession(self, sid: str) -> None:
        self._later(lambda: self.win._delete_session(_Item(sid, self.win._title_of(sid))))

    @Slot()
    def openCC(self) -> None:
        self.win.on_open_cc()

    @Slot()
    def openMobile(self) -> None:
        self._later(self.win.on_remote_settings)

    @Slot()
    def pickFolder(self) -> None:
        self._later(self.win.on_folder)

    @Slot()
    def openSettings(self) -> None:
        self._later(lambda: (self.win.on_settings(), self.win._push_prefs()))

    @Slot()
    def restartApp(self) -> None:
        self.win.restart_app()

    @Slot()
    def voiceTest(self) -> None:
        self.win.on_voice_test()

    @Slot(str)
    def voicePreset(self, name: str) -> None:
        self.win.on_voice_preset(name)

    @Slot(str, str)
    def setCost(self, key: str, value: str) -> None:
        self.win._set_cost(key, value)

    @Slot(str)
    def setRoute(self, value: str) -> None:
        self.win.cfg.set("route", value)
        self.win._refresh_placeholder()

    @Slot(str, bool)
    def toggle(self, key: str, on: bool) -> None:
        if key not in TOGGLES:
            return
        self.win.cfg.set(key, bool(on))
        if key == "voice_enabled":
            self.win.on_voice_toggle(on)
        elif key == "wake_words_enabled":
            self.win.on_auto_toggle(on)

    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    @Slot(str)
    def openUrl(self, url: str) -> None:
        if re.match(r"^https?://", url):
            QDesktopServices.openUrl(QUrl(url))


class _Page(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)      # les liens s'ouvrent dans le navigateur, jamais dans Jimmy
            return False
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):
        lv = QWebEnginePage.JavaScriptConsoleMessageLevel
        if level in (lv.WarningMessageLevel, lv.ErrorMessageLevel):
            print(f"[page] {message} ({source}:{line})", file=sys.stderr)


# ------------------------------------------------------------------ adaptateurs des anciens widgets
class _Chat:
    def __init__(self, emit):
        self.emit = emit

    def add_user(self, text):
        self.emit({"t": "msg", "role": "user", "text": text})

    def add_assistant(self, text, label="JIMMY", color="#e84df5"):
        self.emit({"t": "msg", "role": "assistant", "text": text, "label": label, "color": color if label != "JIMMY" else ""})

    def add_system(self, text):
        self.emit({"t": "system", "text": text})

    def add_step(self, text, first=False):
        self.emit({"t": "step", "text": text, "first": bool(first)})

    def begin_live(self):
        self.emit({"t": "live_begin"})

    def live_chunk(self, text, duration, words=None):
        self.emit({"t": "live_chunk", "text": text, "duration": duration})

    def end_live(self, full_text):
        self.emit({"t": "live_end", "text": full_text, "label": "JIMMY", "color": ""})

    def clear(self):
        self.emit({"t": "clear"})

    def apply_theme(self):
        pass


class _Orb:
    def __init__(self, emit):
        self.emit = emit
        self._t = 0.0

    def set_state(self, state):
        self.emit({"t": "state", "state": state})

    def set_level(self, rms):
        now = time.monotonic()
        if now - self._t >= 0.05:             # 20 images par seconde au plus
            self._t = now
            self.emit({"t": "level", "rms": float(rms)})

    def set_psychosis(self, level):
        self.emit({"t": "psy", "level": float(level)})

    def set_palette(self, *_a):
        pass

    def set_options(self, *_a):
        pass


class _Label:
    """Texte affiché à un endroit précis de la page."""

    def __init__(self, emit, kind, extra=None):
        self.emit, self.kind, self.extra = emit, kind, extra or {}
        self.text = ""

    def setText(self, text):
        self.text = text
        self.emit({"t": self.kind, "text": text, **self.extra})

    def setToolTip(self, *_a):
        pass


class _Ctx:
    """Jauge de contexte : un seul événement regroupe le texte, le pourcentage, la couleur et l'info-bulle."""

    def __init__(self, emit):
        self.emit, self.pct, self.color, self.label, self.tip = emit, 0, "", "Contexte 0 %", ""

    def push(self):
        self.emit({"t": "ctx", "pct": self.pct, "color": self.color, "label": self.label, "tip": self.tip})


class _CtxLabel:
    def __init__(self, ctx):
        self.ctx = ctx

    def setText(self, t):
        self.ctx.label = t
        self.ctx.push()

    def setToolTip(self, t):
        self.ctx.tip = t
        self.ctx.push()


class _CtxBar:
    def __init__(self, ctx):
        self.ctx = ctx

    def setValue(self, v):
        self.ctx.pct = int(v)

    def setStyleSheet(self, css):
        m = re.search(r"background:\s*(#[0-9a-fA-F]{3,8})", css or "")
        self.ctx.color = m.group(1) if m else ""
        self.ctx.push()


class _UsageBar:
    def __init__(self, emit, index):
        self.emit, self.i = emit, index
        self.pct, self.text, self.color = 0, "—", ""

    def setValue(self, v):
        self.pct = int(v)

    def setStyleSheet(self, css):
        m = re.search(r"background:\s*(#[0-9a-fA-F]{3,8})", css or "")
        self.color = m.group(1) if m else ""
        self.push()

    def push(self):
        self.emit({"t": "usage", "i": self.i, "pct": self.pct, "text": self.text, "color": self.color})

    def setToolTip(self, *_a):
        pass


class _UsageText:
    def __init__(self, bar):
        self.bar = bar

    def setText(self, t):
        self.bar.text = t


class _UsageTitle:
    def __init__(self, emit):
        self.emit = emit

    def setText(self, t):
        self.emit({"t": "usage_title", "text": t})


class _Toggle:
    def __init__(self, cfg, key, default):
        self.cfg, self.key, self.default = cfg, key, default

    def isChecked(self):
        return bool(self.cfg.get(self.key, self.default))

    def setChecked(self, v):
        self.cfg.set(self.key, bool(v))

    def __getattr__(self, name):
        return lambda *a, **k: None


class _MuteBtn:
    def __init__(self, emit):
        self.emit, self.checked = emit, False

    def isChecked(self):
        return self.checked

    def setChecked(self, v):
        self.checked = bool(v)
        self.emit({"t": "mute", "on": self.checked})

    def setText(self, *_a):
        pass

    def set_icon(self, *_a):
        pass


class _TalkBtn:
    def __init__(self, emit):
        self.emit = emit

    def set_active(self, active):
        self.emit({"t": "talk", "active": bool(active)})

    def setText(self, *_a):
        pass

    def set_icon(self, *_a):
        pass


class _RestartBtn:
    def __init__(self, emit):
        self.emit = emit

    def show(self):
        self.emit({"t": "restart_needed"})

    def __getattr__(self, name):
        return lambda *a, **k: None


class _Input:
    def __init__(self, emit):
        self.emit = emit

    def set_preview(self, text):
        self.emit({"t": "preview", "text": text})

    def end_preview(self):
        self.emit({"t": "preview", "text": ""})

    def setPlaceholderText(self, text):
        self.emit({"t": "placeholder", "text": text})

    def append_text(self, text):
        self.emit({"t": "append", "text": text})

    def setFocus(self):
        self.emit({"t": "focus"})

    def toPlainText(self):
        return ""

    def clear(self):
        pass


class _RouteBox:
    def __init__(self, win):
        self.win = win

    def setVisible(self, _v):
        self.win._push_prefs()

    def currentData(self):
        return self.win.cfg.get("route", "claude")


class _SessionList:
    """L'ancien code vide / remplit / interroge la liste : ici la page s'en occupe, on ne garde que ce qu'il faut."""

    def clear(self):
        pass

    def addItem(self, *_a):
        pass

    def clearSelection(self):
        pass

    def count(self):
        return 0

    def item(self, _i):
        return None

    def currentItem(self):
        return None


# ------------------------------------------------------------------ la fenêtre
class WebJimmyWindow(W.JimmyWindow):
    def _build_ui(self) -> None:
        self.setWindowTitle("Jimmy")
        self.jsb = Bridge(self)
        em = self.jsb.emit
        self.chat = _Chat(em)
        self.orb = _Orb(em)
        self.status_lbl = _Label(em, "status")
        self.folder_lbl = _Label(em, "folder")
        ctx = _Ctx(em)
        self._ctx = ctx
        self.ctx_lbl, self.ctx_bar = _CtxLabel(ctx), _CtxBar(ctx)
        self.usage_session, self.usage_week = _UsageBar(em, 1), _UsageBar(em, 2)
        self.usage_labels = {self.usage_session: _UsageText(self.usage_session), self.usage_week: _UsageText(self.usage_week)}
        self.usage_title = _UsageTitle(em)
        self.btn_voice = _Toggle(self.cfg, "voice_enabled", True)
        self.btn_relisten = _Toggle(self.cfg, "auto_relisten", True)
        self.btn_dict = _Toggle(self.cfg, "dictation", False)
        self.btn_mute = _MuteBtn(em)
        self.btn_talk = _TalkBtn(em)
        self.btn_restart = _RestartBtn(em)
        self.input = _Input(em)
        self.route_box = _RouteBox(self)
        self.session_list = _SessionList()
        self.sweep = self.logo = self.subtitle = self.chat_frame = _Null()

        view = QWebEngineView(self)
        page = _Page(view)
        page.setBackgroundColor(QColor("#0b0d12"))
        view.setPage(page)
        s = page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        view.setContextMenuPolicy(Qt.NoContextMenu)
        channel = QWebChannel(page)
        channel.registerObject("bridge", self.jsb)
        page.setWebChannel(channel)
        self.view = view
        self.setCentralWidget(view)
        view.setUrl(QUrl.fromLocalFile(os.path.join(web_dir(), "index.html")))
        self._place_window()

    # ---- éléments d'interface qui n'ont plus de widget
    def _title_of(self, sid: str) -> str:
        for s in self._sessions_cache:
            if s["id"] == sid:
                return s["title"]
        return "cette discussion"

    def _push_prefs(self) -> None:
        cfg = self.cfg
        main, second = ACCENTS.get(cfg.get("accent"), ACCENTS["Cyan néon"])
        voice = resolve_preset(cfg.get("voice_preset"))
        self.jsb.emit({"t": "prefs", "p": {
            "accent": [main, second], "version": __version__, "chat_font": int(cfg.get("chat_font", 15)),
            "models": [[l, v] for l, v in W.MODELS], "model": cfg.get("model") or "",
            "efforts": [[l, v] for l, v in W.EFFORTS], "effort": cfg.get("effort") or "",
            "voices": list(VOICE_PRESETS), "voice_preset": voice if voice in VOICE_PRESETS else DEFAULT_PRESET,
            "toggles": {k: bool(cfg.get(k, d)) for k, d in (("voice_enabled", True), ("wake_words_enabled", True),
                                                           ("auto_relisten", True), ("long_mode", False), ("dictation", False))},
            "local_enabled": bool(cfg.get("local_enabled", False)), "route": cfg.get("route", "claude"),
            "wake_label": self._wake_label(), "psy": self._psy_level() > 0,
        }})

    def _push_all(self) -> None:
        """La page vient de se charger : on lui renvoie l'état courant."""
        self._refresh_folder_label()
        self._refresh_ctx()
        self._refresh_placeholder()
        self.refresh_sessions()
        self.refresh_usage()
        self.set_state(self.listener.state if self.listener.state not in ("loading", "sent") else "loading")

    def _apply_look(self) -> None:
        main, second = ACCENTS.get(self.cfg.get("accent"), ACCENTS["Cyan néon"])
        THEME.update(accent=main, accent2=second, effects=bool(self.cfg.get("effects", True)))
        theme.set_accent(main)
        self.setStyleSheet(W.themed_style(self.cfg))      # les fenêtres Qt (réglages, questions) gardent le thème
        QApplication.setWindowIcon(W.make_icon(256, second if main.lower() != "#22d3ee" else None,
                                               main if main.lower() != "#22d3ee" else None))
        if hasattr(self, "jsb"):
            self._push_prefs()
        self._refresh_ctx()

    def _arm_glitch(self) -> None:
        pass            # pas de glitchs dans l'interface web : sobre

    def _micro_glitch(self) -> None:
        pass

    def _apply_psychosis(self) -> None:
        if hasattr(self, "jsb"):
            self.jsb.emit({"t": "psy", "level": float(self._psy_level())})

    def _swap_anim(self) -> None:
        self.jsb.emit({"t": "swap"})

    def _chat_region(self):
        from PySide6.QtCore import QRectF
        return QRectF(0, 0, self.width(), self.height())

    def _refresh_placeholder(self) -> None:
        route = self._route() if hasattr(self, "_route") else "claude"
        who = {"local": "à l'IA locale", "auto": "(Auto : l'IA locale d'abord)"}.get(route, "")
        self.input.setPlaceholderText(f"Écris {who} ici, ou dis « {self._wake_label()} »".replace("  ", " "))

    def refresh_sessions(self) -> None:
        wd = self.bridge.workdir()
        pn = self._pending_name
        if pn and self.bridge.session_id and self.bridge.session_id != pn[2]:
            sessions.set_name(self.bridge.session_id, pn[0], manual=pn[1])
            self._pending_name = None
        full = sessions.full_ids()
        listed = sessions.list_sessions(wd)
        sessions.ensure_names(listed)
        cache = [{"id": sid, "title": title, "when": when, "full": sid in full} for sid, title, when in listed]
        self._sessions_cache = cache
        self.jsb.emit({"t": "sessions", "items": cache, "current": self.bridge.session_id or ""})
        self._remote_emit(self._sessions_event())

    def _on_usage(self, data) -> None:
        super()._on_usage(data)
        for bar in (self.usage_session, self.usage_week):
            bar.push()

    def on_new(self) -> None:
        super().on_new()
        self.jsb.emit({"t": "sessions", "items": self._sessions_cache, "current": self.bridge.session_id or ""})


def selftest() -> int:
    """Ouvre la page dans un navigateur intégré invisible, vérifie que le pont Python <-> page fonctionne, écrit le résultat."""
    from PySide6.QtCore import QTimer
    from config import data_dir
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    out = data_dir() / "webtest.txt"
    result = {"page": "", "channel": "", "dom": ""}

    class _B(QObject):
        event = Signal(str)

        @Slot()
        def ready(self):
            result["channel"] = "ok"

    view = QWebEngineView()
    page = _Page(view)
    view.setPage(page)
    ch = QWebChannel(page)
    probe_bridge = _B()          # garder une référence : un objet Python libéré planterait la page
    ch.registerObject("bridge", probe_bridge)
    page.setWebChannel(ch)
    view.resize(900, 600)
    view.setUrl(QUrl.fromLocalFile(os.path.join(web_dir(), "index.html")))
    view.show()

    def probe():
        page.runJavaScript("document.title + '|' + (document.querySelector('#sessions') ? 'dom-ok' : 'dom-absent') + '|' + (typeof QWebChannel)",
                           lambda r: (result.update(page=str(r)), None))

    def finish():
        ok = result["channel"] == "ok" and "dom-ok" in result["page"]
        out.write_text(f"{'OK' if ok else 'ECHEC'}\n{json.dumps(result, ensure_ascii=False)}\n", encoding="utf-8")
        app.quit()

    QTimer.singleShot(4000, probe)
    QTimer.singleShot(7000, finish)
    app.exec()
    return 0 if out.exists() and out.read_text(encoding="utf-8").startswith("OK") else 1
