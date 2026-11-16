"""Test de la sauvegarde par discussion : captures, messages d'Aurélie, dialogues, passages de main, activité, travail de Jimmy, dernier rendu."""
import base64
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jpers_"))
import config

config.data_dir = lambda: work
import extras
import sessions

fails = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "ECHEC"), name, "" if cond else detail)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- le magasin
extras.add(None, "image", file="a.png", caption="avant l'id", who="local")
extras.add(None, "feed", text="J'ouvre la page", who="local")
check("rien n'est écrit tant que la discussion n'a pas d'identifiant", not list((work / "extras").glob("*.jsonl")))
extras.save_frame(None, jpg=base64.b64encode(b"\xff\xd8fake").decode(), url="https://x.fr", title="Accueil", w=1280, h=800)
extras.bind("sess-1")
items = extras.load("sess-1")
check("à l'identifiant, ce qui attendait est rangé dans la discussion", [i["kind"] for i in items] == ["image", "feed"])
check("le dernier rendu qui attendait est rangé aussi", (extras.load_frame("sess-1") or {}).get("title") == "Accueil")
time.sleep(0.01)
extras.add("sess-1", "work", phase="start", id="t1", tool="Edit", label="Modification · je modifie index.html", target="C:/site/index.html", detail="- a\n+ b")
extras.add("sess-1", "work", phase="end", id="t1", ok=True, out="ok")
extras.add("sess-1", "dialog", frm="local", to="jimmy", text="Jimmy, voilà")
check("ordre chronologique conservé", [i["kind"] for i in extras.load("sess-1")] == ["image", "feed", "work", "work", "dialog"])
check("filtre par type", [i["kind"] for i in extras.load("sess-1", kinds=("dialog",))] == ["dialog"])
check("le détail d'une modification est gardé", extras.load("sess-1", kinds=("work",))[0]["detail"] == "- a\n+ b")
check("identifiant piégé refusé (pas d'écriture hors du dossier)", extras.add("../evil", "feed", text="x") and not (work / "evil.jsonl").exists())
# reprise de contexte : l'historique de l'ancienne suit la nouvelle
extras.bind("sess-2", "sess-1")
check("reprise de contexte : l'historique suit la nouvelle discussion", len(extras.load("sess-2")) == 5)
check("reprise de contexte : le dernier rendu suit aussi", (extras.load_frame("sess-2") or {}).get("url") == "https://x.fr")
extras.forget("sess-1")
check("suppression d'une discussion : ses éléments partent avec elle", extras.load("sess-1") == [] and extras.load_frame("sess-1") is None)
extras.add(None, "feed", text="en attente", who="local")
extras.drop_pending()
extras.bind("sess-3")
check("changer de discussion jette ce qui attendait (pas de mélange)", extras.load("sess-3") == [])

# ---------------------------------------------------------------- chronologie des messages
folder = sessions.project_dir(str(work))
folder.mkdir(parents=True, exist_ok=True)
t0 = time.time() - 100


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


rows = [{"type": "user", "sessionId": "sess-2", "timestamp": iso(t0), "message": {"role": "user", "content": "Ouvre le site et montre-moi"}},
        {"type": "assistant", "sessionId": "sess-2", "timestamp": iso(t0 + 30), "message": {"role": "assistant", "content": [{"type": "text", "text": "Voilà, c'est fait."}]}}]
(folder / "sess-2.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
tl = sessions.load_timeline(str(work), "sess-2")
check("chronologie : messages avec leur heure", len(tl) == 2 and tl[0][1] == "user" and abs(tl[0][0] - int(t0)) < 2 and tl[1][0] > tl[0][0])


# ---------------------------------------------------------------- discussion menée seulement avec Aurélie
lid = extras.new_local_id()
check("discussion avec Aurélie : identifiant reconnaissable", extras.is_local(lid) and not extras.is_local("5e23715d-1379"))
extras.bind(lid)
extras.add(lid, "user", text="Aurélie, que sais-tu faire de concret ?")
time.sleep(0.01)
extras.add(lid, "local", text="Je peux ouvrir un site, le mesurer et te montrer le rendu.")
ls = extras.local_sessions()
check("discussion avec Aurélie : titre tiré de la première question", ls and ls[0][0] == lid and ls[0][1].startswith("Aurélie, que sais-tu"))
listed = sessions.list_sessions(str(work))
check("discussion avec Aurélie : elle apparaît dans la liste des discussions", any(s[0] == lid and s[1].startswith("Aurélie, que sais-tu") for s in listed))
sessions.set_name(lid, "Mon test avec Aurélie", manual=True)
check("discussion avec Aurélie : renommable comme les autres", any(s[0] == lid and s[1] == "Mon test avec Aurélie" for s in sessions.list_sessions(str(work))))
extras.bind("claude-sess-9", lid)
check("quand Claude intervient : la discussion avec Aurélie devient celle de Claude, sans rien perdre",
      [i["kind"] for i in extras.load("claude-sess-9")] == ["user", "local"])
check("quand Claude intervient : plus de doublon dans la liste", not any(s[0] == lid for s in sessions.list_sessions(str(work))) and extras.load(lid) == [])
lid2 = extras.new_local_id()
extras.bind(lid2)
extras.add(lid2, "user", text="Question pour rien")
sessions.delete_session(str(work), lid2)
check("supprimer une discussion avec Aurélie : elle disparaît", extras.load(lid2) == [] and not any(s[0] == lid2 for s in sessions.list_sessions(str(work))))

# ---------------------------------------------------------------- rejeu dans la fenêtre : tout revient, à sa place
import window as W

extras.add("sess-2", "local", text="Réponse d'Aurélie entre les deux")
# on place les éléments à des heures précises pour vérifier l'entrelacement
p = work / "extras" / "sess-2.jsonl"
lines = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
for it in lines:
    if it["kind"] == "local":
        it["ts"] = t0 + 10
    elif it["kind"] == "image":
        it["ts"] = t0 + 20
    elif it["kind"] == "dialog":
        it["ts"] = t0 + 40
    else:
        it["ts"] = t0 + 5
p.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in lines), encoding="utf-8")
log = []
me = SimpleNamespace(bridge=SimpleNamespace(workdir=lambda: str(work), session_id="sess-2"), _replaying=False, notices=[],
                     add_system=lambda t: log.append(("system", t)),
                     add_message=lambda role, text: log.append((role, text)),
                     add_dialog=lambda f, t, x: log.append(("dialog", x)),
                     _replay_xfer=lambda it: log.append(("xfer", it.get("why"))),
                     _replay_image=lambda it: log.append(("image", it.get("caption"))),
                     _replay_feed=lambda sid: log.append(("feed", sid)))
