"""Le « PC » d'Aurélie : un navigateur intégré à Jimmy (Chromium), invisible, qu'elle pilote pour voir un site comme un humain.

- Elle ouvre une page, la lit (le texte vraiment affiché, JavaScript compris), clique, défile, remplit un champ, fait un rapport
  (erreurs, images cassées, débordements) et prend des CAPTURES.
- Pendant qu'elle travaille, des images réduites partent vers le panneau « Écran en direct » de la fenêtre : on voit le rendu
  en direct. Ces images ne vont JAMAIS vers Claude : elles ne coûtent aucun token.
- Un profil « hors-piste » : ni cookies, ni historique, ni identifiants gardés.

Toutes les méthodes publiques peuvent être appelées depuis n'importe quel fil (sauf celui de l'interface) : le travail se fait
dans le fil de l'interface, l'appelant attend le résultat.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRect, QSize, Qt, QThread, QTimer, QUrl, Signal, Slot

from . import design

instance = None          # le navigateur de la fenêtre (créé par la fenêtre web) ; les outils d'Aurélie s'en servent

VIEW_W, VIEW_H = 1280, 800
MAX_FULL_H = 5000
FRAME_W = 760
FRAME_EVERY_MS = 900
FRAME_KEEP_S = 9.0
_SECRET = re.compile(r"(\.env|\.pem|\.key|\.ppk|id_rsa|id_ed25519|credentials|secret|password|passwd|token|\.kdbx|config\.php)", re.I)


# ------------------------------------------------------------------ dossier des captures
def captures_dir() -> Path:
    from config import data_dir
    d = data_dir() / "captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path() -> Path:
    return captures_dir() / "index.json"


def list_captures(limit: int = 60) -> list:
    """Les dernières captures [{file, caption, ts, url, who}], la plus récente d'abord (celles dont le fichier existe encore)."""
    try:
        rows = json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    rows = [r for r in rows if Path(r.get("file", "")).is_file()]
    return rows[::-1][:limit]


