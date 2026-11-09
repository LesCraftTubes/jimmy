"""Test de la reprise de contexte, des noms et du ménage des discussions, dans un dossier jetable.

Lancer : .venv\\Scripts\\python.exe -X utf8 test_handoff.py   (n'écrit rien dans tes vraies discussions ni ta mémoire)
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="jimmy_test_"))
os.environ["JIMMY_MEM_DIR"] = str(root / "mem")
sys.path.insert(0, str(Path(__file__).parent))

import config
import jimmy_mem
import sessions

config.data_dir = lambda: root / "data"
(root / "data").mkdir()
sessions.projects_root = lambda: root / "claude_projects"
WD = str(root / "work")
Path(WD).mkdir()
folder = sessions.project_dir(WD)
folder.mkdir(parents=True)

fails = []


def check(label, cond):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


def write_session(sid, entries, age_hours):
    p = folder / f"{sid}.jsonl"
    lines = []
    for role, content in entries:
        msg = {"type": role, "sessionId": sid, "timestamp": "2026-11-01T10:00:00Z",
               "message": {"role": role, "content": content}}
        lines.append(json.dumps(msg, ensure_ascii=False))
    p.write_text("\n".join(lines), encoding="utf-8")
    t = time.time() - age_hours * 3600
    os.utime(p, (t, t))
    return p


def tool(name, path):
    return [{"type": "text", "text": "je modifie"}, {"type": "tool_use", "name": name, "input": {"file_path": path}}]


# A : discussion d'origine ; B : ancienne reprise (gros résumé) ; C : reprise nouveau format
write_session("aaaa-1111", [
    ("user", "Refais la page boutique du site avec les nouveaux prix"),
    ("assistant", tool("Edit", "C:/site/boutique.php")),
    ("assistant", [{"type": "text", "text": "Page boutique refaite, il reste le panier à tester."}]),
    ("user", "Teste le panier maintenant avec un vrai achat de test"),
    ("assistant", [{"type": "text", "text": "Panier testé : un bug sur la quantité."}]),
], 50)
recap_old = ("[Reprise de contexte : la discussion précédente était presque pleine (limite de taille). Voici l'essentiel.\n"
             "Au départ, l'utilisateur voulait : Refais la page boutique du site avec les nouveaux prix\n"
             "Derniers échanges :\nUtilisateur : Teste le panier maintenant avec un vrai achat de test\n"
             "Jimmy : Panier testé : un bug sur la quantité.\nContinue à partir de là.]")
write_session("bbbb-2222", [("user", recap_old), ("assistant", [{"type": "text", "text": "Je corrige la quantité."}]),
                            ("user", "Ok, corrige aussi le total")], 30)
write_session("cccc-3333", [("user", sessions.mini_message("Page boutique", "Refais la page boutique")),
                            ("assistant", [{"type": "text", "text": "Reprise ok."}])], 20)
write_session("zzzz-9999", [("user", "Une autre discussion sans rapport"),
                            ("assistant", [{"type": "text", "text": "Ok."}])], 10)

# 1) noms
check("nom retrouvé dans un mini-message", sessions._title(folder / "cccc-3333.jsonl") == "Page boutique")
check("ancien résumé -> but d'origine", sessions._title(folder / "bbbb-2222.jsonl").startswith("Refais la page boutique"))
check("message de reprise affiché court", sessions._user_text(
    [{"type": "text", "text": sessions.mini_message("X", "y")}]) == "↺ Suite de la discussion.")

# 2) ménage : A, B, C = une seule discussion, la plus récente (C) gardée avec le nom d'origine
plan = sessions.plan_cleanup(WD)
check("B (dernière de la chaîne A -> B) gardée", "bbbb-2222" in plan["keep"])
check("A à supprimer (doublon de la même discussion)", plan["remove"] == ["aaaa-1111"])
check("zzzz non touchée", "zzzz-9999" not in plan["remove"])
done = sessions.apply_cleanup(WD, plan)
check("1 supprimée", done["removed"] == 1)
check("fichier retiré", not (folder / "aaaa-1111.jsonl").exists() and (folder / "bbbb-2222.jsonl").exists())
check("copie en corbeille", (sessions.trash_dir() / "aaaa-1111.jsonl").exists())
check("B a le nom d'origine", sessions.display_name(WD, "bbbb-2222").startswith("Refais la page boutique"))
check("C a son nom", sessions.display_name(WD, "cccc-3333") == "Page boutique")
check("notes en mémoire (but + fichiers)", any("boutique" in r["contenu"] for r in jimmy_mem.search("boutique panier")))
check("fichier touché mémorisé", any("boutique.php" in r["contenu"] for r in jimmy_mem.search("fichiers boutique")))
lst = [t for _i, t, _w in sessions.list_sessions(WD)]
check("liste : une entrée par vraie discussion", len(lst) == 3 and not any(t.startswith("↺") for t in lst))

# 3) renommage manuel durable + reprise : le nom manuel survit, aucun préfixe ajouté
sessions.set_name("cccc-3333", "Ma boutique", manual=True)
write_session("cccc-3333", [("user", sessions.mini_message("Page boutique", "x")),
                            ("assistant", [{"type": "text", "text": "Contexte presque plein."}]),
                            ("user", "Ajoute une promo"), ("assistant", tool("Write", "C:/site/promo.php"))], 1)
name = sessions.display_name(WD, "cccc-3333")
res = sessions.handoff(WD, "cccc-3333", name, delete=True, days=7)
check("reprise : ancienne supprimée", res["deleted"] and not (folder / "cccc-3333.jsonl").exists())
check("reprise : mini-message sans gros résumé", len(res["message"]) < 450 and "Ma boutique" in res["message"])
check("reprise : nom manuel retrouvé dans le mini-message", sessions.resume_info(res["message"])[0] == "Ma boutique")
check("reprise : ancienne copie en corbeille", (sessions.trash_dir() / "cccc-3333.jsonl").exists())
write_session("dddd-4444", [("user", res["message"]), ("assistant", [{"type": "text", "text": "ok"}])], 0)
check("nouvelle discussion = même nom (aucun suffixe)", sessions._title(folder / "dddd-4444.jsonl") == "Ma boutique")
check("note de reprise en mémoire", any("promo" in r["contenu"] for r in jimmy_mem.search("Ma boutique promo")))

# 4) sécurité : identifiant vérifié, jamais le fichier d'une autre discussion
bad = write_session("eeee-5555", [("user", "x")], 40)
txt = bad.read_text(encoding="utf-8").replace('"sessionId": "eeee-5555"', '"sessionId": "autre-id"')
bad.write_text(txt, encoding="utf-8")
check("refuse un fichier dont l'identifiant ne correspond pas", sessions.delete_session(WD, "eeee-5555") is False and bad.exists())
check("refuse un identifiant piégé", sessions.delete_session(WD, "../x") is False)

# 5) corbeille purgée
old = sessions.trash_dir() / "aaaa-1111.jsonl"
t = time.time() - 9 * 86400
os.utime(old, (t, t))
check("purge de la corbeille (> 7 jours)", sessions.purge_trash(7) >= 1 and not old.exists())

# 6) secret refusé en mémoire
try:
    jimmy_mem.add_note("clé", "mot de passe : hunter2abc")
    check("secret refusé", False)
except ValueError:
    check("secret refusé", True)

print("\nRÉSULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ÉCHEC(S) : {fails}")
sys.exit(1 if fails else 0)
