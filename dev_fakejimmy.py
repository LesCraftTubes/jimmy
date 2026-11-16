"""FAUX JIMMY : la vraie fenêtre de Jimmy (vraie page, vraie machinerie), pilotée par un script, avec des données isolées (dossier temporaire).

Sert à vérifier de bout en bout, comme un utilisateur : messages envoyés à Aurélie et ses réponses, ce que fait Jimmy (vraie tâche de Claude, en
Haiku pour consommer très peu), l'activité en direct, les rendus dans la conversation, la sauvegarde et la réouverture d'une discussion.
Demande : LM Studio lancé (modèle d'Aurélie) et `claude` connecté. À lancer à la main (ce n'est pas un test automatique : il utilise de vrais modèles).

    .venv\\Scripts\\python.exe dev_fakejimmy.py [dossier_des_captures_d_écran]
"""
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

work = Path(tempfile.mkdtemp(prefix="jfake_"))
site = work / "site"
site.mkdir()
import config

config.data_dir = lambda: work

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv[:1])
import listener

listener.Listener.start = lambda self: None          # pas de micro
import extras
import sessions
import webwindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else work
LOG: list = []
_orig_emit = webwindow.Bridge.emit


def _rec(self, ev):
    LOG.append(ev)
    return _orig_emit(self, ev)


webwindow.Bridge.emit = _rec

(site / "index.html").write_text("""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Boutique La Forge</title></head>
<body style="margin:0;font-family:Arial;background:#f1f1f1">
<header style="background:#14213d;color:#fff;padding:20px;font-size:26px">LA FORGE · Armes et armures</header>
<p style="color:#bdbdbd;font-size:20px;padding:0 20px">Découvrez nos soldes de fin de saison sur toutes les épées.</p>
<button style="background:#fca311;color:#fff;border:0;padding:12px 22px;font-size:18px;margin:20px">Acheter</button>
</body></html>""", encoding="utf-8")

cfg = config.Config.load()
for k, v in dict(workdir=str(site), local_enabled=True, route="auto", model="haiku", effort="low", voice_enabled=False, wake_words_enabled=False,
                 remote_enabled=False, psy_enabled=False, ctx_auto=False, show_steps=True, follow_check=True, follow_live=True, follow_snap=True).items():
    cfg.set(k, v)


class Poster(QObject):
    """Exécute une fonction dans le fil de l'interface (comme un clic)."""
    @Slot(object)
    def run(self, fn):
        fn()


from PySide6.QtCore import Signal


class _Sig(QObject):
    call = Signal(object)


poster, sig = Poster(), _Sig()
sig.call.connect(poster.run, Qt.QueuedConnection)
win = webwindow.WebJimmyWindow(cfg)
win.resize(1500, 920)
win.show()
RESULT = []


def gui(fn):
    sig.call.emit(fn)


def gui_wait(fn, timeout=20):
    ev, box = threading.Event(), {}

    def go():
        try:
            box["v"] = fn()
        finally:
            ev.set()
    gui(go)
    ev.wait(timeout)
    return box.get("v")


def wait(cond, timeout, step=0.4):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(step)
    return False


def check(name, ok, detail=""):
    RESULT.append((name, bool(ok)))
    print(("OK    " if ok else "ECHEC ") + name + (f"   [{detail}]" if detail and not ok else ""))


def shot(name):
    time.sleep(1.8)                                   # l'interface a fini de s'animer
    gui_wait(lambda: win.view.grab().save(str(OUT / name)))


def since(mark, **match):
    return [e for e in LOG[mark:] if all(e.get(k) == v for k, v in match.items())]


def local_replies(mark):
    return [e for e in LOG[mark:] if e.get("t") == "msg" and e.get("role") == "assistant" and "IA LOCALE" in str(e.get("label", ""))]


def show(title, text):
    print(f"\n----- {title} -----\n{str(text).strip()[:1400]}\n")


