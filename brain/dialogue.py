"""Dialogue entre l'IA locale et Jimmy (Claude) : de vraies phrases, pas des lignes techniques.

- `message_to_jimmy` : l'IA locale écrit elle-même, avec son modèle, le message qu'elle envoie à Jimmy quand elle lui passe la main
  (ce que veut l'utilisateur, ce qu'elle a déjà fait, pourquoi). Si le moteur local est coupé ou trop lent, une phrase de secours
  est fabriquée à partir du même journal : le dialogue ne casse jamais.
- `humanize_step` : transforme une étape technique (« Commande · Voir la config ») en phrase à la première personne.
"""
from __future__ import annotations

import re
import threading

DEFAULT_NAME = "Aurélie"

_IMPERATIF = {
    "voir": "je regarde", "regarder": "je regarde", "repérer": "je repère", "lire": "je lis", "écrire": "j'écris", "tester": "je teste",
    "supprimer": "je supprime", "lancer": "je lance", "chercher": "je cherche", "vérifier": "je vérifie", "installer": "j'installe",
    "copier": "je copie", "lister": "je liste", "compiler": "je compile", "ouvrir": "j'ouvre", "afficher": "j'affiche", "créer": "je crée",
    "mettre": "je mets", "corriger": "je corrige", "appliquer": "j'applique", "attendre": "j'attends", "relancer": "je relance",
    "fabriquer": "je fabrique", "comparer": "je compare", "contrôler": "je contrôle", "publier": "je publie", "télécharger": "je télécharge",
    "construire": "je construis", "trouver": "je trouve", "récupérer": "je récupère", "nettoyer": "je nettoie", "préparer": "je prépare",
    "déployer": "je déploie", "sauvegarder": "je sauvegarde", "mesurer": "je mesure", "capturer": "je capture", "exécuter": "j'exécute",
    "analyser": "j'analyse", "ajouter": "j'ajoute", "modifier": "je modifie", "remplacer": "je remplace", "retirer": "je retire",
    "ranger": "je range", "chercher": "je cherche", "examiner": "j'examine", "inspecter": "j'inspecte", "démarrer": "je démarre",
}


def _cap(s: str) -> str:
    s = s.strip()
    return (s[:1].upper() + s[1:]) if s else s


def _end(s: str) -> str:
    s = s.strip()
    return s if not s or s[-1] in ".!?…:" else s + "."


def humanize_step(step: str) -> str:
    """« Lecture · je lis shop.php » -> « Je lis shop.php. » ; « Commande · Voir la config » -> « Je regarde la config. »"""
    step = (step or "").strip()
    if " · " not in step:
        return _end(_cap(step))
    kind, detail = (p.strip() for p in step.split(" · ", 1))
    low = detail.lower()
    if kind in ("Analyse", "Réflexion"):
        return _end(_cap(detail))
    if low.startswith(("je ", "j'", "j’")):
        return _end(_cap(detail))
    first, _, rest = detail.partition(" ")
    verb = _IMPERATIF.get(first.lower())
    if verb:
        return _end(_cap(f"{verb} {rest}".strip()))
    k = kind.lower()
    if k == "web":
        return _end(f"Je cherche « {detail} » sur Internet")
    if k == "page":
        return _end(f"Je lis la page {detail}")
    if k == "mémoire":
        return _end(f"Je regarde dans ma mémoire : {detail}")
    if k == "dossier":
        return _end(f"Je regarde le contenu du dossier {detail}")
    if k in ("lecture", "écriture", "modification"):
        return _end(f"{ {'lecture': 'Je lis', 'écriture': 'J’écris', 'modification': 'Je modifie'}[k] } {detail}")
    if k == "commande":
        return _end(f"Je lance : {detail}")
    if k == "résultat":
        return _end(f"J'ai obtenu : {detail}")
    if k == "relais":
        return _end(_cap(detail))
    if k == "ia locale":
        return _end(_cap(detail))
    return _end(_cap(f"{kind.lower()} : {detail}"))


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def fallback_message(user_text: str, journal: list, reason: str, name: str = DEFAULT_NAME) -> str:
    """Message de secours (sans modèle) : le même contenu, écrit comme on parle."""
    done = ""
    if journal:
        done = " J'ai déjà fait : " + " ; ".join(_clip(j, 90) for j in journal[-3:]) + "."
    why = {"demande": "ça dépasse mes moyens", "refus": "je n'y arrive pas", "indisponible": "mon moteur est éteint",
           "erreur": "j'ai planté"}.get(reason, "j'ai besoin de toi")
    return f"Jimmy, l'utilisateur demande : « {_clip(user_text, 220)} ».{done} Je te passe la main parce que {why}."


def _ask_model(engine, messages, timeout: float) -> str:
    box = {}

    def run() -> None:
        try:
            msg = engine.chat(messages, tools=None)
            box["text"] = (msg.get("content") or "").strip()
        except Exception:  # noqa: BLE001
            box["text"] = ""
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("text", "")


def message_to_jimmy(engine, user_text: str, journal: list, reason: str, name: str = DEFAULT_NAME, timeout: float = 14.0) -> str:
    """L'IA locale écrit à Jimmy. Renvoie toujours un texte (modèle, ou secours)."""
    backup = fallback_message(user_text, journal, reason, name)
    if engine is None:
        return backup
    done = "\n".join(f"- {_clip(j, 160)}" for j in (journal or [])[-6:]) or "(rien encore)"
    why = {"demande": "la tâche dépasse tes moyens", "refus": "tu n'as pas réussi", "indisponible": "ton moteur ne répond pas",
           "erreur": "tu as rencontré une erreur"}.get(reason, "tu as besoin de lui")
    system = (f"Tu es {name}, l'IA locale de l'utilisateur. Tu parles à Jimmy, l'assistant Claude, entre collègues, en français, naturel, "
              f"tutoiement. « je » = toi ({name}) : ne parle JAMAIS de {name} à la troisième personne, ne t'excuse pas, commence par « Jimmy, ». "
              "L'utilisateur est un tiers (« il »). Écris UN message de 2 à 3 phrases courtes : ce que veut l'utilisateur, ce que tu as déjà fait ou trouvé "
              "(résume, ne recopie pas), et pourquoi tu lui passes la main. Pas de liste, pas de titre, pas de guillemets autour du message.")
    user = f"Demande de l'utilisateur : {_clip(user_text, 500)}\nCe que tu as déjà fait :\n{done}\nTu lui passes la main parce que {why}."
    text = _ask_model(engine, [{"role": "system", "content": system}, {"role": "user", "content": user}], timeout)
    text = re.sub(r"^[\"«»\s]+|[\"«»\s]+$", "", text)
    from .agent import is_failure
    # Un vrai message commence par « Jimmy » (elle lui parle) ; un refus générique (« je ne peux pas aider ») est écarté.
    refus = (is_failure(text) and not text.lower().startswith("jimmy")) or "jimmy" not in text[:20].lower()
    if len(text) < 12 or len(text) > 900 or refus:
        return backup          # un refus (« je ne peux pas aider ») n'est pas un message pour Jimmy : phrase de secours
    return text
