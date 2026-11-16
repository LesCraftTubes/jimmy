"""Fenêtre web de Jimmy : l'interface est une vraie page HTML / CSS / JavaScript (dossier webui) affichée dans l'appli
par Qt WebEngine, avec un pont (QWebChannel) vers le même cerveau que l'ancienne fenêtre.

JimmyWindow garde toute la logique (écoute, Claude, voix, IA locale, discussions). Ici on remplace seulement les
« widgets » par des adaptateurs qui envoient des événements à la page, et la page rappelle Python par des slots.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

import sessions
import theme
import window as W
from config import ACCENTS, app_dir, data_dir
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
        self.win.submit(self.win.compose_attachments(text))

    @Slot()
    def checkUpdate(self) -> None:
        self.win.check_update_now()

    @Slot()
    def pickFiles(self) -> None:
        self._later(self.win.pick_files)

    @Slot(str)
    def detach(self, path: str) -> None:
        self.win.detach_file(path)

    @Slot(str, str)
    def dropData(self, name: str, b64: str) -> None:
        self.win.drop_data(name, b64)

    @Slot()
    def openAttachFolder(self) -> None:
        self._later(self.win.open_attach_folder)

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
    on_file = None          # appelé avec le chemin d'un fichier ou dossier déposé sur la page

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "file" and is_main_frame and self.on_file:
            path = os.path.abspath(url.toLocalFile())
            if not os.path.normcase(path).startswith(os.path.normcase(os.path.abspath(web_dir()))):
                self.on_file(path)
                return False        # la page reste en place : le fichier est joint, pas ouvert
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)      # les liens s'ouvrent dans le navigateur, jamais dans Jimmy
            return False
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):
        lv = QWebEnginePage.JavaScriptConsoleMessageLevel
        if level in (lv.WarningMessageLevel, lv.ErrorMessageLevel):
            print(f"[page] {message} ({source}:{line})", file=sys.stderr)


# ------------------------------------------------------------------ adaptateurs des anciens widgets
class _DropFilter(QObject):
    """Attrape les fichiers déposés sur la fenêtre AU NIVEAU DE QT : on a toujours le vrai chemin, quelle que soit la taille,
    sans dépendre de ce que Chromium fait d'un fichier déposé."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.dragging = False

    def _inside(self, obj) -> bool:
        v = self.win.view
        return obj is v or (isinstance(obj, QWidget) and v.isAncestorOf(obj))

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t not in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop, QEvent.Type.DragLeave) or not self._inside(obj):
            return False
        if t == QEvent.Type.DragLeave:
            self._show(False)
            return False
        md = ev.mimeData()
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md and md.hasUrls() else []
        if not paths:
            return False
        if t == QEvent.Type.Drop:
            self._show(False)
            self.win.attach_paths(paths)
        else:
            self._show(True)
        ev.acceptProposedAction()
        return True

    def _show(self, on: bool) -> None:
        if on != self.dragging:
            self.dragging = on
            self.win.jsb.emit({"t": "dragging", "on": on})


class _AttachSig(QObject):
    done = Signal(object)


class _UpdSig(QObject):
    state = Signal(str, str, int)      # état, texte à afficher, pourcentage
    install = Signal(str)              # chemin de l'installateur téléchargé