def scenario():
    try:
        check("la page est chargée", wait(lambda: any(e.get("t") == "prefs" for e in LOG), 40))
        # on laisse la barre du haut se charger complètement (état, abonnement, liste des discussions) avant d'agir, comme un vrai utilisateur
        wait(lambda: any(e.get("t") == "usage" for e in LOG), 25)
        wait(lambda: any(e.get("t") == "sessions" for e in LOG), 10)
        wait(lambda: any(e.get("t") == "state" and e.get("state") != "loading" for e in LOG), 30)
        time.sleep(5)
        ok = gui_wait(lambda: win._ensure_local_agent() == "")
        check("le moteur d'Aurélie répond (LM Studio)", ok)

        # ---------------------------------------------------- 1. une vraie conversation avec Aurélie
        m = len(LOG)
        gui(lambda: win.submit("@local Aurélie, présente-toi en deux phrases : qu'est-ce que tu sais faire de concret pour m'aider ?"))
        check("Aurélie répond dans la conversation", wait(lambda: local_replies(m), 120))
        r1 = local_replies(m)[0]["text"] if local_replies(m) else ""
        show("Aurélie (présentation)", r1)
        check("sa réponse ne parle pas d'elle à la 3e personne et ne se fait pas passer pour Jimmy", r1 and "[Jimmy" not in r1 and "Aurélie a " not in r1 and "l'IA locale a " not in r1)
        sid1 = gui_wait(lambda: win._current_sid())
        check("la discussion avec Aurélie a SON identifiant (elle existe, comme une vraie discussion)", extras.is_local(sid1), str(sid1))
        kinds = [i["kind"] for i in extras.load(sid1)]
        check("ta question ET sa réponse sont sauvegardées", "user" in kinds and "local" in kinds, str(kinds))
        listed = sessions.list_sessions(str(site))
        check("la discussion apparaît dans la liste, titrée par ta question", any(s[0] == sid1 and "présente-toi" in s[1] for s in listed), str(listed[:2]))
        shot("fake_1_aurelie.png")

        # ---------------------------------------------------- 2. Aurélie capture et juge un rendu
        m = len(LOG)
        index = str(site / "index.html")
        gui(lambda: win.submit(f"@local fais une capture de {index} en version mobile et dis-moi si les couleurs sont bien et si le texte est lisible"))
        check("Aurélie envoie un rendu dans la conversation", wait(lambda: since(m, t="image"), 240))
        check("puis elle répond", wait(lambda: local_replies(m), 240))
        r2 = local_replies(m)[0]["text"] if local_replies(m) else ""
        show("Aurélie (jugement du rendu)", r2)
        check("son jugement s'appuie sur des mesures vraies (contraste 1.66 repéré)", "1.66" in r2 or "1,66" in r2 or "contraste" in r2.lower(), r2[:160])
        steps = [e.get("text", "") for e in since(m, t="step")]
        check("l'activité en direct montre son travail (étapes)", len(steps) >= 2 or len(since(m, t="live_action")) >= 2, str(steps[:3]))
        shot("fake_2_rendu.png")

        # ---------------------------------------------------- 3. une vraie tâche de Jimmy (Claude)
        m = len(LOG)
        gui(lambda: win.submit("@claude Dans index.html, change le texte du bouton en « Valider » et sa couleur de fond en vert #0a7d33, "
                               "puis rends le texte du paragraphe plus foncé (#333333) pour qu'il soit lisible. Réponds en une seule phrase courte."))
        check("Jimmy démarre : l'activité s'affiche en direct (outils lancés)", wait(lambda: since(m, t="work", phase="start"), 120), "aucun événement work")
        check("le MICRO reste ouvert pendant que Jimmy travaille (tu peux parler pour ajouter une précision)", gui_wait(lambda: win.busy and not win.listener._paused.is_set()))
        shot("fake_3a_jimmy_en_cours.png")
        check("la tâche de Jimmy se termine", wait(lambda: gui_wait(lambda: not win.busy), 300, 1.0) and bool(since(m, t="work")), "")
        works = since(m, t="work", phase="start")
        tools = [w.get("tool") for w in works]
        edits = [w for w in works if w.get("tool") in ("Edit", "MultiEdit", "Write")]
        show("Jimmy : outils vus en direct", ", ".join(f"{w.get('tool')}:{Path(w.get('target') or '').name or w.get('label', '')[:40]}" for w in works))
        check("on voit ce que Jimmy lit et modifie, avec les lignes changées", bool(edits) and any("+ " in (w.get("detail") or "") for w in edits), str(tools))
        check("la modification est bien faite dans le fichier", "Valider" in (site / "index.html").read_text(encoding="utf-8"))
        check("le résultat de chaque action arrive (réussi / échec)", bool(since(m, t="work", phase="end")))
        check("Aurélie relit les fichiers modifiés à la fin", wait(lambda: any("relu" in str(e.get("text", "")) and e.get("from") == "local" for e in since(m, t="dialog")), 120), "")
        wait(lambda: since(m, t="handoff", to="jimmy") and since(m, t="image"), 120)
        check("Aurélie envoie le rendu final dans la conversation", bool(since(m, t="image")))
        dlg = [e.get("text", "") for e in since(m, t="dialog") if e.get("from") == "local"]
        show("Aurélie → Jimmy (relecture + rendu)", "\n".join(dlg))
        check("passages de la main visibles (Jimmy → Aurélie → Jimmy)", bool(since(m, t="handoff", to="local")) and bool(since(m, t="handoff", to="jimmy")))
        shot("fake_3b_fin_de_tache.png")

        # ---------------------------------------------------- 4. Aurélie sait ce que fait Jimmy
        m = len(LOG)
        gui(lambda: win.submit("@local qu'est-ce que Jimmy vient de modifier ?"))
        check("Aurélie répond sur le travail de Jimmy", wait(lambda: local_replies(m), 120))
        r4 = local_replies(m)[0]["text"] if local_replies(m) else ""
        show("Aurélie (que fait Jimmy ?)", r4)
        check("sa réponse cite le fichier modifié", "index.html" in r4, r4[:160])
        shot("fake_4_activite.png")

        # ---------------------------------------------------- 4b. passage de relais demandé : Aurélie fait sa part, PUIS Jimmy fait la sienne
        m = len(LOG)
        gui(lambda: win.submit("@local d'abord Aurélie se présente, puis ensuite tu passes le relais à Jimmy pour qu'il se présente lui-même. Une phrase chacun."))
        check("relais : Aurélie fait sa part (elle se présente)", wait(lambda: local_replies(m), 150))
        check("relais : le passage de la main vers Jimmy a vraiment lieu", wait(lambda: since(m, t="handoff", to="jimmy"), 60))
        check("relais : Jimmy répond à son tour", wait(lambda: any(e.get("t") == "msg" and e.get("role") == "assistant" and "IA LOCALE" not in str(e.get("label", "")) for e in LOG[m:]), 240))
        wait(lambda: gui_wait(lambda: not win.busy), 120, 1.0)
        jr = [str(e.get("text", "")) for e in LOG[m:] if e.get("t") == "msg" and e.get("role") == "assistant" and "IA LOCALE" not in str(e.get("label", ""))]
        ar = local_replies(m)
        show("relais : Aurélie", ar[0]["text"] if ar else "")
        show("relais : Jimmy", jr[0] if jr else "")
        check("relais : les deux messages viennent de deux auteurs différents", bool(ar) and bool(jr) and ar[0]["text"][:60] != jr[0][:60])
        check("relais : Jimmy se présente lui-même (il parle de lui, pas d'Aurélie seule)", bool(jr) and "Jimmy" in jr[0], jr[0][:120] if jr else "")
        shot("fake_4b_relais.png")

        # ---------------------------------------------------- 4c. une demande de modification adressée à Aurélie passe AUTOMATIQUEMENT à Jimmy
        m = len(LOG)
        gui(lambda: win.submit("@local modifie le texte du bouton en « Payer » dans index.html. Réponds en une phrase."))
        check("modification demandée à Aurélie : le relais vers Jimmy est automatique", wait(lambda: since(m, t="handoff", to="jimmy"), 90))
        check("modification demandée à Aurélie : Jimmy travaille (outils vus en direct)", wait(lambda: since(m, t="work", phase="start"), 180))
        wait(lambda: gui_wait(lambda: not win.busy) and since(m, t="work", phase="end"), 240, 1.0)
        check("modification demandée à Aurélie : le fichier est bien modifié par Jimmy", "Payer" in (site / "index.html").read_text(encoding="utf-8"))
        wait(lambda: since(m, t="dialog"), 120)

        # ---------------------------------------------------- 5. la discussion se sauvegarde et se rouvre en entier
        sid = gui_wait(lambda: win._current_sid())
        check("la discussion avec Aurélie est devenue celle de Claude (un seul fil)", sid and not extras.is_local(sid), str(sid))
        check("l'ancienne discussion « Aurélie seule » n'est plus en double", not any(extras.is_local(s[0]) for s in sessions.list_sessions(str(site))))
        gui_wait(lambda: win.on_new())
        time.sleep(1.0)
        m = len(LOG)
        gui_wait(lambda: win.switch_session(sid))
        time.sleep(2.5)
        ev = LOG[m:]
        msgs = [e for e in ev if e.get("t") == "msg"]
        texts = " ".join(str(e.get("text", "")) for e in msgs)
        check("réouverture : ta 1re question à Aurélie est revenue", "présente-toi" in texts)
        check("réouverture : la réponse d'Aurélie est revenue", r1[:40] in texts if r1 else False)
        check("réouverture : la question sur le rendu aussi", "capture de" in texts)
        check("réouverture : la demande à Jimmy est revenue", "Valider" in texts)
        check("réouverture : les rendus sont revenus dans la conversation", len([e for e in ev if e.get("t") == "image"]) >= 2)
        check("réouverture : l'activité de Jimmy est rechargée dans le panneau", len([e for e in ev if e.get("t") == "work"]) >= 2 and any(e.get("t") == "feed_clear" for e in ev))
        check("réouverture : les messages d'Aurélie à Jimmy et les passages de main sont revenus", any(e.get("t") == "dialog" for e in ev) and any(e.get("t") == "xfer" for e in ev))
        order = [("user" if e.get("role") == "user" else "ia") for e in msgs]
        check("réouverture : l'ordre est celui de la discussion (toi, Aurélie, toi...)", order[:2] == ["user", "ia"], str(order[:4]))
        shot("fake_5_reouverture.png")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        RESULT.append(("exception " + repr(e), False))
    finally:
        gui(app.quit)


threading.Thread(target=scenario, daemon=True).start()
app.exec()
bad = [n for n, ok in RESULT if not ok]
print("\nRESULTAT :", "TOUT EST OK" if not bad else f"{len(bad)} ECHEC(S) : {bad}")
try:
    from PySide6.QtCore import QTimer
    win._live.shutdown()
except Exception:  # noqa: BLE001
    pass
# ménage : les discussions de test créées côté Claude Code pour ce dossier jetable
try:
    shutil.rmtree(sessions.project_dir(str(site)), ignore_errors=True)
except Exception:  # noqa: BLE001
    pass
print("captures d'écran :", OUT)
sys.exit(1 if bad else 0)
