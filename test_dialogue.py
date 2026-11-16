"""Test du dialogue IA locale <-> Jimmy. Lancer : python -W ignore test_dialogue.py"""
import sys
import tempfile
import time
import types
from pathlib import Path
from types import SimpleNamespace

from brain import agent as A
from brain import dialogue as D
from brain import tools as T
import local_server

fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- les étapes deviennent des phrases
cases = {
    "Commande · Voir la config utilisateur et les messages système": "Je regarde la config utilisateur et les messages système.",
    "Lecture · je lis shop.php": "Je lis shop.php.",
    "Écriture · j'écris _glitch_try.py": "J'écris _glitch_try.py.",
    "Commande · Supprimer la capture qui contenait le bureau": "Je supprime la capture qui contenait le bureau.",
    "Web · hauteur de la tour Eiffel": "Je cherche « hauteur de la tour Eiffel » sur Internet.",
    "Mémoire · garl boss": "Je regarde dans ma mémoire : garl boss.",
    "Analyse · Je vérifie le style": "Je vérifie le style.",
    "Résultat · 330 mètres": "J'ai obtenu : 330 mètres.",
}
for src, want in cases.items():
    got = D.humanize_step(src)
    check(f"phrase : {src[:46]}", got == want)
    if got != want:
        print("      obtenu :", got)
check("une phrase n'a plus de séparateur technique « · »", all(" · " not in D.humanize_step(s) for s in cases))

# ---------------------------------------------------------------- l'IA locale écrit à Jimmy
journal = ["chercher_web(hauteur tour Eiffel) -> [Résultats via Bing] Tour Eiffel", "lire_page(https://x) -> début de la page"]


class Eng:
    def __init__(self, text="", delay=0.0, boom=False):
        self.text, self.delay, self.boom, self.seen = text, delay, boom, None

    def chat(self, messages, tools=None):
        self.seen = messages
        if self.boom:
            raise RuntimeError("moteur planté")
        time.sleep(self.delay)
        return {"content": self.text}


e = Eng("Jimmy, il veut la hauteur de la tour Eiffel puis l'ajouter à sa note. J'ai trouvé 330 m mais je ne sais pas modifier sa note, je te laisse la suite.")
msg = D.message_to_jimmy(e, "cherche la hauteur de la tour Eiffel et ajoute-la à ma note", journal, "demande", "Aurélie")
check("l'IA locale écrit SON message avec son modèle", msg.startswith("Jimmy, il veut") and "330" in msg)
check("le modèle reçoit la demande ET ce qui a déjà été fait", "tour Eiffel" in e.seen[1]["content"] and "chercher_web" in e.seen[1]["content"])
check("le modèle sait qui il est (prénom)", "Aurélie" in e.seen[0]["content"])
back = D.message_to_jimmy(None, "redémarre le serveur", journal, "indisponible")
check("moteur éteint : phrase de secours naturelle, jamais de plantage", back.startswith("Jimmy,") and "redémarre le serveur" in back and "éteint" in back)
check("moteur en panne : phrase de secours", D.message_to_jimmy(Eng(boom=True), "x" * 30, journal, "erreur").startswith("Jimmy,"))
t0 = time.time()
slow = D.message_to_jimmy(Eng("Une réponse très lente mais valide pour Jimmy.", delay=3), "demande lente", journal, "demande", timeout=0.5)
check("moteur trop lent : secours en moins d'une seconde", time.time() - t0 < 1.5 and slow.startswith("Jimmy,"))
check("réponse trop courte ou vide : secours", D.message_to_jimmy(Eng("ok"), "demande", journal, "refus").startswith("Jimmy,"))

