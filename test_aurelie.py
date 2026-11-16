"""Tests : « Hey Aurélie » + sa voix, migration des réglages (autonomie), recherche de fichiers de l'IA locale. Lancer : python -W ignore test_aurelie.py"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv[:1])
fails = []


def check(name, cond):
    print(("OK   " if cond else "ECHEC ") + name)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- « Hey Aurélie » ou « Hey Jimmy » : le micro sait à qui tu parles
from listener import Listener

words = ["hey jimmy", "hey aurélie", "aurélie"]
check("« Hey Aurélie, cherche... » -> l'IA locale", Listener._wake_kind("Hey Aurélie, cherche la météo", words) == "local")
check("« Aurélie cherche... » (sans hey) -> l'IA locale", Listener._wake_kind("Aurélie cherche la météo", words) == "local")
check("« Hey Jimmy, ... » -> Claude", Listener._wake_kind("Hey Jimmy, refais la page", words) == "claude")

# ---------------------------------------------------------------- la phrase part vers la bonne IA, avec un point final
import window as W

sent = []


def heard(last_wake, local_on=True):
    me = SimpleNamespace(input=SimpleNamespace(end_preview=lambda: None), cfg=SimpleNamespace(get=lambda k, d=None: {"local_enabled": local_on}.get(k, d)),
                         listener=SimpleNamespace(last_wake=last_wake, last_followup=False), btn_dict=SimpleNamespace(isChecked=lambda: False),
                         bridge=SimpleNamespace(pending_tools=[]), submit=lambda t, followup=False: sent.append(t))
    W.JimmyWindow.on_heard(me, "cherche la météo de demain")
    return me


me = heard("local")
check("Hey Aurélie : la phrase part en @local avec un point final", sent[-1] == "@local cherche la météo de demain.")
check("le mot d'éveil est oublié après usage (le suivant repart normalement)", me.listener.last_wake == "")
heard("claude")
check("Hey Jimmy : pas de @local", sent[-1] == "cherche la météo de demain.")
heard("local", local_on=False)
check("IA locale coupée : « Hey Aurélie » part chez Claude, sans @local", sent[-1] == "cherche la météo de demain.")

# ---------------------------------------------------------------- la voix d'Aurélie, seulement pour sa réplique
log = SimpleNamespace(spoken=[], live=0, ended=[], finished=0, states=[])


def local_reply(text, handoff="", voice_on=True, name="Aurélie", voice="Éloïse"):
    log.spoken.clear()
    log.live = log.finished = 0
    sp = SimpleNamespace(voice_override=None, speak=lambda t: log.spoken.append(t))
    chat = SimpleNamespace(next_label=None, begin_live=lambda: setattr(log, "live", log.live + 1))
    me = SimpleNamespace(
        thinking=True, _local_reason="", _local_forced=False, _last_reply="", _force_claude=False, _local_ctx=[], _local_last_q="q", _relay_msg="",
        _remote_turn=False, _live_text=None, busy=False, speaking=False, speaker=sp, chat=chat, _HANDOFF_WHY=W.JimmyWindow._HANDOFF_WHY,
        btn_voice=SimpleNamespace(isChecked=lambda: voice_on), listener=SimpleNamespace(pause=lambda: None),
        cfg=SimpleNamespace(get=lambda k, d=None: {"local_voice": voice, "local_name": name}.get(k, d)),
        _route=lambda: "auto", _remote_emit=lambda *_a: None, _bump_local=lambda k: None, _local_name=lambda: name,
        add_message=lambda r, t: log.ended.append((r, t)), add_system=lambda t: None, add_dialog=lambda f, t, x: None,
        set_state=lambda s: log.states.append(s), _finish=lambda: setattr(log, "finished", log.finished + 1), submit=lambda *a, **k: None)
    W.JimmyWindow._on_local_reply(me, text, handoff)
    return me


me = local_reply("Il fera 14 degrés demain.")
check("Aurélie PARLE avec sa voix (Éloïse)", me.speaker.voice_override == "Éloïse" and log.spoken == ["Il fera 14 degrés demain."])
check("le texte s'écrit au rythme de la voix, étiqueté AURÉLIE · IA LOCALE", log.live == 1 and "AURÉLIE" in me.chat.next_label[0])
check("Jimmy ne reprend pas la parole tant qu'elle parle", log.finished == 0 and me.speaking and "speaking" in log.states)
done = SimpleNamespace(speaker=me.speaker, _live_text="x", chat=SimpleNamespace(end_live=lambda t: None), _finish=lambda: None)
W.JimmyWindow._on_speech_done(done)
check("après sa réplique, la voix de Jimmy est rétablie", me.speaker.voice_override is None)
me = local_reply("Il fera 14 degrés demain.", voice_on=False)
check("voix coupée : le texte s'affiche, personne ne parle", log.spoken == [] and log.ended == [("local", "Il fera 14 degrés demain.")] and me.speaker.voice_override is None)
me = local_reply("Je te passe la main.", handoff="Demande...")
check("quand elle passe la main à Jimmy, elle ne parle pas à voix haute", log.spoken == [])

# ---------------------------------------------------------------- migration des réglages d'un Jimmy déjà installé
import config

tmp = Path(tempfile.mkdtemp(prefix="jcfg_"))
(tmp / "config.json").write_text(json.dumps({"permission_mode": "acceptEdits", "wake_words": ["hey jimmy"], "model": "sonnet"}), encoding="utf-8")
config.data_dir = lambda: tmp
c = config.Config.load()
check("autonomie : acceptEdits (fenêtres + bip) devient « aucune demande »", c.get("permission_mode") == "bypassPermissions")
check("« Hey Aurélie » ajouté aux mots d'éveil, « Hey Jimmy » gardé", "hey aurélie" in c.get("wake_words") and "hey jimmy" in c.get("wake_words"))
check("les autres réglages ne bougent pas", c.get("model") == "sonnet")
c.set("permission_mode", "acceptEdits")                       # l'utilisateur redécide plus tard : la migration ne revient pas
c2 = config.Config.load()
check("la migration ne se rejoue pas (ton choix est respecté ensuite)", c2.get("permission_mode") == "acceptEdits" and c2.get("wake_words").count("hey aurélie") == 1)

# ---------------------------------------------------------------- l'IA locale cherche des fichiers (gratuit)
from brain import tools as T

work = Path(tempfile.mkdtemp(prefix="jfind_"))
(work / "site").mkdir()
(work / "site" / "shop.php").write_text("<?php\n$prix = 12;\n// boutique\n", encoding="utf-8")
(work / "site" / "notes.md").write_text("liste des boss : Garl, Malakor\n", encoding="utf-8")
(work / ".git").mkdir()
(work / ".git" / "shop.php").write_text("ne pas lister", encoding="utf-8")
(work / "mots.env").write_text("TOKEN=abc", encoding="utf-8")


class Cfg(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


reg = T.base_registry()
ctx = T.Context(cfg=Cfg(workdir=str(work)), user_text="")
r = reg.call("chercher_fichiers", {"motif": "shop"}, ctx)
check("chercher_fichiers : trouve shop.php (nom partiel)", "site" in r and "shop.php" in r)
check("chercher_fichiers : ignore le dossier .git", ".git" not in r.replace("[", ""))
check("chercher_fichiers : joker *.md", "notes.md" in reg.call("chercher_fichiers", {"motif": "*.md"}, ctx))
r = reg.call("chercher_texte", {"texte": "malakor"}, ctx)
check("chercher_texte : trouve « Malakor » avec fichier et ligne", "notes.md:1" in r)
check("chercher_texte : ne lit pas les fichiers de secrets", "introuvable" in reg.call("chercher_texte", {"texte": "abc"}, ctx))
check("ces deux outils marchent aussi en lecture seule (demande de Jimmy)", "shop.php" in T.base_registry().call("chercher_fichiers", {"motif": "shop"}, T.Context(cfg=Cfg(workdir=str(work)), user_text="")))
check("recherche vide : message clair", "vide" in reg.call("chercher_texte", {"texte": " "}, ctx))

print("\nRESULTAT :", "TOUT EST OK" if not fails else f"{len(fails)} ECHEC(S) : {fails}")
sys.exit(1 if fails else 0)