def _remember(row: dict, keep: int = 300) -> None:
    try:
        rows = json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    rows.append(row)
    for old in rows[:-keep]:
        try:
            Path(old.get("file", "")).unlink(missing_ok=True)
            audit_path(old.get("file", "")).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        _index_path().write_text(json.dumps(rows[-keep:], ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def audit_path(png: str) -> Path:
    """Fichier des mesures prises avec une capture (couleurs, contrastes, polices...)."""
    return Path(str(png) + ".audit.json")


def load_audit(png: str) -> dict:
    try:
        return json.loads(audit_path(png).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def purge_captures(days: int = 14) -> int:
    """Supprime les captures de plus de `days` jours (et leurs mesures). Renvoie le nombre de captures retirées."""
    limit, n = time.time() - days * 86400, 0
    for f in captures_dir().glob("cap-*.png.audit.json"):
        try:
            if f.stat().st_mtime < limit:
                f.unlink()
        except OSError:
            pass
    for f in captures_dir().glob("cap-*.png"):
        try:
            if f.stat().st_mtime < limit:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n


def check_url(url: str) -> str:
    """Adresse acceptée par le navigateur d'Aurélie, ou lève ValueError. http(s), localhost et fichiers locaux non secrets."""
    url = (url or "").strip()
    if not url:
        raise ValueError("adresse vide")
    if re.match(r"^[a-z]:[\\/]", url, re.I) or url.startswith("\\\\"):
        url = QUrl.fromLocalFile(url).toString()
    if not re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
        url = "https://" + url
    low = url.lower()
    if low.startswith("file:"):
        path = QUrl(url).toLocalFile()
        if not path or not Path(path).exists():
            raise ValueError("fichier introuvable")
        if _SECRET.search(Path(path).name):
            raise ValueError("fichier refusé (il pourrait contenir un secret)")
        return url
    if not re.match(r"^https?://", low):
        raise ValueError("seules les adresses http(s) et les fichiers locaux sont ouverts")
    return url


# ------------------------------------------------------------------ le navigateur
class LiveBrowser(QObject):
    _call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_frame = None      # (dict) image réduite pour le panneau : {"jpg": base64, "url", "title", "w", "h"}
        self.on_action = None     # (texte) ce que fait Aurélie, en une phrase (fil d'activité du panneau)
        self.on_image = None      # (chemin, légende) une capture à montrer dans la discussion
        self.on_click = None      # (dict) {"x","y","w","h"} : où elle a cliqué (anneau animé sur l'image)
        self.on_state = None      # (dict) {"url","title","loading"}
        self._view = None
        self._page = None
        self._errors: list = []
        self._lock = threading.RLock()       # une action à la fois
        self._live_until = 0.0
        self._timer = None
        self._seq = 0
        self.last_capture = ""
        self._call.connect(self._exec, Qt.QueuedConnection)

    # ------------------------------------------------------------------ marshalling vers le fil de l'interface
    @Slot(object)
    def _exec(self, fn) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print("LiveBrowser :", e)

    def _run(self, starter, timeout: float = 30.0) -> dict:
        if QThread.currentThread() is self.thread():
            raise RuntimeError("LiveBrowser ne doit pas être appelé depuis le fil de l'interface")
        holder = {"ev": threading.Event(), "res": None}

        def done(res=None) -> None:
            if not holder["ev"].is_set():
                holder["res"] = res
                holder["ev"].set()

        def go() -> None:
            try:
                starter(done)
            except Exception as e:  # noqa: BLE001
                done({"ok": False, "error": str(e)})

        self._call.emit(go)
        if not holder["ev"].wait(timeout):
            return {"ok": False, "error": "délai dépassé"}
        return holder["res"] or {"ok": False, "error": "pas de réponse"}

    def _say(self, text: str) -> None:
        if self.on_action:
            try:
                self.on_action(text)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ fil de l'interface : création paresseuse
    def _ensure(self) -> None:
        if self._view is not None:
            return
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        outer = self

        class _Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    outer._errors.append(f"{message} ({Path(source or '').name or source}:{line})"[:220])

            def createWindow(self, _type):  # noqa: N802
                return self          # pas de fenêtre en plus : un lien « nouvel onglet » s'ouvre ici

        profile = QWebEngineProfile(self)        # hors-piste : rien n'est enregistré
        profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        self._page = _Page(profile, self)
        self._view = QWebEngineView()
        self._view.setPage(self._page)
        self._view.setAttribute(Qt.WA_DontShowOnScreen, True)
        self._view.resize(VIEW_W, VIEW_H)
        self._view.show()
        s = self._page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        self._page.loadStarted.connect(lambda: self._state(True))
        self._page.loadFinished.connect(lambda _ok: self._state(False))
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_EVERY_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _state(self, loading: bool) -> None:
        if self.on_state and self._page is not None:
            try:
                self.on_state({"url": self._page.url().toString(), "title": self._page.title(), "loading": loading})
            except Exception:  # noqa: BLE001
                pass
        self.keep_live()

    # ------------------------------------------------------------------ images en direct pour le panneau
    def keep_live(self, seconds: float = FRAME_KEEP_S) -> None:
        self._live_until = max(self._live_until, time.time() + seconds)

    def _tick(self) -> None:
        if time.time() < self._live_until:
            self._push_frame()

    def _push_frame(self) -> None:
        if self._view is None or not self.on_frame:
            return
        pix = self._view.grab()
        if pix.isNull():
            return
        small = pix.scaledToWidth(FRAME_W, Qt.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        small.save(buf, "JPG", 62)
        self.on_frame({"jpg": base64.b64encode(bytes(buf.data())).decode("ascii"), "url": self._page.url().toString(),
                       "title": self._page.title(), "w": pix.width(), "h": pix.height()})

    # ------------------------------------------------------------------ actions (appelables depuis un fil de travail)
    def open(self, url: str, timeout: float = 30.0, say=None) -> dict:
        """Ouvre une page. -> {ok, url, title, ms, errors}. `say` = phrase du fil d'activité ("" = aucune)."""
        try:
            url = check_url(url)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        with self._lock:
            if say != "":
                self._say(say or f"J'ouvre {url[:90]}")

            def start(done) -> None:
                self._ensure()
                t0, st = time.time(), {"d": False}
                self._errors = []
                self.keep_live(timeout + 5)

                def fin(ok: bool) -> None:
                    if st["d"]:
                        return
                    st["d"] = True
                    try:
                        self._page.loadFinished.disconnect(fin)
                    except (RuntimeError, TypeError):
                        pass

                    def end() -> None:
                        self._push_frame()
                        done({"ok": bool(ok) or bool(self._page.title()), "url": self._page.url().toString(), "title": self._page.title(),
                              "ms": int((time.time() - t0) * 1000), "errors": len(self._errors)})
                    QTimer.singleShot(900, end)          # laisse le JavaScript de la page finir de dessiner

                self._page.loadFinished.connect(fin)
                QTimer.singleShot(int(timeout * 1000) - 1500, lambda: fin(False))
                self._page.load(QUrl(url))
            return self._run(start, timeout + 4)

    def _js(self, code: str, done, delay: int = 0) -> None:
        def go() -> None:
            self._page.runJavaScript(code, 0, lambda r: done(r))
        QTimer.singleShot(delay, go) if delay else go()

    def text(self, maxc: int = 6000) -> dict:
        """Le texte réellement affiché (JavaScript compris)."""
        with self._lock:
            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return
                self._js("(document.body && document.body.innerText || '')", lambda r: done({"ok": True, "text": str(r or "")[:maxc], "title": self._page.title(), "url": self._page.url().toString()}))
            return self._run(start, 15)

    _REPORT_JS = """(() => {
      const d = document, vw = innerWidth, q = s => [...d.querySelectorAll(s)];
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const wide = q('body *').filter(e => { const r = e.getBoundingClientRect(); return r.right > vw + 2 && r.width > 0 && getComputedStyle(e).position !== 'fixed'; }).slice(0, 5)
        .map(e => (e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\\s+/)[0] : '')));
      const small = q('a,button,input,select,textarea').filter(e => vis(e)).filter(e => { const r = e.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).length;
      return JSON.stringify({
        title: d.title, lang: d.documentElement.lang || '', viewport_meta: !!d.querySelector('meta[name=viewport]'),
        headings: q('h1,h2,h3').filter(vis).slice(0, 14).map(h => h.tagName + ' ' + h.innerText.trim().slice(0, 70)),
        links: q('a[href]').length, buttons: q('button,input[type=submit],[role=button]').length, forms: q('form').length,
        images: q('img').length, broken_images: q('img').filter(i => i.complete && i.naturalWidth === 0).slice(0, 6).map(i => i.getAttribute('src') || ''),
        no_alt: q('img').filter(i => !i.hasAttribute('alt')).length, overflow_x: d.documentElement.scrollWidth > vw + 2,
        too_wide: wide, small_targets: small, page_height: d.documentElement.scrollHeight, viewport_width: vw,
        text_chars: (d.body ? d.body.innerText.length : 0)});
    })()"""

    def report(self) -> dict:
        """Rapport sur la page ouverte : titres, images cassées, débordements, erreurs JavaScript... (rien n'est modifié)."""
        with self._lock:
            self._say("Je contrôle la page (titres, images, débordements, erreurs)")

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return

                def got(raw) -> None:
                    try:
                        rep = json.loads(raw or "{}")
                    except ValueError:
                        rep = {}
                    rep["console_errors"] = list(dict.fromkeys(self._errors))[:8]
                    done({"ok": True, "report": rep, "url": self._page.url().toString()})
                self._js(self._REPORT_JS, got)
            return self._run(start, 15)

    def capture(self, full: bool = False, selector: str = "", width: int = 0, caption: str = "", who: str = "local", announce: bool = True) -> dict:
        """Capture PNG de la page ouverte (écran visible, page entière, ou un élément). -> {ok, file, w, h, url, title}"""
        with self._lock:
            self._say("Je prends une capture" + (" de la page entière" if full else (f" de {selector}" if selector else "")))

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte : ouvre d'abord une page"})
                    return
                w = max(320, min(int(width or VIEW_W), 2400))
                self.keep_live(12)
                audit: dict = {}

                def shoot(h: int, rect=None) -> None:
                    self._view.resize(w, h)

                    def snap() -> None:
                        pix = self._view.grab()
                        if rect:
                            dpr = pix.devicePixelRatio() or 1.0
                            x, y, rw, rh = [int(v * dpr) for v in rect]
                            pix = pix.copy(QRect(max(0, x), max(0, y), max(8, rw), max(8, rh)))
                        self._view.resize(VIEW_W, VIEW_H)
                        if pix.isNull():
                            done({"ok": False, "error": "capture vide"})
                            return
                        self._seq += 1
                        name = captures_dir() / f"cap-{datetime.now():%Y%m%d-%H%M%S}-{self._seq}.png"
                        if not pix.save(str(name), "PNG"):
                            done({"ok": False, "error": "impossible d'enregistrer la capture"})
                            return
                        res = {"ok": True, "file": str(name), "w": pix.width(), "h": pix.height(), "url": self._page.url().toString(), "title": self._page.title(), "audit": audit}
                        if audit:
                            try:
                                audit_path(str(name)).write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
                            except OSError:
                                pass
                        self._finish_capture(res, caption, who, announce)
                        done(res)
                    QTimer.singleShot(450, snap)           # le temps que la page se redessine à la nouvelle taille

                def proceed() -> None:
                  if selector:
                    sel = json.dumps(selector)
                    self._view.resize(w, VIEW_H)

                    def got(raw) -> None:
                        try:
                            r = json.loads(raw or "null")
                        except ValueError:
                            r = None
                        if not r:
                            done({"ok": False, "error": f"élément introuvable : {selector}"})
                            return
                        shoot(max(VIEW_H, min(int(r["h"]) + 40, MAX_FULL_H)), (r["x"], r["y"], r["w"], r["h"]))
                    self._js("""(() => { const e = document.querySelector(%s); if (!e) return 'null'; e.scrollIntoView({block: 'start'});
                      const r = e.getBoundingClientRect(); return JSON.stringify({x: Math.max(0, r.left), y: Math.max(0, r.top), w: Math.min(r.width, innerWidth), h: Math.min(r.height, %d)}); })()""" % (sel, MAX_FULL_H), got)
                  elif full:
                    self._view.resize(w, VIEW_H)
                    self._js("Math.min(document.documentElement.scrollHeight, %d)" % MAX_FULL_H, lambda h: shoot(max(VIEW_H, int(h or VIEW_H))), 250)
                  else:
                    shoot(VIEW_H)

                def measure() -> None:
                    """Les MESURES exactes de la page (couleurs, contrastes, polices, chevauchements...) à la largeur de la capture."""
                    self._view.resize(w, VIEW_H)

                    def run_audit() -> None:
                        self._js(design.AUDIT_JS, lambda raw: (audit.update(design.parse(raw)), proceed()))
                    QTimer.singleShot(400 if w != VIEW_W else 0, run_audit)
                measure()
            return self._run(start, 30)

    def audit(self) -> dict:
        """Les mesures exactes de la page ouverte, sans capture. -> {ok, audit}"""
        with self._lock:
            self._say("Je mesure les couleurs, contrastes et polices de la page")

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return
                self._js(design.AUDIT_JS, lambda raw: done({"ok": True, "audit": design.parse(raw), "url": self._page.url().toString()}))
            return self._run(start, 20)

    def screen(self, caption: str = "Écran du PC", who: str = "local") -> dict:
        """Capture de tout l'écran du PC (écran principal)."""
        with self._lock:
            self._say("Je prends une capture de l'écran du PC")

            def start(done) -> None:
                from PySide6.QtGui import QGuiApplication
                scr = QGuiApplication.primaryScreen()
                pix = scr.grabWindow(0) if scr else None
                if pix is None or pix.isNull():
                    done({"ok": False, "error": "capture de l'écran impossible"})
                    return
                self._seq += 1
                name = captures_dir() / f"cap-{datetime.now():%Y%m%d-%H%M%S}-{self._seq}.png"
                pix.save(str(name), "PNG")
                res = {"ok": True, "file": str(name), "w": pix.width(), "h": pix.height(), "url": "écran", "title": caption}
                self._finish_capture(res, caption, who, True)
                done(res)
            return self._run(start, 20)

    def _finish_capture(self, res: dict, caption: str, who: str, announce: bool) -> None:
        self.last_capture = res["file"]
        cap = caption or res.get("title") or res.get("url") or "Capture"
        _remember({"file": res["file"], "caption": cap, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "url": res.get("url", ""), "who": who})
        self._push_frame()
        if announce and self.on_image:
            try:
                self.on_image(res["file"], cap, who)
            except Exception:  # noqa: BLE001
                pass

    _FIND_JS = """(() => { const t = %s; let el = null;
      try { if (/^[#.\\[]|^[a-z]+[#.\\[:>]/i.test(t) || /^[a-z][a-z0-9-]*$/i.test(t) && !/\\s/.test(t) && document.querySelector(t)) el = document.querySelector(t); } catch (e) {}
      if (!el) { const low = t.toLowerCase().trim();
        const all = [...document.querySelectorAll('a,button,input,select,textarea,summary,[role=button],[role=tab],[onclick],label')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
        const txt = e => ((e.innerText || e.value || e.getAttribute('aria-label') || e.title || e.placeholder || '') + '').toLowerCase().trim();
        el = all.find(e => txt(e) === low) || all.find(e => txt(e).includes(low)); }
      if (!el) return 'null';
      el.scrollIntoView({block: 'center', inline: 'center'});
      const r = el.getBoundingClientRect();
      return JSON.stringify({x: r.left + r.width / 2, y: r.top + r.height / 2, tag: el.tagName.toLowerCase(), text: ((el.innerText || el.value || '') + '').trim().slice(0, 60)}); })()"""

    def click(self, target: str) -> dict:
        """Clique sur un élément (sélecteur CSS ou texte visible). Ne remplit rien et ne valide aucun formulaire à ta place."""
        with self._lock:
            self._say(f"Je clique sur « {target[:60]} »")

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return
                self.keep_live(10)

                def got(raw) -> None:
                    try:
                        r = json.loads(raw or "null")
                    except ValueError:
                        r = None
                    if not r:
                        done({"ok": False, "error": f"rien trouvé qui corresponde à « {target} »"})
                        return
                    if self.on_click:
                        self.on_click({"x": r["x"], "y": r["y"], "w": self._view.width(), "h": self._view.height()})
                    before = self._page.url().toString()
                    self._js("""(() => { const t = %s; let el; try { el = document.querySelector(t); } catch (e) {}
                      if (!el) { const low = t.toLowerCase().trim(); const all = [...document.querySelectorAll('a,button,input,select,textarea,summary,[role=button],[role=tab],[onclick],label')];
                        const txt = e => ((e.innerText || e.value || e.getAttribute('aria-label') || e.title || e.placeholder || '') + '').toLowerCase().trim();
                        el = all.find(e => txt(e) === low) || all.find(e => txt(e).includes(low)); }
                      if (el) el.click(); return 'ok'; })()""" % json.dumps(target), lambda _r: QTimer.singleShot(
                        1300, lambda: (self._push_frame(), done({"ok": True, "clicked": r.get("text") or r.get("tag"), "url": self._page.url().toString(),
                                                                  "title": self._page.title(), "navigated": self._page.url().toString() != before}))))
                self._js(self._FIND_JS % json.dumps(target), got)
            return self._run(start, 20)

    def type_text(self, target: str, text: str) -> dict:
        """Écrit dans un champ (sélecteur CSS ou texte du champ). N'appuie pas sur Entrée et n'envoie rien."""
        with self._lock:
            self._say(f"J'écris dans « {target[:50]} »")

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return
                self.keep_live(8)

                def got(raw) -> None:
                    try:
                        r = json.loads(raw or "null")
                    except ValueError:
                        r = None
                    if not r:
                        done({"ok": False, "error": f"champ introuvable : {target}"})
                        return
                    if self.on_click:
                        self.on_click({"x": r["x"], "y": r["y"], "w": self._view.width(), "h": self._view.height()})
                    js = """(() => { const t = %s, v = %s; let el; try { el = document.querySelector(t); } catch (e) {}
                      if (!el) { const low = t.toLowerCase().trim(); el = [...document.querySelectorAll('input,textarea,select')].find(e => ((e.placeholder || e.name || e.id || e.getAttribute('aria-label') || '') + '').toLowerCase().includes(low)); }
                      if (!el) return 'non'; el.focus(); el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); return 'ok'; })()""" % (json.dumps(target), json.dumps(text))
                    self._js(js, lambda ok: QTimer.singleShot(500, lambda: (self._push_frame(), done({"ok": ok == "ok", "error": "" if ok == "ok" else "champ non modifiable"}))))
                self._js(self._FIND_JS % json.dumps(target), got)
            return self._run(start, 15)

    def scroll(self, where: str = "bas") -> dict:
        """Défile : « haut », « bas », « page » (une page vers le bas) ou « -page »."""
        with self._lock:
            self._say("Je fais défiler la page")

            def start(done) -> None:
                if self._page is None:
                    done({"ok": False, "error": "aucune page ouverte"})
                    return
                w = (where or "bas").lower()
                code = ("window.scrollTo(0,0)" if w.startswith(("haut", "top", "début")) else
                        "window.scrollTo(0,document.documentElement.scrollHeight)" if w.startswith(("bas", "bottom", "fin")) else
                        "window.scrollBy(0,-innerHeight*0.85)" if w.startswith(("-", "monter")) else "window.scrollBy(0,innerHeight*0.85)")
                self.keep_live(8)
                self._js(code + ";JSON.stringify({y:Math.round(scrollY),h:document.documentElement.scrollHeight,vh:innerHeight})",
                         lambda r: QTimer.singleShot(450, lambda: (self._push_frame(), done({"ok": True, "pos": json.loads(r or "{}")}))))
            return self._run(start, 12)

    def current(self) -> dict:
        with self._lock:
            def start(done) -> None:
                if self._page is None:
                    done({"ok": True, "url": "", "title": ""})
                else:
                    done({"ok": True, "url": self._page.url().toString(), "title": self._page.title()})
            return self._run(start, 5)

    def shutdown(self) -> None:
        """À la fermeture de Jimmy : la page cachée ne doit pas empêcher l'application de se terminer."""
        try:
            if self._timer is not None:
                self._timer.stop()
            if self._view is not None:
                self._view.close()
                self._view.deleteLater()
                self._view = None
                self._page = None
        except RuntimeError:
            pass

    def close_page(self) -> None:
        def start(done) -> None:
            if self._page is not None:
                self._page.load(QUrl("about:blank"))
            done({"ok": True})
        self._run(start, 5)
