"""Test du glisser-déposer : un fichier déposé sur la fenêtre arrive avec son vrai chemin. Lancer : python -W ignore test_drop.py"""
import os
import sys
import tempfile

from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, QTimer, QUrl, Qt, QObject, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

import webwindow

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication(sys.argv[:1])
f = os.path.join(tempfile.mkdtemp(prefix="jdrop_"), "depose-ici.txt")
open(f, "w").write("contenu")
got, calls = [], []


class B(QObject):
    event = Signal(str)

    @Slot()
    def ready(self):
        pass

    @Slot(str, str)
    def dropData(self, name, b64):
        calls.append(("dropData", name, len(b64)))


view = QWebEngineView()
page = webwindow._Page(view)
page.on_file = lambda p: got.append(p)
view.setPage(page)
ch = QWebChannel(page)
b = B()
ch.registerObject("bridge", b)
page.setWebChannel(ch)
view.resize(1280, 800)
from PySide6.QtWidgets import QWidget
events = []


class Win(QObject):
    pass


win = Win()
win.view = view
win.jsb = type("J", (), {"emit": staticmethod(lambda ev: events.append(ev))})()
win.attach_paths = lambda paths: got.extend(paths)
flt = webwindow._DropFilter(win)
view.setAcceptDrops(True)


def hook(_ok=True):
    for w in [view, view.focusProxy(), *view.findChildren(QWidget)]:
        if w is not None:
            w.setAcceptDrops(True)
            w.installEventFilter(flt)


view.loadFinished.connect(lambda ok: (hook(), QTimer.singleShot(1500, hook)))
view.setUrl(QUrl.fromLocalFile(os.path.join(webwindow.web_dir(), "index.html")))
view.show()


def drop():
    proxy = view.focusProxy() or view
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(f)])
    pos = QPoint(600, 400)
    app.sendEvent(proxy, QDragEnterEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    app.sendEvent(proxy, QDragMoveEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    page.runJavaScript("document.querySelector('#dropHint').hidden")
    QTimer.singleShot(400, lambda: print("voile demandé pendant le survol :", [e for e in events if e["t"] == "dragging"]))
    QTimer.singleShot(700, lambda: app.sendEvent(proxy, QDropEvent(QPointF(pos), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)))
    QTimer.singleShot(3500, finish)


def finish():
    print("chemin réel reçu au dépôt :", got)
    print("événements envoyés à la page :", events)
    ok = bool(got) and got[0].endswith("depose-ici.txt")
    print("RESULTAT :", "DEPOT OK (chemin réel récupéré, voile affiché puis retiré)" if ok and [e["on"] for e in events] == [True, False] else "A REVOIR")
    app.quit()


QTimer.singleShot(3000, drop)
app.exec()
