"""Test du « PC » d'Aurélie : navigateur intégré, captures, rapport de page, lecture du texte d'une image, règles de sécurité des outils."""
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

work = Path(tempfile.mkdtemp(prefix="jlive_"))
import config

config.data_dir = lambda: work

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC"), name)
    if not cond:
        fails.append(name)


page = work / "demo.html"
page.write_text("""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Boutique de test</title></head>
<body style="margin:0;font-family:Arial;background:#fff">
<h1 style="font-size:64px;margin:30px">BOUTIQUE EN LIGNE</h1>
<h2>Nos produits</h2>
<p id="msg">Bienvenue chez nous.</p>
<button id="ok" style="font-size:28px;padding:14px" onclick="document.getElementById('msg').innerText='Commande validée !'">Valider</button>
<input id="nom" placeholder="Votre nom" style="font-size:24px;display:block;margin:20px">
<img src="introuvable.png">
<div style="width:2200px;height:40px;background:#c33;color:#fff">bande trop large</div>
<div style="height:1800px;background:linear-gradient(#fff,#9cf)">bas de page</div>
<script>console.error("boom de test");</script>
</body></html>""", encoding="utf-8")
secret = work / ".env"
secret.write_text("X=1")

from brain import live, tools, vision

lb = live.LiveBrowser()
frames, images, actions, clicks = [], [], [], []
lb.on_frame = lambda d: frames.append(d)
lb.on_image = lambda f, c, w: images.append((f, c, w))
lb.on_action = actions.append
lb.on_click = clicks.append
live.instance = lb
R = {}


def job():
    try:
        R["bad1"] = lb.open("ftp://exemple.com")
        R["bad2"] = lb.open(str(secret))
        R["open"] = lb.open(str(page))
        R["text"] = lb.text()
        R["report"] = lb.report()
        R["cap"] = lb.capture(caption="Accueil")
        R["full"] = lb.capture(full=True, who="local")
        R["sel"] = lb.capture(selector="#ok")
        R["mob"] = lb.capture(width=390)
        R["click"] = lb.click("Valider")
        R["text2"] = lb.text()
        R["type"] = lb.type_text("Votre nom", "Camille")
        R["scroll"] = lb.scroll("bas")
        R["cap2"] = lb.capture()
        R["ocr"] = vision.ocr(R["cap"]["file"])
        R["basics"] = vision.basics(R["cap"]["file"])
        R["analyze"] = vision.analyze(SimpleNamespace(get=lambda k, d=None: d), R["cap"]["file"], "Que dit la page ?")
        ctx = tools.Context(cfg=SimpleNamespace(get=lambda k, d=None: d), user_text="")
        reg = tools.base_registry()
        R["refus_click"] = reg.call("cliquer", {"cible": "Valider"}, ctx)
        R["refus_screen"] = reg.call("capturer_ecran", {}, ctx)
        ctx2 = tools.Context(cfg=ctx.cfg, user_text="clique sur Valider")
        R["ok_click"] = reg.call("cliquer", {"cible": "Valider"}, ctx2)
        R["tool_img"] = reg.call("analyser_image", {"chemin": "", "question": "titre ?"}, ctx2)
        R["tool_cap"] = reg.call("capturer_page", {"adresse": str(page), "largeur": "500"}, ctx)
        R["tool_report"] = reg.call("rapport_page", {}, ctx)
        import window as W
        dlg, ho, bumped = [], [], []
        enabled = {"local_enabled": True}
        me = SimpleNamespace(cfg=SimpleNamespace(get=lambda k, d=None: enabled.get(k, d)), sig=SimpleNamespace(dialog=SimpleNamespace(emit=lambda f, t, x: dlg.append((f, t, x)))),
                             _announce_handoff=lambda f, t, w="": ho.append((f, t)), _bump_local=lambda k: bumped.append(k))
        me._delegate_act_inner = lambda c, r: W.JimmyWindow._delegate_act_inner(me, c, r)
        n_imgs = len(images)
        R["act_cap"] = W.JimmyWindow._delegate_act(me, "capture", {"url": str(page), "full": True, "width": "0", "element": "", "caption": "Pour Jimmy"})
        R["act_imgs"] = len(images) - n_imgs
        R["act_see"] = W.JimmyWindow._delegate_act(me, "see", {"path": R["cap"]["file"], "question": "Que dit la page ?"})
        R["act_secret"] = W.JimmyWindow._delegate_act(me, "see", {"path": str(work / "secret.png")})
        R["act_badurl"] = W.JimmyWindow._delegate_act(me, "capture", {"url": "ftp://x", "full": False, "width": "0", "element": "", "caption": ""})
        enabled["local_enabled"] = False
        R["act_off"] = W.JimmyWindow._delegate_act(me, "capture", {"url": str(page)})
        R["act_dlg"], R["act_ho"], R["act_bump"] = dlg, ho, bumped
        R["tool_secret"] = reg.call("analyser_image", {"chemin": str(work / "id_rsa.png")}, ctx)
    except Exception as e:  # noqa: BLE001
        R["error"] = repr(e)
    finally:
        R["done"] = True


