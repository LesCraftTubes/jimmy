"""Utilisation de l'abonnement Claude (Pro/Max) : limite de session (5 h) et limite hebdomadaire.

Interroge le même service que la commande /usage de Claude Code, avec la connexion déjà
enregistrée par Claude Code sur ce PC (~/.claude/.credentials.json). Rien n'est envoyé ailleurs.
Service non documenté officiellement et limité en nombre d'appels : on n'interroge pas plus
d'une fois par minute, on patiente quand il dit « trop de requêtes » (429), et on garde les
derniers chiffres connus (usage_cache.json) pour ne jamais afficher « — » sans raison.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from config import data_dir

URL = "https://api.anthropic.com/api/oauth/usage"
_DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MIN_INTERVAL = 60          # secondes entre deux appels au service
_CACHE = data_dir() / "usage_cache.json"
_last_call = 0.0
_blocked_until = 0.0       # après un 429 : pas d'appel avant cet instant


def _token():
    try:
        data = json.loads((Path.home() / ".claude" / ".credentials.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    oauth = data.get("claudeAiOauth") or {}
    return oauth.get("accessToken"), oauth.get("subscriptionType")


def _when(iso: str, with_day: bool = True) -> str:
    try:
        dt = datetime.fromisoformat(iso).astimezone()  # heure locale du PC
    except (TypeError, ValueError):
        return "?"
    if with_day and dt.date() != datetime.now().date():
        return f"{_DAYS[dt.weekday()]} {dt:%H:%M}"
    return f"{dt:%H:%M}"


def _parse(data: dict, plan) -> dict:
    """Si l'heure de reset est passée, les chiffres en cache sont périmés : on affiche 0 %."""
    out = {"plan": (plan or "").capitalize()}
    now = datetime.now().astimezone()
    for key, name in (("five_hour", "session"), ("seven_day", "week")):
        block = data.get(key) or {}
        if block.get("utilization") is None:
            continue
        pct, iso = float(block["utilization"]), block.get("resets_at")
        try:
            reset_dt = datetime.fromisoformat(iso).astimezone() if iso else None
        except (TypeError, ValueError):
            reset_dt = None
        if reset_dt is not None and reset_dt <= now:
            out[name] = (0.0, "")           # fenêtre déjà remise à zéro
            out["stale"] = True
        else:
            out[name] = (pct, _when(iso, True) if reset_dt is not None else "")
            if reset_dt is not None:
                nxt = reset_dt.timestamp()
                out["next_reset"] = min(out.get("next_reset", nxt), nxt)
    return out


def _cached(plan):
    """Derniers chiffres reçus (heures de reset recalculées en heure locale)."""
    try:
        data = json.loads(_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _parse(data, plan)


def fetch():
    """-> {"plan", "session": (pourcentage, reset), "week": (pourcentage, reset)} ou None."""
    global _last_call, _blocked_until
    token, plan = _token()
    if not token:
        return None
    now = time.time()
    if now < _blocked_until or now - _last_call < MIN_INTERVAL:
        return _cached(plan)       # cache déjà corrigé si un reset est passé (voir _parse)
    _last_call = now
    req = urllib.request.Request(
        URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "jimmy-assistant",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            try:
                wait = float(e.headers.get("Retry-After") or 300)
            except ValueError:
                wait = 300
            _blocked_until = now + max(60, wait)
        return _cached(plan)
    except Exception:  # noqa: BLE001
        return _cached(plan)
    try:
        _CACHE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return _parse(data, plan)
