"""Test du passage IA locale -> Claude dans la fenêtre (mode Auto, mode manuel, @local). Lancer : python test_local_flow.py"""
import sys
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

import window as W

app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


def scenario(route, reason, text, handoff, forced=False):
    log = SimpleNamespace(messages=[], system=[], submitted=[], finished=0, stats=[], dialogs=[])
    me = SimpleNamespace(
        thinking=True, _local_reason=reason, _local_forced=forced, _last_reply="x", _force_claude=False,
        _local_ctx=[], _local_last_q="redémarre le serveur", _relay_msg="Jimmy, il veut redémarrer le serveur ; je ne sais pas faire, je te passe la main.", _local_name=lambda: "Aurélie", btn_voice=SimpleNamespace(isChecked=lambda: False), _remote_turn=False, chat=SimpleNamespace(next_label=None), _route=lambda: route, _remote_emit=lambda *_a: None, _HANDOFF_WHY=W.JimmyWindow._HANDOFF_WHY,
    )
    me._bump_local = lambda k: log.stats.append(k)
    me.add_dialog = lambda f, t, x: log.dialogs.append((f, t, x))
    me.add_message = lambda role, t: log.messages.append((role, t))
    me.add_system = lambda t: log.system.append(t)
    me._finish = lambda: setattr(log, "finished", log.finished + 1)

    def submit(t, echo=True):
        log.submitted.append((t, me._force_claude, echo))
    me.submit = submit
    W.JimmyWindow._on_local_reply(me, text, handoff)
    log.chat = me.chat
    app.processEvents()
    app.processEvents()
    return log


H = "Demande de l'utilisateur : redémarre le serveur\n\nL'IA locale n'a pas pu la traiter."

# Auto + refus : le refus n'est pas montré, Claude reprend, la ligne de passage est visible
l = scenario("auto", "refus", "Je ne peux pas faire ça.", H)
check("auto/refus : le « je ne peux pas » n'est PAS affiché", l.messages == [])
check("auto/refus : l'IA locale PARLE à Jimmy (vraie phrase, pas une ligne technique)", len(l.dialogs) == 1 and l.dialogs[0][:2] == ("local", "jimmy") and l.dialogs[0][2].startswith("Jimmy,") and l.system == [])
check("auto/refus : Claude reçoit la demande d'origine", len(l.submitted) == 1 and "redémarre le serveur" in l.submitted[0][0])
check("auto/refus : Jimmy reçoit le message de l'IA locale (avec son prénom)", "Aurélie" in l.submitted[0][0] and "Jimmy, il veut" in l.submitted[0][0])
check("auto/refus : forcé vers Claude, sans écho", l.submitted and l.submitted[0][1] is True and l.submitted[0][2] is False)

# Auto + moteur coupé
l = scenario("auto", "indisponible", "", "redémarre le serveur\n\n(L'IA locale est indisponible : moteur éteint)")
check("auto/moteur coupé : rien d'affiché comme réponse locale", l.messages == [])
check("auto/moteur coupé : Claude reprend, après un message de l'IA locale", len(l.submitted) == 1 and l.submitted[0][1] is True and len(l.dialogs) == 1)

# Auto + l'IA locale a demandé elle-même : sa phrase est montrée, puis Claude
l = scenario("auto", "demande", "Je passe la main à Claude.", H)
check("auto/demande : sa phrase est montrée", l.messages == [("local", "Je passe la main à Claude.")])
check("auto/demande : Claude reprend", len(l.submitted) == 1)

# Auto + vraie réponse : aucun relais
l = scenario("auto", "", "Il est midi.", "")
check("auto/réponse normale : affichée, pas de relais", l.messages == [("local", "Il est midi.")] and not l.submitted and not l.system)

# Mode « IA locale » seule : on montre et on propose, sans forcer
l = scenario("local", "refus", "Je ne peux pas.", H)
check("mode local : réponse montrée + proposition, pas de relais automatique", len(l.messages) == 1 and not l.submitted and l.system and l.system[0].startswith("↪"))

# @local explicite en mode auto : respecté
l = scenario("auto", "refus", "Je ne peux pas.", H, forced=True)
check("@local : pas de relais automatique", not l.submitted and len(l.messages) == 1)

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
