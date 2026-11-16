"""Test de ce qui rend Aurélie utile sans token : relecture des fichiers de Jimmy, « que fait Jimmy ? », réponse composée par le code, titres propres."""
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jchk_"))
import config

config.data_dir = lambda: work
import extras
import sessions
from brain import checks, live_tools, tools, vision
from brain.agent import LocalAgent, prefetch
from brain.tools import FINAL

fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC"), name)
    if not cond:
        fails.append(name)


def w(name, text):
    p = work / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------- relecture des fichiers
r = checks.check_file(w("bon.py", "def f(x):\n    return x + 1\n"))
check("Python correct : aucun problème", r["ok"] and not r["problems"])
r = checks.check_file(w("casse.py", "def f(x:\n    return x\n"))
check("Python cassé : erreur de syntaxe avec la ligne", not r["ok"] and "ligne" in r["problems"][0])
r = checks.check_file(w("c.json", '{"a": 1,}'))
check("JSON invalide repéré", not r["ok"] and "JSON invalide" in r["problems"][0])
r = checks.check_file(w("p.html", "<html><body><div><p>Salut</body></html>"))
check("HTML : balise <div> jamais fermée repérée", not r["ok"] and any("div" in x for x in r["problems"]))
r = checks.check_file(w("ok.html", "<!doctype html><html><body><div><img src='a.png'><br><p>ok</div></body></html>"))
check("HTML correct (balises vides et <p> facultatif) : aucun problème", r["ok"])
r = checks.check_file(w("s.css", "a { color: red; \n b { color: blue; }"))
check("CSS : accolades déséquilibrées repérées", not r["ok"] and "accolades" in r["problems"][0])
FAKE = "hunter2" + "-super-" + "value"          # valeur d'essai coupée en morceaux : la garde anti-fuites ne doit pas la prendre pour un vrai secret
r = checks.check_file(w("conf.py", "DB_PASS" + "WORD = " + chr(34) + FAKE + chr(34) + "\nname = 1\n"))
check("secret écrit en clair repéré avec sa ligne", not r["ok"] and any("SECRET POSSIBLE" in x and "ligne 1" in x for x in r["problems"]))
check("la valeur du secret n'est JAMAIS recopiée", "hunter2" not in json.dumps(r, ensure_ascii=False))
r = checks.check_file(w("k.txt", "-----BEGIN RSA PRIV" + "ATE KEY-----\nabc\n"))
check("clé privée repérée", not r["ok"])
r = checks.check_file(w("ok2.py", 'password = os.environ["DB_PASSWORD"]\ntoken = ""\n'))
check("lecture d'une variable d'environnement : pas de fausse alerte", r["ok"])
r = checks.check_file(w(".env", "SECRET=abc123456\n"))
check("fichier de secrets : non lu du tout", r["skipped"] and r["ok"])
r = checks.check_file(str(work / "absent.py"))
check("fichier absent : dit qu'il est introuvable", "introuvable" in r["skipped"])
res = checks.check_files([w("a1.py", "x = 1\n"), w("a2.py", "x = (\n")])
sm = checks.summary(res)
check("résumé : nomme le fichier à problème et dit que l'autre est correct", "a2.py" in sm and "correct" in sm)
check("résumé : tout va bien", "aucun problème" in checks.summary(checks.check_files([w("b1.py", "y = 2\n")])))

# ---------------------------------------------------------------- « que fait Jimmy ? »
sid = "sess-work"
now = time.time()
for k, it in enumerate([dict(phase="say", text="Je regarde la boutique."),
                        dict(phase="start", id="1", tool="Read", label="Lecture · je lis shop.php", target="C:/s/shop.php"), dict(phase="end", id="1", ok=True, out="ok"),
                        dict(phase="start", id="2", tool="Edit", label="Modification · je modifie shop.php", target="C:/s/shop.php", detail="- a\n+ b"), dict(phase="end", id="2", ok=True, out="ok"),
                        dict(phase="start", id="3", tool="Bash", label="Commande · je teste", target="", detail="php -l shop.php"), dict(phase="end", id="3", ok=False, out="Parse error ligne 41"),
                        dict(phase="start", id="4", tool="Bash", label="Commande · je relance le test", target="")]):
    extras.add(sid, "work", **it)
