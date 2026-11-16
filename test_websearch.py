"""Test RÉEL de la recherche Internet de l'IA locale (demande une connexion). Lancer : python test_websearch.py"""
import sys
import threading
import time

from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtWidgets import QApplication

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication(sys.argv[:1])

from brain import tools as T
from brain import web
from brain.browser_search import HeadlessSearch

fails = []
out = {}


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


hs = HeadlessSearch()
web.browser_search = hs.search


class Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def worker():
    reg = T.base_registry()
    ctx = T.Context(cfg=Cfg(workdir="."), user_text="cherche sur internet la hauteur de la tour Eiffel")
    t0 = time.time()
    out["tour"] = reg.call("chercher_web", {"requete": "hauteur de la tour Eiffel"}, ctx)
    out["t1"] = time.time() - t0
    out["journal"] = list(ctx.journal)
    ctx2 = T.Context(cfg=Cfg(workdir="."), user_text="cherche la dernière version de Python")
    out["python"] = reg.call("chercher_web", {"requete": "dernière version stable de Python python.org"}, ctx2)
    out["done"] = True


threading.Thread(target=worker, daemon=True).start()
t0 = time.time()
while not out.get("done") and time.time() - t0 < 120:
    app.processEvents()
    time.sleep(0.02)

tour = out.get("tour", "")
check("la recherche répond", bool(tour) and "a échoué" not in tour)
check("source indiquée (navigateur de Jimmy)", "Navigateur de Jimmy" in tour or "Bing" in tour or "DuckDuckGo" in tour)
check("résultat PERTINENT : la hauteur 330 m / 300 m apparaît", "330" in tour or "300 m" in tour)
check("des extraits de texte sont donnés", tour.count("\n  ") >= 2)
check("durée raisonnable (< 40 s)", out.get("t1", 99) < 40)
check("le journal des étapes se remplit (pour Claude)", bool(out.get("journal")) and "chercher_web" in out["journal"][0])
py = out.get("python", "")
check("2e recherche : Python, un numéro de version 3.x apparaît", "3.1" in py or "3.2" in py or "3.0" in py)
print("   extrait :", tour[:300].replace("\n", " "))
print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