threading.Thread(target=job, daemon=True).start()
poll = QTimer()
poll.setInterval(300)
poll.timeout.connect(lambda: app.quit() if R.get("done") else None)
poll.start()
QTimer.singleShot(170000, app.quit)
app.exec()

check("aucune erreur de test", "error" not in R and R.get("done"))
if "error" in R:
    print("   ", R["error"])
check("adresse ftp refusée", not R["bad1"].get("ok"))
check("fichier secret refusé", not R["bad2"].get("ok") and "secret" in R["bad2"].get("error", ""))
check("page ouverte avec son titre", R["open"].get("ok") and R["open"].get("title") == "Boutique de test")
check("le texte affiché est lu", "BOUTIQUE EN LIGNE" in R["text"].get("text", "") and "Bienvenue" in R["text"]["text"])
rep = R["report"].get("report", {})
check("rapport : image cassée repérée", any("introuvable" in s for s in rep.get("broken_images", [])))
check("rapport : débordement en largeur repéré", rep.get("overflow_x") is True or bool(rep.get("too_wide")))
check("rapport : erreur JavaScript repérée", any("boom de test" in e for e in rep.get("console_errors", [])))
check("rapport : titres lus", any("Nos produits" in h for h in rep.get("headings", [])))
check("capture : fichier PNG créé", R["cap"].get("ok") and Path(R["cap"]["file"]).is_file() and R["cap"]["w"] >= 1000)
check("capture : annoncée pour la discussion (une fois)", images and images[0][1] == "Accueil" and images[0][2] == "local")
check("capture page entière : plus haute que l'écran", R["full"].get("ok") and R["full"]["h"] > 1500)
check("capture d'un élément : petite", R["sel"].get("ok") and R["sel"]["w"] < 500 and R["sel"]["h"] < 200)
check("capture en largeur mobile (390 px)", R["mob"].get("ok") and R["mob"]["w"] == 390)
check("clic : le texte de la page change", R["click"].get("ok") and "Commande validée" in R["text2"].get("text", ""))
check("clic : position envoyée pour l'anneau du panneau", clicks and clicks[0]["x"] > 0)
check("saisie dans un champ", R["type"].get("ok"))
check("défilement", R["scroll"].get("ok") and R["scroll"]["pos"].get("y", 0) > 100)
check("images en direct envoyées au panneau", len(frames) >= 3 and frames[-1].get("jpg", "")[:4] == "/9j/")
check("fil d'activité renseigné", any("J'ouvre" in a for a in actions) and any("capture" in a for a in actions))
check("lecture du texte de l'image (BOUTIQUE)", "BOUTIQUE" in R["ocr"].upper())
check("couleurs de l'image", R["basics"]["w"] >= 1000 and len(R["basics"]["colors"]) >= 2)
check("analyse : texte + limites honnêtes", "BOUTIQUE" in R["analyze"].upper() and "aucun modèle de vision" in R["analyze"])
check("clic refusé sans demande de l'utilisateur", "REFUSÉ" in R["refus_click"])
check("capture d'écran refusée sans demande", "REFUSÉ" in R["refus_screen"])
check("clic accepté quand l'utilisateur le demande", "Cliqué" in R["ok_click"])
check("analyser_image sans chemin = dernière capture", "Image : cap-" in R["tool_img"])
check("outil capturer_page : ouvre + capture + prévient", "Capture enregistrée" in R["tool_cap"] and "DÉJÀ affichée" in R["tool_cap"])
check("outil rapport_page : résumé lisible", "Problèmes" in R["tool_report"])
check("outil analyser_image : fichier secret refusé", "REFUSÉ" in R["tool_secret"])
check("délégation : Jimmy reçoit le chemin, le rapport et le texte lu", "Capture enregistrée" in R["act_cap"] and "Problèmes" in R["act_cap"] and "BOUTIQUE" in R["act_cap"].upper())
check("délégation : la capture s'affiche aussi pour l'utilisateur", R["act_imgs"] == 1)
check("délégation : l'image n'est PAS renvoyée à Jimmy (texte seulement)", "base64" not in R["act_cap"] and len(R["act_cap"]) < 4000)
check("délégation : analyse d'image", "Texte lu dans l'image" in R["act_see"] and "BOUTIQUE" in R["act_see"].upper())
check("délégation : fichier secret refusé", "REFUSÉ" in R["act_secret"])
check("délégation : mauvaise adresse -> message clair", "Impossible d'ouvrir" in R["act_badurl"])
check("délégation : IA locale coupée -> Jimmy est prévenu", "désactivée" in R["act_off"])
check("délégation : passages Jimmy -> Aurélie -> Jimmy annoncés", ("jimmy", "local") in R["act_ho"] and ("local", "jimmy") in R["act_ho"])
check("délégation : Aurélie est toujours rendue à Jimmy (même en cas de refus)", R["act_ho"].count(("local", "jimmy")) == R["act_ho"].count(("jimmy", "local")) + 0 or R["act_ho"][-1] == ("local", "jimmy"))
check("délégation : dialogue visible dans la discussion", any(f == "jimmy" for f, t, x in R["act_dlg"]) and any(f == "local" for f, t, x in R["act_dlg"]))
check("délégation : comptée dans les statistiques", R["act_bump"].count("delegated") >= 4)
check("galerie : captures retrouvées", len(live.list_captures()) >= 6)
check("purge : rien de récent supprimé", live.purge_captures(14) == 0 and len(live.list_captures()) >= 6)