ctx = tools.Context(cfg=SimpleNamespace(get=lambda k, d=None: d), user_text="")
check("sans discussion : le dit honnêtement", "pas de discussion" in live_tools._t_jimmy_work({}, ctx))
ctx.notes["session_id"] = "sess-vide"
check("discussion sans travail : le dit", "rien fait" in live_tools._t_jimmy_work({}, ctx))
ctx.notes["session_id"] = sid
txt = live_tools._t_jimmy_work({}, ctx)
check("« que fait Jimmy ? » : compte lectures, modifications, commandes", "1 lecture" in txt and "1 modification" in txt and "2 commande" in txt)
check("« que fait Jimmy ? » : fichier modifié, échec et action en cours", "shop.php" in txt and "Parse error" in txt and "En ce moment" in txt)
check("aiguillage : « que fait Jimmy ? » -> travail_de_jimmy", prefetch("Aurélie, que fait Jimmy en ce moment ?")[0][0] == "travail_de_jimmy" and prefetch("qu'est-ce que Jimmy a fait ?")[0][0] == "travail_de_jimmy")
tool_ctx = tools.Context(cfg=SimpleNamespace(get=lambda k, d=None: d), user_text="")
out = tools.base_registry().call("relire_fichiers", {"chemins": w("z1.py", "a = (\n") + ";" + w("z2.py", "b = 1\n")}, tool_ctx)
check("outil relire_fichiers", "z1.py" in out and "correct" in out)

# ---------------------------------------------------------------- réponse composée par le code (jugement de rendu)
audit = {"bg": [["#eeeeee", 72], ["#112244", 12]], "fg": [["#bbbbbb", 35], ["#000000", 20]], "fonts": [["Arial", 100]],
         "contrast_bad": [{"el": "p", "text": "Texte clair", "ratio": 1.66, "need": 4.5, "fg": "#bdbdbd", "bg": "#f1f1f1", "size": 20},
                          {"el": "button", "text": "Acheter", "ratio": 2.02, "need": 4.5, "fg": "#ffffff", "bg": "#fca311", "size": 18}], "contrast_bad_count": 2,
         "clipped": [{"el": "h3", "text": "Bouclier", "kind": "coupé avec « … »"}], "overlaps": [], "stretched": [], "small_count": 0}
info = {"file": "cap.png", "basics": None, "audit": audit, "verdict": ["2 texte(s) au contraste insuffisant", "1 texte(s) coupé(s)"], "vlm": "", "notes": ["pas de modèle de vision : ..."]}
rep = vision.judge_reply(info, "Boutique La Forge")
check("jugement : cite le contraste 1.66:1 ET 2.02:1 comme insuffisants (jamais « acceptable »)", "1.66:1" in rep and "2.02:1" in rep and rep.count("insuffisant") >= 2 and "acceptable" not in rep.lower())
check("jugement : couleurs nommées, texte coupé, verdict", "gris" in rep and "bleu nuit" in rep and "Texte coupé" in rep and "Verdict des mesures" in rep)
info["vlm"], info["vlm_model"] = "Un en-tête bleu foncé avec un bouton orange.", "qwen/qwen3-vl-4b"
check("jugement : ajoute ce que voit le modèle de vision", "modèle de vision" in vision.judge_reply(info) and "bouton orange" in vision.judge_reply(info))


class Eng:
    def chat(self, messages, tools=None):
        return {"content": "Tout va bien, le bouton est lisible."}      # le petit modèle adoucirait : on ne doit PAS l'entendre


ag = LocalAgent(SimpleNamespace(get=lambda k, d=None: d))
ag.engine, ag.packs = Eng(), []
reg = tools.base_registry()
reg.add(tools.Tool("juger_rendu", "x", {"adresse": "x"}, lambda a, c: FINAL + "RÉPONSE COMPOSÉE PAR LE CODE", required=[]))
ag.registry = reg
reply, hand = ag.run("juge le design de https://exemple.fr")
check("réponse finale d'un outil : rendue telle quelle, sans passer par le petit modèle", reply == "RÉPONSE COMPOSÉE PAR LE CODE" and hand == "")
check("elle est gardée dans l'historique d'Aurélie", ag.history[-1]["content"] == "RÉPONSE COMPOSÉE PAR LE CODE")

# ---------------------------------------------------------------- titres propres
t = sessions._user_text("[Contexte : l'IA locale de Jimmy a déjà répondu entre-temps : à « a » elle a répondu : b]\n\n@claude Dans index.html, change le bouton")
check("titre : sans le bruit technique ni le mot de routage", t == "Dans index.html, change le bouton")
check("titre : @local retiré", sessions._user_text("@local bonjour Aurélie") == "bonjour Aurélie")

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
