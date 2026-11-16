"""Ce qui s'affiche dans la fenêtre SANS être dans le fichier de la discussion de Claude, gardé PAR DISCUSSION pour revenir à la réouverture :

- `image`  : une capture montrée dans la conversation (chemin, légende, qui l'a prise)
- `local`  : une réponse d'Aurélie (l'IA locale)
- `dialog` : un message entre Aurélie et Jimmy
- `xfer`   : un passage de la main (Aurélie -> Jimmy, Jimmy -> Aurélie)
- `feed`   : une ligne du fil d'activité du panneau de droite (ce que fait Aurélie : page ouverte, clic, capture...)
- `work`   : ce que fait Jimmy en direct (fichier lu, modifié, commande lancée, avec le détail)

Un fichier par discussion dans `<données>/extras/<id>.jsonl` (une ligne = un élément, horodaté). Tant que la discussion n'a pas encore
d'identifiant (premier message en cours), les éléments attendent en mémoire, puis `bind()` les range. Quand une discussion en remplace une
autre (reprise de contexte), `bind(new, old)` recopie l'historique : rien ne se perd. Aucun secret n'est stocké : seulement ce qui était déjà affiché.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from pathlib import Path

MAX_ITEMS = 700          # au-delà, les plus anciens sont retirés
_ID = re.compile(r"^[\w-]+$")
_lock = threading.RLock()
_pending: list = []      # éléments en attente d'un identifiant de discussion
_pending_frame: dict = {}


LOCAL_PREFIX = "aurelie-"      # discussion qui n'existe QUE avec Aurélie (Claude n'y est pas encore intervenu)


def new_local_id() -> str:
    import uuid
    return LOCAL_PREFIX + uuid.uuid4().hex[:12]


def is_local(sid) -> bool:
    return str(sid or "").startswith(LOCAL_PREFIX)


def local_sessions(limit: int = 40) -> list:
    """Les discussions menées seulement avec Aurélie : [(id, titre, heure de dernière activité)], les plus récentes d'abord."""
    out = []
    try:
        files = sorted(_dir().glob(LOCAL_PREFIX + "*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return []
    for f in files:
        title = ""
        for it in load(f.stem, kinds=("user",)):
            title = " ".join(str(it.get("text", "")).split())[:70]
            break
        out.append((f.stem, title or "Discussion avec Aurélie", f.stat().st_mtime))
    return out


def _dir() -> Path:
    from config import data_dir
    d = data_dir() / "extras"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(sid: str) -> Path:
    if not _ID.match(sid or ""):
        raise ValueError("identifiant de discussion invalide")
    return _dir() / f"{sid}.jsonl"


def _clip(v, n: int = 1200):
    return v[:n] if isinstance(v, str) else v


def add(sid: str | None, kind: str, **data) -> dict:
    """Garde un élément. `sid` vide = discussion pas encore créée : il attend (voir bind)."""
    item = {"ts": time.time(), "kind": kind, **{k: _clip(v) for k, v in data.items()}}
    with _lock:
        if sid and not _ID.match(sid):
            return item                      # identifiant invalide : on ignore (rien n'est écrit, rien n'attend)
        if not sid:
            _pending.append(item)
            del _pending[:-MAX_ITEMS]
            return item
        try:
            with open(_file(sid), "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return item


def drop_pending() -> None:
    """On change de discussion : ce qui attendait ne doit pas être rattaché à une autre."""
    with _lock:
        _pending.clear()
        _pending_frame.clear()


def load(sid: str | None, kinds=None) -> list:
    """Les éléments gardés, du plus ancien au plus récent (ceux de la discussion + ceux qui attendent encore, si c'est la discussion courante)."""
    out = []
    if sid and _ID.match(sid):
        try:
            with open(_file(sid), encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
    out.sort(key=lambda i: i.get("ts", 0))
    if kinds:
        out = [i for i in out if i.get("kind") in kinds]
    return out[-MAX_ITEMS:]


def bind(sid: str, old: str | None = None) -> None:
    """La discussion existe : range ce qui attendait, et recopie l'historique de l'ancienne discussion si celle-ci la remplace."""
    if not sid or not _ID.match(sid):
        return
    with _lock:
        moved = []
        if old and old != sid and _ID.match(old):
            moved = load(old)
            try:
                of = _file(old)
                if of.exists():
                    jpg = _dir() / f"{old}.jpg"
                    if jpg.exists() and not (_dir() / f"{sid}.jpg").exists():
                        jpg.replace(_dir() / f"{sid}.jpg")
                        mp = _dir() / f"{old}.frame.json"
                        if mp.exists():
                            mp.replace(_dir() / f"{sid}.frame.json")
            except OSError:
                pass
        items = moved + list(_pending)
        _pending.clear()
        if old and is_local(old):
            forget(old)               # la discussion avec Aurélie devient celle de Claude : un seul fil, rien en double
        if items:
            try:
                with open(_file(sid), "a", encoding="utf-8") as f:
                    for it in sorted(items, key=lambda i: i.get("ts", 0)):
                        f.write(json.dumps(it, ensure_ascii=False) + "\n")
            except OSError:
                pass
        if _pending_frame:
            save_frame(sid, **_pending_frame)
            _pending_frame.clear()
        trim(sid)


def trim(sid: str) -> None:
    items = load(sid)
    if len(items) < MAX_ITEMS:
        return
    try:
        with open(_file(sid), "w", encoding="utf-8") as f:
            for it in items[-MAX_ITEMS:]:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    except OSError:
        pass


def forget(sid: str) -> None:
    """La discussion est supprimée : ses éléments aussi (la corbeille de Jimmy garde la discussion elle-même)."""
    if not sid or not _ID.match(sid):
        return
    for suffix in (".jsonl", ".jpg", ".frame.json"):
        try:
            (_dir() / f"{sid}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


# ------------------------------------------------------------------ dernier rendu de l'écran en direct
def save_frame(sid: str | None, jpg: str, url: str = "", title: str = "", w: int = 0, h: int = 0) -> None:
    """Garde la dernière image affichée dans l'écran en direct (JPEG en base64)."""
    with _lock:
        if not sid or not _ID.match(sid):
            _pending_frame.clear()
            _pending_frame.update(jpg=jpg, url=url, title=title, w=w, h=h)
            return
        try:
            (_dir() / f"{sid}.jpg").write_bytes(base64.b64decode(jpg))
            (_dir() / f"{sid}.frame.json").write_text(json.dumps({"url": url, "title": title, "w": w, "h": h, "ts": time.time()}, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            pass


def load_frame(sid: str | None) -> dict | None:
    if not sid or not _ID.match(sid):
        return None
    try:
        meta = json.loads((_dir() / f"{sid}.frame.json").read_text(encoding="utf-8"))
        jpg = base64.b64encode((_dir() / f"{sid}.jpg").read_bytes()).decode("ascii")
    except (OSError, ValueError):
        return None
    return {"jpg": jpg, **meta}