class _Chat:
    next_label = None            # (étiquette, couleur) pour la prochaine réponse de Claude après un relais de l'IA locale

    def __init__(self, emit):
        self.emit = emit

    def add_user(self, text):
        self.emit({"t": "msg", "role": "user", "text": text})

    def add_assistant(self, text, label="JIMMY", color="#e84df5"):
        if label == "JIMMY" and self.next_label:
            label, color = self.next_label
            self.next_label = None
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
        label, color = self.next_label or ("JIMMY", "")
        self.next_label = None
        self.emit({"t": "live_end", "text": full_text, "label": label, "color": color})

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
        self._usig = _UpdSig()
        self._usig.state.connect(self._on_update_state)
        self._usig.install.connect(self._run_installer)
        self._updating = False
        self._attach = []                    # pièces jointes en attente d'envoi
        self._asig = _AttachSig()
        self._asig.done.connect(self._attached)
        self.sweep = self.logo = self.subtitle = self.chat_frame = _Null()

        from brain import web as _web
        from brain.browser_search import HeadlessSearch
        self._hsearch = HeadlessSearch()
        _web.browser_search = self._hsearch.search      # l'IA locale cherche sur Internet par là, sans ouvrir ton navigateur

        view = QWebEngineView(self)
        page = _Page(view)
        page.on_file = lambda path: self.attach_paths([path])
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
        view.setAcceptDrops(True)
        self._dropfilter = _DropFilter(self)

        def hook_drops(_ok=True) -> None:
            for w in [view, view.focusProxy(), *view.findChildren(QWidget)]:
                if w is not None:
                    w.setAcceptDrops(True)
                    w.installEventFilter(self._dropfilter)
        view.loadFinished.connect(lambda ok: (hook_drops(), QTimer.singleShot(1500, hook_drops)))
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

    # ---- bouton « Vérifier les mises à jour » : cherche, et s'il y en a une, télécharge et lance l'installation tout de suite
    def check_update_now(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._usig.state.emit("checking", "Recherche d'une mise à jour…", 0)

        def work() -> None:
            try:
                import updater
                from version import UPDATE_REPO
                repo = self.cfg.get("update_repo") or UPDATE_REPO
                upd = updater.check(repo)
                if upd is None:
                    self._usig.state.emit("none", f"Jimmy est à jour (version {__version__}).", 0)
                    return
                if not updater.can_self_update():
                    self._usig.state.emit("manual", f"La version {upd.version} est disponible. La mise à jour automatique ne marche que "
                                                    "sur la version installée : télécharge-la sur la page des releases.", 0)
                    return
                self._usig.state.emit("downloading", f"Mise à jour {upd.version} : téléchargement…", 0)
                last = [-1]

                def prog(done: int, total: int) -> None:
                    pct = int(done * 100 / total) if total else 0
                    if pct != last[0]:
                        last[0] = pct
                        self._usig.state.emit("downloading", f"Mise à jour {upd.version} : téléchargement {pct} %", pct)
                path = updater.download(upd, prog)
                self._usig.state.emit("installing", f"Installation de la {upd.version}… Jimmy se ferme puis se rouvre tout seul.", 100)
                self._usig.install.emit(str(path))
            except Exception as e:  # noqa: BLE001
                self._usig.state.emit("error", f"Mise à jour impossible : {e}", 0)
        threading.Thread(target=work, daemon=True).start()

    def _on_update_state(self, state: str, text: str, pct: int) -> None:
        if state in ("none", "manual", "error"):
            self._updating = False
        self.jsb.emit({"t": "update", "state": state, "text": text, "pct": pct})

    def _run_installer(self, path: str) -> None:
        import updater
        updater.run_installer(Path(path))
        QApplication.quit()

    # ---- à quoi sert l'IA locale : compteurs visibles dans la barre latérale
    def _push_local_stats(self) -> None:
        if not hasattr(self, "jsb"):
            return
        st = self.cfg.get("local_stats") or {}
        self.jsb.emit({"t": "localstats", "local": int(st.get("local", 0)), "relay": int(st.get("relay", 0)),
                       "direct": int(st.get("direct", 0))})

    # ---- pièces jointes : copiées dans un dossier de Jimmy, jointes au message (le chemin reste dans la discussion)
    @staticmethod
    def _size_text(n: int) -> str:
        for unit in ("o", "Ko", "Mo", "Go"):
            if n < 1024 or unit == "Go":
                return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
            n /= 1024

    def _attach_dir(self) -> Path:
        d = data_dir() / "pieces_jointes" / time.strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _unique(folder: Path, name: str) -> Path:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "fichier"
        target, n = folder / name, 1
        while target.exists():
            n += 1
            target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        return target

    def attach_paths(self, paths) -> None:
        """Copie les fichiers (ou dossiers) dans le dossier des pièces jointes, quelle que soit la taille, sans bloquer la fenêtre."""
        paths = [p for p in paths if p and os.path.exists(p)]
        if not paths:
            return
        dest = self._attach_dir()
        self.jsb.emit({"t": "toast", "text": f"Copie de {len(paths)} élément(s) en cours…"})

        def work() -> None:
            items = []
            for src in paths:
                try:
                    target = self._unique(dest, os.path.basename(src.rstrip("\\/")))
                    if os.path.isdir(src):
                        shutil.copytree(src, target)
                        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                    else:
                        shutil.copy2(src, target)
                        size = target.stat().st_size
                    items.append({"name": target.name, "path": str(target), "size": size})
                except Exception as e:  # noqa: BLE001
                    items.append({"error": f"{os.path.basename(src)} : {e}"})
            self._asig.done.emit(items)
        threading.Thread(target=work, daemon=True).start()

    def _attached(self, items) -> None:
        for it in items:
            if "error" in it:
                self.jsb.emit({"t": "toast", "text": "Copie impossible : " + it["error"], "err": True})
            else:
                self._attach.append(it)
        self._emit_attached()
        ok = [i for i in items if "error" not in i]
        if ok:
            self.jsb.emit({"t": "toast", "text": f"{len(ok)} fichier(s) joint(s) : ils partiront avec ton prochain message."})

    def _emit_attached(self) -> None:
        if hasattr(self, "jsb"):
            self.jsb.emit({"t": "attached", "items": [{"name": i["name"], "path": i["path"], "size": self._size_text(i["size"])}
                                                       for i in self._attach]})

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Joindre des fichiers")
        self.attach_paths(paths)

    def drop_data(self, name: str, b64: str) -> None:
        """Repli : fichier déposé dont le chemin n'est pas connu, reçu en base64 depuis la page."""
        try:
            target = self._unique(self._attach_dir(), name)
            target.write_bytes(base64.b64decode(b64))
            self._attached([{"name": target.name, "path": str(target), "size": target.stat().st_size}])
        except Exception as e:  # noqa: BLE001
            self.jsb.emit({"t": "toast", "text": f"Fichier non joint : {e}", "err": True})

    def detach_file(self, path: str) -> None:
        self._attach = [i for i in self._attach if i["path"] != path]
        self._emit_attached()

    def open_attach_folder(self) -> None:
        d = data_dir() / "pieces_jointes"
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(str(d))

    def compose_attachments(self, text: str) -> str:
        """Ajoute au message la liste des fichiers joints (avec leur chemin) et les note en mémoire pour les retrouver plus tard."""
        items, self._attach = self._attach, []
        if not items:
            return text
        self._emit_attached()
        lines = "\n".join(f"- {i['path']} ({self._size_text(i['size'])})" for i in items)
        base = text.strip() or "Regarde les fichiers joints."
        try:
            import jimmy_mem
            jimmy_mem.add_note(f"Pièces jointes du {time.strftime('%d/%m/%Y %H:%M')}",
                               f"Jointes à la demande « {base[:100]} » :\n{lines}", projet="Pièces jointes", tags="pieces-jointes")
        except Exception:  # noqa: BLE001
            pass
        return f"{base}\n\n[Fichiers joints, copiés par Jimmy dans son dossier des pièces jointes :\n{lines}\n]"

    def _push_all(self) -> None:
        """La page vient de se charger : on lui renvoie l'état courant."""
        self._refresh_folder_label()
        self._refresh_ctx()
        self._refresh_placeholder()
        self._push_local_stats()
        self._emit_attached()
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