# ---------------------------------------------------------------- Jimmy (Claude) -> Aurélie : commandes capture et see
import local_server

seen = {}
srv = local_server.LocalServer(lambda q: "réponse " + q, lambda cmd, req: (seen.update(cmd=cmd, req=req) or "ok " + cmd))
ok, ans = local_server.request({"cmd": "capture", "url": "https://exemple.fr", "full": True, "width": "390"}, srv.port, srv.token)
check("serveur : commande capture transmise avec ses options", ok and seen.get("cmd") == "capture" and seen["req"]["url"] == "https://exemple.fr" and seen["req"]["full"] is True and seen["req"]["width"] == "390")
ok, ans = local_server.request({"cmd": "see", "path": "a.png", "question": "titre ?"}, srv.port, srv.token)
check("serveur : commande see transmise", ok and seen.get("cmd") == "see" and seen["req"]["question"] == "titre ?")
ok, ans = local_server.ask("salut", srv.port, srv.token)
check("serveur : ask fonctionne toujours", ok and ans == "réponse salut")
ok, ans = local_server.request({"cmd": "capture", "url": "x"}, srv.port, "mauvais-jeton")
check("serveur : mauvais jeton refusé", not ok and "invalide" in ans.lower())
ok, ans = local_server.request({"cmd": "supprimer"}, srv.port, srv.token)
check("serveur : commande inconnue refusée", "inconnue" in ans)
rest = ["https://exemple.fr", "--width", "390", "--caption", "Accueil mobile"]
check("ligne de commande : options lues", local_server._opt(rest, "--width", "0") == "390" and local_server._opt(rest, "--caption") == "Accueil mobile" and rest == ["https://exemple.fr"])
check("ligne de commande : usage si incomplet", local_server.main(["capture"]) == 2)
import claude_bridge

hint = claude_bridge.ClaudeBridge._local_hint(SimpleNamespace(extra_env={"JIMMY_LOCAL_PORT": "1"}, cfg=SimpleNamespace(get=lambda k, d=None: True if k == "local_enabled" else d)))
check("Claude est prévenu : capture, see et économie de tokens", " capture " in hint and " see " in hint and "dernier recours" in hint)
srv.shutdown()

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
