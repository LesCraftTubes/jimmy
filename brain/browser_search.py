"""Recherche Internet par le navigateur intégré de Jimmy (Chromium), INVISIBLE : aucune fenêtre, aucun onglet dans ton navigateur.

Les moteurs servent de mauvais résultats (ou bloquent) aux programmes simples ; un vrai moteur de navigation est reconnu comme
un visiteur normal. La page est chargée dans un profil « hors-piste » : ni cookies ni historique ne sont gardés.

`search()` peut être appelée depuis n'importe quel fil : le travail se fait dans le fil de l'interface, l'appelant attend.
"""
from __future__ import annotations

import json
import threading

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal, Slot

from . import web

_BING_JS = """JSON.stringify([...document.querySelectorAll('li.b_algo')].slice(0,8).map(li => {
  const a = li.querySelector('h2 a'); const p = li.querySelector('.b_caption p, p');
  return [a ? a.innerText : '', a ? a.href : '', p ? p.innerText : ''];}))"""
_DDG_JS = """JSON.stringify([...document.querySelectorAll('article[data-testid=result], li[data-layout=organic]')].slice(0,8).map(li => {
  const a = li.querySelector('h2 a'); const p = li.querySelector('[data-result=snippet], div[data-testid=result-snippet], span');
  return [a ? a.innerText : '', a ? a.href : '', p ? p.innerText : ''];}))"""
SITES = (("Bing", "https://www.bing.com/search?setlang=fr&q=", _BING_JS),
         ("DuckDuckGo", "https://duckduckgo.com/?ia=web&q=", _DDG_JS))


class HeadlessSearch(QObject):
    _go = Signal(object)

    def __init__(self):
        super().__init__()
        self._profile = None
        self._lock = threading.Lock()          # une recherche à la fois
        self._go.connect(self._start, Qt.QueuedConnection)

    # ------------------------------------------------------------------ appelé depuis n'importe quel fil
    def search(self, query: str, n: int = 5, timeout: float = 40.0) -> list:
        with self._lock:
            req = {"q": query, "n": n, "ev": threading.Event(), "rows": [], "source": ""}
            self._go.emit(req)
            req["ev"].wait(timeout)
            req["abandoned"] = True
            if req["rows"]:
                web.last_source = req["source"] + " (navigateur de Jimmy)"
            return req["rows"]

    # ------------------------------------------------------------------ dans le fil de l'interface
    @Slot(object)
    def _start(self, req: dict) -> None:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        if self._profile is None:
            self._profile = QWebEngineProfile(self)      # hors-piste : rien n'est enregistré
        self._try_site(req, 0)

    def _finish(self, req: dict) -> None:
        req["ev"].set()

    def _try_site(self, req: dict, i: int) -> None:
        if i >= len(SITES) or req.get("abandoned"):
            self._finish(req)
            return
        from PySide6.QtWebEngineCore import QWebEnginePage
        name, base, js = SITES[i]
        page = QWebEnginePage(self._profile, self)
        state = {"tries": 0, "done": False}

        def next_site() -> None:
            if state["done"]:
                return
            state["done"] = True
            page.deleteLater()
            self._try_site(req, i + 1)

        def poll() -> None:
            if state["done"] or req.get("abandoned"):
                return
            state["tries"] += 1

            def got(raw) -> None:
                if state["done"]:
                    return
                try:
                    rows = json.loads(raw or "[]")
                except ValueError:
                    rows = []
                out = []
                for title, href, snippet in rows:
                    url = web._unwrap_bing(href) if name == "Bing" else href
                    if title and url.startswith("http"):
                        out.append((title.strip(), url, " ".join((snippet or "").split())))
                if out:
                    state["done"] = True
                    req["rows"], req["source"] = out[:req["n"]], name
                    page.deleteLater()
                    self._finish(req)
                elif state["tries"] >= 8:
                    next_site()
                else:
                    QTimer.singleShot(800, poll)
            page.runJavaScript(js, got)

        def loaded(ok: bool) -> None:
            if not ok:
                next_site()
                return
            QTimer.singleShot(900, poll)

        page.loadFinished.connect(loaded)
        page.load(QUrl(base + QUrl.toPercentEncoding(req["q"]).data().decode("ascii")))