me._replay_item = lambda it: W.JimmyWindow._replay_item(me, it)
W.JimmyWindow._render_session(me, "sess-2", 60)
kinds = [k for k, _ in log]
check("rejeu : messages, captures, réponses d'Aurélie et dialogues dans l'ordre du temps", kinds[:5] == ["user", "local", "image", "assistant", "dialog"])
check("rejeu : le fil d'activité et le dernier rendu sont rechargés", ("feed", "sess-2") in log)
check("rejeu : rien n'est resauvegardé pendant le rejeu", me._replaying is False and len(extras.load("sess-2")) == len(lines))


# ---------------------------------------------------------------- réglages d'apparence : enregistrés dans la configuration de Jimmy
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv[:1])
import webwindow

store = {}
cfg_fake = SimpleNamespace(set=lambda k, v: store.__setitem__(k, v), get=lambda k, d=None: store.get(k, d))
b = SimpleNamespace(win=SimpleNamespace(cfg=cfg_fake))
webwindow.Bridge.setUi(b, "round", "pill")
webwindow.Bridge.setUi(b, "amb", "halo")
webwindow.Bridge.setUi(b, "look", "sobre")
webwindow.Bridge.setUi(b, "mode", "light")
webwindow.Bridge.setUi(b, "tint", "65")
webwindow.Bridge.setUi(b, "live_w", "612")
check("apparence : arrondis, ambiance, style, mode, teinte et largeur du panneau enregistrés dans la configuration",
      store.get("ui_round") == "pill" and store.get("ui_amb") == "halo" and store.get("ui_look") == "sobre" and store.get("ui_mode") == "light"
      and store.get("ui_tint") == 65 and store.get("ui_live_w") == 612 and store.get("ui_saved") is True)
webwindow.Bridge.setUi(b, "round", "<script>")
webwindow.Bridge.setUi(b, "tint", "9999")
webwindow.Bridge.setUi(b, "live_w", "50")
webwindow.Bridge.setUi(b, "inconnu", "x")
check("apparence : valeurs invalides refusées ou bornées", store.get("ui_round") == "pill" and store.get("ui_tint") == 100 and store.get("ui_live_w") == 320 and "ui_inconnu" not in store)


# ---------------------------------------------------------------- régression : ce qui s'est passé avec Aurélie AVANT le premier message de Claude revient aussi
with open(work / "extras" / "sess-2.jsonl", "a", encoding="utf-8") as f:
    f.write(chr(10))
    f.write(json.dumps({"ts": t0 - 50, "kind": "user", "text": "Question posée à Aurélie avant que Claude intervienne"}, ensure_ascii=False) + "\n")
    f.write(json.dumps({"ts": t0 - 40, "kind": "local", "text": "Réponse d'Aurélie avant Claude"}, ensure_ascii=False) + "\n")
log.clear()
W.JimmyWindow._render_session(me, "sess-2", 60)
texts = [x for _k, x in log]
check("rejeu : la conversation avec Aurélie d'AVANT le premier message de Claude revient, en premier",
      texts[:2] == ["Question posée à Aurélie avant que Claude intervienne", "Réponse d'Aurélie avant Claude"], str(log[:4]) + " extras=" + str([(i["kind"], i.get("text", "")[:20]) for i in extras.load("sess-2")][:5]))
log.clear()
W.JimmyWindow._render_session(me, "sess-2", 1)
check("rejeu : discussion trop longue -> on n'affiche que la fenêtre demandée (le plus ancien est écarté)",
      "Question posée à Aurélie avant que Claude intervienne" not in [x for _k, x in log])

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