# ---------------------------------------------------------------- Jimmy demande un travail à l'IA locale (serveur + commande)
received = []
srv = local_server.LocalServer(lambda q: received.append(q) or f"Réponse à : {q}")
env = srv.env()
ok, ans = local_server.ask("où est le fichier shop.php ?", env["JIMMY_LOCAL_PORT"], env["JIMMY_LOCAL_TOKEN"])
check("Jimmy vers IA locale : la question arrive, la réponse revient", ok and ans == "Réponse à : où est le fichier shop.php ?" and received == ["où est le fichier shop.php ?"])
ok2, ans2 = local_server.ask("x", env["JIMMY_LOCAL_PORT"], "mauvais-jeton")
check("mauvais jeton : refusé (un autre programme ne peut pas s'en servir)", not ok2 and "invalide" in ans2.lower() and len(received) == 1)
import os
os.environ.pop("JIMMY_LOCAL_PORT", None)          # ce test tourne peut-être DANS un Jimmy en marche : on enlève ses variables
os.environ.pop("JIMMY_LOCAL_TOKEN", None)
ok3, ans3 = local_server.ask("x", None, None)
check("IA locale coupée : message clair pour Claude", not ok3 and "toi-même" in ans3)
srv.shutdown()

# ---------------------------------------------------------------- la délégation est en LECTURE SEULE (le code l'impose)
tmp = Path(tempfile.mkdtemp(prefix="jdeleg_"))


class Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


cfg = Cfg(workdir=str(tmp))


class Script:
    def __init__(self, script):
        self.script = list(script)

    def chat(self, messages, tools=None):
        return self.script.pop(0)


ag = A.LocalAgent(cfg)
ag.engine = Script([{"content": "", "tool_calls": [{"id": "1", "function": {"name": "ecrire_fichier", "arguments": {"chemin": "piege.txt", "contenu": "x"}}}]},
                    {"content": "Je n'ai pas pu écrire."}])
ag.registry, ag.packs = T.base_registry(), []
ag.run("crée le fichier piege.txt", readonly=True)
check("demande venue de Jimmy : l'écriture est REFUSÉE par le code", not (tmp / "piege.txt").exists())
ag2 = A.LocalAgent(cfg)
(tmp / "a.txt").write_text("contenu lisible")
ag2.engine = Script([{"content": "", "tool_calls": [{"id": "1", "function": {"name": "lire_fichier", "arguments": {"chemin": "a.txt"}}}]},
                     {"content": "Le fichier contient : contenu lisible."}])
ag2.registry, ag2.packs = T.base_registry(), []
reply, _h = ag2.run("lis a.txt", readonly=True)
check("demande venue de Jimmy : la lecture marche", "contenu lisible" in reply)

# ---------------------------------------------------------------- côté fenêtre : les deux messages s'affichent, dans l'ordre
import window as W

events = []
me = SimpleNamespace(cfg=cfg, local_agent=None, _local_lock=__import__("threading").Lock(),
                     sig=SimpleNamespace(dialog=SimpleNamespace(emit=lambda f, t, x: events.append((f, t, x)))), bumped=[])
cfg["local_enabled"] = True
me._ensure_local_agent = lambda: ""
me._seed_local_context = lambda: None
me.local_agent = SimpleNamespace(history=[], run=lambda q, readonly=False: (f"J'ai trouvé shop.php dans /srv ({'lecture seule' if readonly else 'normal'}).", ""))
me._bump_local = lambda k: me.bumped.append(k)
out = W.JimmyWindow._delegate(me, "Aurélie, où est shop.php ?")
check("fenêtre : 1) Jimmy parle à l'IA locale, 2) l'IA locale répond à Jimmy", [(f, t) for f, t, _ in events] == [("jimmy", "local"), ("local", "jimmy")])
check("fenêtre : la question et la réponse sont affichées en entier", events[0][2] == "Aurélie, où est shop.php ?" and "shop.php" in events[1][2])
check("fenêtre : la réponse revient à Claude, en lecture seule", out == events[1][2] and "lecture seule" in out)
check("fenêtre : compté dans recherches pour Jimmy", me.bumped == ["delegated"])
cfg["local_enabled"] = False
events.clear()
check("IA locale désactivée : Claude est prévenu, rien d'affiché", "désactivée" in W.JimmyWindow._delegate(me, "x") and events == [])

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
