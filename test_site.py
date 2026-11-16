"""Exploration de site par l'IA locale : alias du domaine, routage, pages annoncées, défilement du fil (sans réseau)."""
import re
from pathlib import Path
from brain import agent, web

class Cfg(dict):
    pass
web.configure(Cfg(site_url="https://exemple.org", site_doc="/doc/", site_alias=r"exempl?e?\.org"))

ok = True
def check(name, cond):
    global ok
    print(("OK   " if cond else "ECHEC"), name); ok = ok and bool(cond)

check("faute de frappe sur le site configuré corrigée", web.resolve("exempl.org/a") == "https://exemple.org/a")
check("sans site configuré : adresse inchangée", (web.configure({}), web.resolve("exempl.org/a"))[1] == "https://exempl.org/a")
check("domaine sans https complété", web.resolve("example.com/a") == "https://example.com/a")
check("adresse déjà complète inchangée", web.resolve("https://docs.python.org/3/") == "https://docs.python.org/3/")
p = agent.prefetch("va voir la documentation sur example.com")
check("n'importe quel site -> explorer_site", p and p[0][0] == "explorer_site" and p[0][1]["adresse"] == "example.com")
p = agent.prefetch("parcours https://docs.python.org/3/ pour asyncio")
check("adresse https -> explorer_site", p and p[0][0] == "explorer_site")
check("demande de modification : pas d'exploration", not any(c[0] == "explorer_site" for c in agent.prefetch("modifie le site exemple.org")))
check("promesse de relais sans outil = relais réel", agent.is_failure("Je vais demander à Claude de reprendre la demande.") and agent.is_failure("Oui, j'ai bien transmis la demande à Claude."))
check("vraie réponse : pas de relais", not agent.is_failure("Voici les 20 reliques les plus puissantes : Sceau du Tyran, Croc du Vampire."))
check("mots du sujet extraits (sans mots courants)", web.keywords_of("il y a moyen taille sur mon site, sur les reliques, 20 les meilleurs") == ["taille", "reliques"])
web.configure(Cfg(site_url="https://exemple.org", site_doc="/doc/", site_alias=r"exempl?e?\.org"))
check("navigateur : faute corrigée, autres adresses intactes", web.fix_alias("exempl.org/x") == "https://exemple.org/x" and web.fix_alias("C:/a/page.html") == "C:/a/page.html" and web.fix_alias("localhost:8000") == "localhost:8000")
fake = "Le Sceau du Tyran donne +3 dégâts. Le Croc du Vampire soigne. Cape du Phénix : vie."
check("contrôle anti-invention : vrais noms acceptés, faux refusés", agent.ungrounded("**Sceau du Tyran** et **Croc du Vampire**", fake) == [] and agent.ungrounded("**Sceau du Tyran** et **Épée du Destin**", fake) == ["Épée du Destin"])
check("« aller sur mon site » déclenche l'exploration", agent.prefetch("tu peux aller sur mon site et chercher les reliques")[0][0] == "explorer_site")
js = Path(__file__).with_name("webui").joinpath("app.js").read_text(encoding="utf-8")
check("fil d'activité : suit le bas seulement si on y est", "function feedStick" in js and "if (!L.stick) return" in js and "box.scrollTop = box.scrollHeight; L.feedN" not in js)
print("TOUT OK" if ok else "DES ECHECS"); raise SystemExit(0 if ok else 1)
