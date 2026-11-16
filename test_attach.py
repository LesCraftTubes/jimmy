"""Test des pièces jointes (copie, message, mémoire, retrait, dépôt sur la page). Lancer : python test_attach.py"""
import base64
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jattach_"))
os.environ["JIMMY_MEM_DIR"] = str(work / "mem")      # la vraie mémoire de Jimmy n'est pas touchée

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

import webwindow as WW

WW.data_dir = lambda: work / "data"                  # et la vraie zone de données non plus
app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


events = []
me = SimpleNamespace(jsb=SimpleNamespace(emit=lambda ev: events.append(ev)), _attach=[], _asig=WW._AttachSig())
for n in ("_size_text", "_unique", "_attach_dir", "attach_paths", "_attached", "_emit_attached", "drop_data", "detach_file",
          "compose_attachments"):
    f = WW.WebJimmyWindow.__dict__[n]
    setattr(me, n, f.__func__ if isinstance(f, staticmethod) else types.MethodType(f, me))
me._asig.done.connect(me._attached)

# --- sources : un petit fichier, un GROS fichier (120 Mo), un dossier
src = work / "src"
src.mkdir()
(src / "notes.txt").write_text("bonjour", encoding="utf-8")
with open(src / "gros.bin", "wb") as f:
    f.truncate(120 * 1024 * 1024)
(src / "dossier").mkdir()
(src / "dossier" / "a.py").write_text("print(1)", encoding="utf-8")

me.attach_paths([str(src / "notes.txt"), str(src / "gros.bin"), str(src / "dossier")])
t0 = time.time()
while len(me._attach) < 3 and time.time() - t0 < 60:
    app.processEvents()
    time.sleep(0.05)
check("3 éléments joints (fichier, gros fichier 120 Mo, dossier)", len(me._attach) == 3)
check("le gros fichier est copié en entier", any(i["name"] == "gros.bin" and i["size"] == 120 * 1024 * 1024 for i in me._attach))
check("les copies sont dans le dossier des pièces jointes", all(str(work / "data" / "pieces_jointes") in i["path"] and Path(i["path"]).exists() for i in me._attach))
check("le dossier est copié avec son contenu", any(i["name"] == "dossier" and (Path(i["path"]) / "a.py").exists() for i in me._attach))
check("les originaux ne sont pas touchés", (src / "notes.txt").exists() and (src / "gros.bin").exists())
check("la page est prévenue (puces)", any(e["t"] == "attached" and len(e["items"]) == 3 for e in events))

# --- deux fichiers de même nom : aucun écrasé
me.attach_paths([str(src / "notes.txt")])
t0 = time.time()
while len(me._attach) < 4 and time.time() - t0 < 10:
    app.processEvents()
    time.sleep(0.05)
names = [Path(i["path"]).name for i in me._attach]
check("même nom : renommé, jamais écrasé", len(set(names)) == 4 and "notes (2).txt" in names)

# --- retrait d'une puce
victim = [i for i in me._attach if i["name"] == "notes (2).txt"][0]["path"]
me.detach_file(victim)
check("retrait d'une puce (la copie reste sur le disque)", len(me._attach) == 3 and Path(victim).exists())

# --- envoi : le chemin est dans le message + note en mémoire
paths_before = [i["path"] for i in me._attach]
msg = me.compose_attachments("lis ces fichiers")
check("le message contient le chemin réel de chaque fichier", all(p in msg for p in paths_before))
check("le message contient la demande et la liste", msg.startswith("lis ces fichiers") and "notes.txt" in msg and "gros.bin" in msg)
check("après envoi, plus rien en attente", me._attach == [] and [e for e in events if e["t"] == "attached"][-1]["items"] == [])
import jimmy_mem
rows = jimmy_mem.search("pièces jointes", 5)
check("note en mémoire pour retrouver les fichiers plus tard", bool(rows) and "notes.txt" in rows[0]["contenu"])
check("rien en attente : le message part tel quel", me.compose_attachments("bonjour") == "bonjour")

# --- repli : fichier reçu en base64
me.drop_data("repli.txt", base64.b64encode("salut".encode()).decode())
check("repli base64 : fichier joint", len(me._attach) == 1 and Path(me._attach[0]["path"]).read_text() == "salut")
msg2 = me.compose_attachments("")
check("sans texte : message par défaut", msg2.startswith("Regarde les fichiers joints."))

# --- dépôt sur la page : la navigation vers un fichier est interceptée (la page ne s'ouvre pas dessus)
got = []
page = WW._Page()
page.on_file = lambda p: got.append(p)
drop_file = work / "depose.txt"
drop_file.write_text("x")
ok_nav = page.acceptNavigationRequest(QUrl.fromLocalFile(str(drop_file)), None, True)
check("fichier déposé : intercepté, page non quittée", ok_nav is False and got == [os.path.abspath(str(drop_file))])
own = QUrl.fromLocalFile(os.path.join(WW.web_dir(), "index.html"))
check("la page de Jimmy elle-même se charge normalement", page.acceptNavigationRequest(own, None, True) is True)
check("un lien web s'ouvre dans le navigateur, pas dans Jimmy", page.acceptNavigationRequest(QUrl("https://example.com"), None, True) is False)

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
