"""Test du passage de relais : « fais ça PUIS passe le relais à Jimmy » doit vraiment lancer Jimmy avec sa part, et les demandes de modification
adressées à Aurélie passent automatiquement à Jimmy."""
import sys
from types import SimpleNamespace

from brain import tools
from brain.agent import LocalAgent, split_relay

fails = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "ECHEC"), name, "" if cond else detail)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- découpage de la demande
r = split_relay("nn d'abord aurélie se présente, puis ensuite tu passe le relais à jimmy pour qu'il se présente lui-même")
check("ta demande exacte : part d'Aurélie = se présenter, part de Jimmy = se présenter lui-même", r == ("présente-toi en deux phrases", "présente-toi toi-même en deux phrases"), str(r))
r = split_relay("présente-toi puis passe le relais à Jimmy pour qu'il se présente")
check("« présente-toi puis passe le relais à Jimmy »", r and r[0].startswith("présente-toi") and "toi-même" in r[1], str(r))
r = split_relay("explique ce qu'est un contraste, ensuite tu passes la main à Jimmy pour qu'il modifie le bouton")
check("la part de Jimmy est conservée (modifier le bouton)", r and r[0].startswith("explique") and r[1].startswith("modifie le bouton"), str(r))
r = split_relay("Aurélie, dis à Jimmy de modifier la couleur du bouton")
check("« dis à Jimmy de... » : Aurélie n'a rien à faire avant, tout passe à Jimmy", r == ("", "modifier la couleur du bouton"), str(r))
r = split_relay("présentez-vous tous les deux, chacun son tour")
check("« présentez-vous » : une présentation chacun", r and r[0].startswith("présente-toi") and "toi-même" in r[1], str(r))
check("une demande normale n'est PAS un relais", split_relay("quelle heure est-il ?") is None and split_relay("que fait Jimmy en ce moment ?") is None)
check("parler de Jimmy sans demander de relais n'en est pas un", split_relay("Jimmy a modifié le fichier hier") is None)


# ---------------------------------------------------------------- comportement de l'agent
class Eng:
    def __init__(self):
        self.asked = []

    def chat(self, messages, tools=None):
        self.asked.append(messages[-1]["content"])
        return {"content": "Je suis Aurélie, l'IA locale de Jimmy : je tourne sur ton PC."}


def agent():
    ag = LocalAgent(SimpleNamespace(get=lambda k, d=None: d))
    ag.engine, ag.packs, ag.registry = Eng(), [], tools.base_registry()
    return ag


ag = agent()
reply, hand = ag.run("nn d'abord aurélie se présente, puis ensuite tu passe le relais à jimmy pour qu'il se présente lui-même")
check("Aurélie fait SA part (elle se présente)", "Aurélie" in reply and "Jimmy" in reply)
check("sa présentation est courte et fixe (une ou deux phrases), sans passer par le modèle", len(reply) < 260 and not ag.engine.asked)
check("le relais est PRÉPARÉ pour Jimmy, avec la raison « relais »", ag.last_reason == "relais" and hand.startswith("Demande de l'utilisateur"))
check("Jimmy reçoit sa part, et sait que celle d'Aurélie est faite", "À TOI" in hand and "présente-toi toi-même" in hand and "Aurélie" in hand and "ne refais pas" in hand, hand)
ag = agent()
reply, hand = ag.run("explique ce qu'est un contraste, ensuite tu passes le relais à Jimmy pour qu'il modifie le bouton")
check("sa part (autre que se présenter) passe par le modèle, SANS la part de Jimmy", len(ag.engine.asked) == 1 and "modifie le bouton" not in ag.engine.asked[0] and "contraste" in ag.engine.asked[0], str(ag.engine.asked))
check("et Jimmy reçoit : modifier le bouton", "modifie le bouton" in hand and ag.last_reason == "relais")

ag = agent()
reply, hand = ag.run("Aurélie, dis à Jimmy de modifier la couleur du bouton")
check("« dis à Jimmy de... » : Aurélie ne répond rien, Jimmy reçoit tout", reply == "" and "modifier la couleur du bouton" in hand and ag.last_reason == "relais" and not ag.engine.asked)

# demandes de modification adressées à Aurélie : passage automatique
for t in ["Hey Aurélie, modifie le bouton de la boutique", "corrige la couleur de l'interface", "ajoute une page pour le serveur", "déploie le site"]:
    ag = agent()
    reply, hand = ag.run(t)
    check(f"passage automatique à Jimmy : « {t} »", reply == "" and t in hand and ag.last_reason == "relais" and not ag.engine.asked, f"{reply!r} {hand!r}")

# ce qui doit rester pour Aurélie
for t in ["quelle est la capitale de la France ?", "qu'est-ce que Jimmy vient de modifier ?", "que fait Jimmy ?", "fais une capture de https://exemple.fr et dis-moi si le bouton est bien visible"]:
    ag = agent()
    try:
        reply, hand = ag.run(t)
    except Exception as e:  # noqa: BLE001
        reply, hand = f"(exception {e})", ""
    check(f"reste pour Aurélie (pas de relais) : « {t[:50]} »", ag.last_reason != "relais" and "À TOI" not in hand, f"{ag.last_reason!r} {hand[:80]!r}")

# les délégations de Jimmy (lecture seule) ne se relayent jamais vers lui-même
ag = agent()
reply, hand = ag.run("cherche où est shop.php puis passe le relais à Jimmy", readonly=True)
check("travail délégué par Jimmy : aucun relais (il ne se renvoie pas la balle)", ag.last_reason != "relais")

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
