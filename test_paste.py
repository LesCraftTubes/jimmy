"""Test : bouton Parler allumé pendant que Jimmy travaille, et Ctrl+V d'une capture d'écran / de fichiers. Lancer : python -W ignore test_paste.py"""
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jpaste_"))
os.environ["JIMMY_MEM_DIR"] = str(work / "mem")

from PySide6.QtCore import QCoreApplication, QMimeData, QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

import webwindow as WW

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
WW.data_dir = lambda: work / "data"
app = QApplication(sys.argv[:1])
fails, calls = [], []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


# ------------------------------------------------------------ côté Python : le presse-papiers (faux, le vrai n'est pas touché)
events = []
me = SimpleNamespace(jsb=SimpleNamespace(emit=lambda ev: events.append(ev)), _attach=[], _asig=WW._AttachSig())
for n in ("_size_text", "_unique", "_attach_dir", "attach_paths", "_attached", "_emit_attached", "paste_clipboard"):
    f = WW.WebJimmyWindow.__dict__[n]
    setattr(me, n, f.__func__ if isinstance(f, staticmethod) else types.MethodType(f, me))
me._asig.done.connect(me._attached)


class FakeClip:
    def __init__(self, md, img=None):
        self.md, self.img = md, img

    def mimeData(self):
        return self.md

    def image(self):
        return self.img or QImage()


def with_clip(clip):
    QGuiApplication.clipboard = staticmethod(lambda: clip)


img = QImage(320, 200, QImage.Format_ARGB32)
img.fill(QColor("#22d3ee"))
md = QMimeData()
md.setImageData(img)
with_clip(FakeClip(md, img))
me.paste_clipboard()
check("capture d'écran collée : devient une pièce jointe PNG", len(me._attach) == 1 and me._attach[0]["name"].startswith("capture-")
      and me._attach[0]["name"].endswith(".png") and Path(me._attach[0]["path"]).stat().st_size > 100)
check("l'image enregistrée est lisible et de la bonne taille", QImage(me._attach[0]["path"]).size().width() == 320)

src = work / "doc.txt"
src.write_text("x")
md2 = QMimeData()
md2.setUrls([QUrl.fromLocalFile(str(src))])
with_clip(FakeClip(md2))
me.paste_clipboard()
t0 = time.time()
while len(me._attach) < 2 and time.time() - t0 < 10:
    app.processEvents()
    time.sleep(0.05)
check("fichier copié dans l'Explorateur : joint avec son vrai contenu", len(me._attach) == 2 and Path(me._attach[1]["path"]).read_text() == "x")

with_clip(FakeClip(QMimeData()))
me.paste_clipboard()
check("presse-papiers vide : message clair, rien d'ajouté", len(me._attach) == 2 and events[-1]["t"] == "toast")

# ------------------------------------------------------------ côté page : bouton Parler + détection du collage
class B(QObject):
    event = Signal(str)

    @Slot()
    def ready(self):
        pass

    @Slot()
    def pasteFiles(self):
        calls.append("pasteFiles")


view = QWebEngineView()
page = WW._Page(view)
view.setPage(page)
ch = QWebChannel(page)
b = B()
ch.registerObject("bridge", b)
page.setWebChannel(ch)
view.resize(1100, 700)
view.setUrl(QUrl.fromLocalFile(os.path.join(WW.web_dir(), "index.html")))
view.show()
out = {}

JS = r"""
(function(){
  const r = {};
  onEvent({t:"state", state:"thinking"});                        /* Jimmy travaille */
  r.avant = document.querySelector("#btnTalk").classList.contains("active") || document.querySelector("#btnTalk").classList.contains("warn");
  onEvent({t:"talk", active:true}); onEvent({t:"level", rms:0.05});   /* tu appuies sur Parler : le micro écoute et du son arrive */
  r.pendant = document.querySelector("#btnTalk").classList.contains("active");
  r.texte = document.querySelector("#talkText").textContent;
  onEvent({t:"talk", active:false});
  r.apres = document.querySelector("#btnTalk").classList.contains("active");
  const dt = new DataTransfer(); dt.items.add(new File(["x"], "capture.png", {type: "image/png"}));
  document.querySelector("#input").dispatchEvent(new ClipboardEvent("paste", {clipboardData: dt, bubbles: true, cancelable: true}));
  const t2 = new DataTransfer(); t2.setData("text/plain", "du texte");
  const ev = new ClipboardEvent("paste", {clipboardData: t2, bubbles: true, cancelable: true});
  document.querySelector("#input").dispatchEvent(ev);
  r.texteNonBloque = !ev.defaultPrevented;
  return JSON.stringify(r);
})()
"""


def probe():
    def got(raw):
        out.update(json.loads(raw))
        QTimer.singleShot(300, finish)
    page.runJavaScript(JS, got)


def finish():
    check("pendant le travail : le bouton Parler n'est pas allumé avant l'appui", out["avant"] is False)
    check("pendant le travail : le bouton Parler S'ALLUME quand tu appuies", out["pendant"] is True)
    check("pendant le travail : il affiche « J'écoute… »", "écoute" in out["texte"])
    check("quand tu valides, il s'éteint", out["apres"] is False)
    check("Ctrl+V d'une image : la page demande à Jimmy de la joindre", calls == ["pasteFiles"])
    check("Ctrl+V de texte : collage normal, non bloqué", out["texteNonBloque"] is True)
    print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
    app.exit(1 if fails else 0)


QTimer.singleShot(3500, probe)
sys.exit(app.exec())
