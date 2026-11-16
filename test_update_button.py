"""Test du bouton « Vérifier les mises à jour » (sans rien installer, ni rien télécharger). Lancer : python test_update_button.py"""
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

import updater
import webwindow as WW

app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


def run(upd, can_self=True, download_raises=None):
    events, calls = [], {"installer": None, "quit": 0}
    class Me:
        pass
    me = Me()
    me._updating, me._usig = False, WW._UpdSig()
    me.jsb = SimpleNamespace(emit=lambda ev: events.append(ev))
    me.cfg = SimpleNamespace(get=lambda k, d=None: {"update_repo": "x/y"}.get(k, d))
    me.check_update_now = types.MethodType(WW.WebJimmyWindow.check_update_now, me)
    me._on_update_state = types.MethodType(WW.WebJimmyWindow._on_update_state, me)
    me._run_installer = types.MethodType(WW.WebJimmyWindow._run_installer, me)
    me._usig.state.connect(me._on_update_state)
    me._usig.install.connect(me._run_installer)

    updater.check = lambda repo: upd
    updater.can_self_update = lambda: can_self

    def fake_download(u, progress=None):
        if download_raises:
            raise download_raises
        for d in (10, 50, 100):
            progress(d, 100)
        return Path("C:/tmp/Jimmy-Setup-9.9.9.exe")
    updater.download = fake_download
    updater.run_installer = lambda p: calls.__setitem__("installer", str(p))
    WW.QApplication.quit = staticmethod(lambda: calls.__setitem__("quit", calls["quit"] + 1))

    me.check_update_now()
    me.check_update_now()                       # un 2e clic pendant la recherche ne doit rien relancer
    t0 = time.time()
    while time.time() - t0 < 6:
        app.processEvents()
        time.sleep(0.02)
        if any(e["state"] in ("none", "manual", "error") for e in events) or calls["installer"]:
            for _ in range(10):
                app.processEvents()
            break
    return [e["state"] for e in events], events, calls


# 1) déjà à jour
states, ev, calls = run(None)
check("à jour : « checking » puis « none », rien d'installé", states == ["checking", "none"] and calls["installer"] is None)
check("à jour : message avec la version", "à jour" in ev[-1]["text"])

# 2) version trouvée mais Jimmy lancé depuis le code (pas installé) : on explique, on n'installe pas
states, ev, calls = run(SimpleNamespace(version="9.9.9", url="u", notes="n", size=1), can_self=False)
check("version trouvée hors installation : message « manual », rien d'installé", states[-1] == "manual" and calls["installer"] is None)

# 3) version trouvée, installée : téléchargement avec progression, puis installation + fermeture de Jimmy
states, ev, calls = run(SimpleNamespace(version="9.9.9", url="u", notes="n", size=1), can_self=True)
check("mise à jour : recherche -> téléchargement -> installation", states[0] == "checking" and "downloading" in states and states[-1] == "installing")
check("la progression remonte (10 %, 50 %, 100 %)", [e["pct"] for e in ev if e["state"] == "downloading"][-3:] == [10, 50, 100])
check("l'installateur téléchargé est lancé", calls["installer"] and calls["installer"].endswith("Jimmy-Setup-9.9.9.exe"))
check("Jimmy se ferme pour laisser l'installateur travailler", calls["quit"] == 1)
check("un seul lancement malgré le double clic", states.count("checking") == 1)

# 4) panne de téléchargement : message clair, le bouton redevient utilisable, rien n'est lancé
states, ev, calls = run(SimpleNamespace(version="9.9.9", url="u", notes="n", size=1), can_self=True, download_raises=OSError("réseau coupé"))
check("panne : message d'erreur clair", states[-1] == "error" and "réseau coupé" in ev[-1]["text"] and calls["installer"] is None)

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
