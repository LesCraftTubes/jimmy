"""Conversations de Claude Code : Jimmy lit les mêmes fichiers que `claude --resume`.

Chaque conversation est un fichier ~/.claude/projects/<dossier encodé>/<id>.jsonl, donc tout ce
qui est fait dans Jimmy se retrouve dans Claude Code, et inversement.
"""
import json
import re
import shutil
import time
from pathlib import Path

RESUME_MARK = "[Reprise de contexte"
_SKIP_PREFIXES = ("<command", "<local-command", "<system-reminder", "Caveat:", "[Request interrupted")


_TECH_TAGS = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout|local-command-caveat|"
    r"task-notification|ide_opened_file|ide_selection|user-prompt-submit-hook|bash-input|bash-stdout|bash-stderr)"
    r"(?:\s[^>]*)?>.*?</\1>", re.S)


def projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def project_dir(workdir: str) -> Path:
    return projects_root() / re.sub(r"[^A-Za-z0-9]", "-", str(Path(workdir).resolve()))


def _user_text(content, raw: bool = False) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Une liste avec des tool_result = retour d'outil, pas un message de l'utilisateur.
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return ""
        text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    else:
        return ""
    # Balises techniques collées dans le message (rappels système, notifications...) : jamais affichées.
    text = _TECH_TAGS.sub("", text.strip())
    text = re.sub(r"</?pasted_content[^>]*>", "", text).strip()
    if text.startswith(RESUME_MARK) and not raw:
        return "↺ Suite de la discussion."
    return "" if text.startswith(_SKIP_PREFIXES) else text


def _assistant_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
        ).strip()
    return ""


def _entries(path: Path):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("user", "assistant") or d.get("isMeta") or d.get("isSidechain"):
            continue
        yield d


def load_messages(workdir: str, session_id: str) -> list:
    """[(role, texte)] : les messages lisibles d'une conversation, réponses regroupées par tour."""
    out = []
    for d in _entries(project_dir(workdir) / f"{session_id}.jsonl"):
        content = (d.get("message") or {}).get("content")
        if d["type"] == "user":
            text = _user_text(content)
            if text:
                out.append(["user", text])
        else:
            text = _assistant_text(content)
            if not text:
                continue
            if out and out[-1][0] == "assistant":
                out[-1][1] += "\n\n" + text
            else:
                out.append(["assistant", text])
    return [tuple(m) for m in out]


def _clip(text: str, n: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


_NAME_IN_RESUME = re.compile(r"discussion « (.+?) »")
_GOAL_OLD = re.compile(r"Au départ, l'utilisateur voulait : (.+)")


def resume_info(text: str):
    """Message de reprise -> (nom d'origine ou None, but ou None). Gère l'ancien format (gros résumé) et le nouveau."""
    m = _NAME_IN_RESUME.search(text)
    g = re.search(r"But : (.+?)(?: Le détail est|\]|$)", text, re.S) or _GOAL_OLD.search(text)
    return (m.group(1).strip() if m else None), (g.group(1).strip() if g else None)


def _title(path: Path) -> str:
    """Titre tiré de la première vraie demande ; une reprise de contexte reprend le nom d'origine."""
    resume_goal = None
    for d in _entries(path):
        if d["type"] == "user":
            content = (d.get("message") or {}).get("content")
            raw = _user_text(content, raw=True)
            if raw.startswith(RESUME_MARK):
                name, goal = resume_info(raw)
                if name:
                    return _clip(name, 80)
                if goal:
                    return _clip(goal)      # ancien format : le but d'origine sert de titre
                continue
            text = _user_text(content)
            if text:
                return _clip(text)
    return _clip(resume_goal) if resume_goal else "(conversation vide)"


# ------------------------------------------------------------------ noms des discussions (durables)
def _names_path() -> Path:
    from config import data_dir
    return data_dir() / "session_names.json"


def load_names() -> dict:
    """{id: {"name": str, "manual": bool}} : survit aux redémarrages, aux reprises de contexte et aux mises à jour."""
    try:
        d = json.loads(_names_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_name(session_id: str, name: str, manual: bool = True) -> str:
    name = " ".join(str(name).split())[:80]
    if not session_id or not name:
        return ""
    names = load_names()
    names[session_id] = {"name": name, "manual": bool(manual)}
    try:
        _names_path().write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return name


def ensure_names(listed) -> None:
    """Enregistre un titre (tiré de la première demande) pour les discussions qui n'ont pas encore de nom :
    à partir de là il est durable, renommable, et Jimmy ne le change plus tout seul."""
    names = load_names()
    new = {sid: {"name": " ".join(title.split())[:80], "manual": False}
           for sid, title, _when in listed if sid not in names and title and title != "(conversation vide)"}
    if not new:
        return
    names.update(new)
    try:
        _names_path().write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def forget_name(session_id: str) -> None:
    names = load_names()
    if names.pop(session_id, None) is not None:
        try:
            _names_path().write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def display_name(workdir: str, session_id: str) -> str:
    """Nom affiché : celui enregistré (manuel ou hérité), sinon le titre tiré de la première demande."""
    n = load_names().get(session_id)
    if n and n.get("name"):
        return n["name"]
    path = project_dir(workdir) / f"{session_id}.jsonl"
    return _title(path) if path.exists() else "(conversation vide)"


def is_manual(session_id: str) -> bool:
    return bool((load_names().get(session_id) or {}).get("manual"))


# ------------------------------------------------------------------ corbeille (copie de sécurité)
def trash_dir() -> Path:
    from config import data_dir
    return data_dir() / "corbeille"


def purge_trash(days: int = 7) -> int:
    """Supprime de la corbeille ce qui a plus de `days` jours. Renvoie le nombre de fichiers retirés."""
    folder, n = trash_dir(), 0
    if not folder.is_dir():
        return 0
    limit = time.time() - max(1, days) * 86400
    for f in folder.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < limit:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n


def _owns(path: Path, session_id: str) -> bool:
    """Le fichier est bien celui de CETTE discussion : son nom ET les identifiants écrits dedans correspondent."""
    if path.stem != session_id or not path.is_file():
        return False
    seen = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"sessionId"' not in line:
                    continue
                try:
                    sid = json.loads(line).get("sessionId")
                except ValueError:
                    continue
                if sid and sid != session_id:
                    return False
                seen += 1
                if seen >= 30:
                    break
    except OSError:
        return False
    return True


def delete_session(workdir: str, session_id: str, trash: bool = True, days: int = 7) -> bool:
    """Supprime une conversation (aussi pour Claude Code : c'est le même fichier).

    Vérifie l'identifiant, garde une copie dans la corbeille de Jimmy (purgée après `days` jours),
    puis retire le fichier, son dossier lié, son nom enregistré et sa marque « pleine »."""
    if not re.fullmatch(r"[\w-]+", session_id or ""):
        return False
    folder = project_dir(workdir)
    path = folder / f"{session_id}.jsonl"
    if path.exists() and not _owns(path, session_id):
        return False
    if trash and path.exists():
        try:
            td = trash_dir()
            td.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, td / f"{session_id}.jsonl")
            (td / f"{session_id}.json").write_text(json.dumps(
                {"id": session_id, "name": load_names().get(session_id, {}).get("name") or _title(path),
                 "deleted": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False), encoding="utf-8")
            purge_trash(days)
        except OSError:
            return False      # pas de copie de sécurité : on ne supprime pas
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    side = folder / session_id   # sous-agents et fichiers liés à la conversation
    if side.is_dir():
        shutil.rmtree(side, ignore_errors=True)
    forget_name(session_id)
    unmark_full(session_id)
    return True


def list_sessions(workdir: str, limit: int = 60) -> list:
    """[(id, titre, date lisible)] des conversations Claude Code de ce dossier, plus récentes d'abord."""
    folder = project_dir(workdir)
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    names = load_names()
    out = []
    for f in files:
        stored = (names.get(f.stem) or {}).get("name")
        title = stored or _title(f)
        if title == "(conversation vide)":
            continue
        when = time.strftime("%d/%m %H:%M", time.localtime(f.stat().st_mtime))
        out.append((f.stem, title, when))
    return out


# ------------------------------------------------------------------ taille du contexte
def context_tokens(workdir: str, session_id: str) -> int:
    """Taille actuelle du contexte d'une conversation : lue dans le dernier message de Claude (usage)."""
    path = project_dir(workdir) / f"{session_id}.jsonl"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        u = (d.get("message") or {}).get("usage") or {}
        total = sum(int(u.get(k) or 0) for k in
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        if total:
            return total
    return 0


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _clean_name(name: str) -> str:
    return " ".join(str(name).replace("«", '"').replace("»", '"').replace("]", ")").split())


def mini_message(name: str, goal: str) -> str:
    """Seul message envoyé dans la nouvelle discussion : le nom d'origine, le but, et où est le détail (la mémoire)."""
    return (f'{RESUME_MARK} : discussion « {_clean_name(name)} » (reprise ici, l\'ancienne était pleine). '
            f'But : {_short(_clean_name(goal), 220)}. Le détail est dans la mémoire : '
            f'cherche avec jimmy_mem.py (search « {_clean_name(name)[:40]} »), sans relire l\'historique.]')


def real_messages(workdir: str, session_id: str) -> list:
    """Les messages lisibles SANS les messages de reprise (donc la vraie conversation)."""
    out = []
    for d in _entries(project_dir(workdir) / f"{session_id}.jsonl"):
        content = (d.get("message") or {}).get("content")
        if d["type"] == "user":
            raw = _user_text(content, raw=True)
            if raw and not raw.startswith(RESUME_MARK):
                out.append(("user", raw))
        else:
            text = _assistant_text(content)
            if text:
                out.append(("assistant", text))
    return out


def files_touched(workdir: str, session_id: str, limit: int = 12) -> list:
    """Fichiers modifiés par Claude dans cette discussion (Edit / Write / NotebookEdit), les plus récents en dernier."""
    seen = []
    for d in _entries(project_dir(workdir) / f"{session_id}.jsonl"):
        if d["type"] != "assistant":
            continue
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Edit", "Write", "NotebookEdit"):
                fp = (c.get("input") or {}).get("file_path") or (c.get("input") or {}).get("notebook_path")
                if fp:
                    fp = str(fp).replace("\\", "/")
                    if fp in seen:
                        seen.remove(fp)
                    seen.append(fp)
    return seen[-limit:]


def goal_of(workdir: str, session_id: str) -> str:
    msgs = real_messages(workdir, session_id)
    for role, text in msgs:
        if role == "user":
            return _short(text, 300)
    path = project_dir(workdir) / f"{session_id}.jsonl"
    for d in _entries(path):
        if d["type"] == "user":
            _n, g = resume_info(_user_text((d.get("message") or {}).get("content"), raw=True))
            if g:
                return _short(g, 300)
    return ""


def save_handoff_memory(workdir: str, session_id: str, name: str, stamp: str = "") -> int:
    """Enregistre l'essentiel d'une discussion dans la mémoire (notes courtes). Renvoie le nombre de notes écrites.

    Extraction automatique : le but, les fichiers touchés, la dernière demande et la dernière réponse (état d'avancement
    et suite). Les décisions importantes sont déjà enregistrées au fil de l'eau (consigne du prompt). Une note qui
    ressemble à un secret est ignorée."""
    try:
        import jimmy_mem
    except ImportError:
        return 0
    msgs = real_messages(workdir, session_id)
    if not msgs:
        return 0
    nm = _clean_name(name)[:60]
    notes = [(f"{nm} · but{stamp}", goal_of(workdir, session_id))]
    files = files_touched(workdir, session_id)
    if files:
        notes.append((f"{nm} · fichiers touchés{stamp}", " ; ".join(files)))
    last_user = next((t for r, t in reversed(msgs) if r == "user"), "")
    last_asst = next((t for r, t in reversed(msgs) if r == "assistant"), "")
    state = []
    if last_user:
        state.append("Dernière demande : " + _short(last_user, 250))
    if last_asst:
        state.append("Dernière réponse (état / suite) : " + _short(last_asst, 450))
    if state:
        notes.append((f"{nm} · état et suite{stamp}", " ".join(state)))
    saved = 0
    for sujet, contenu in notes:
        if not contenu:
            continue
        try:
            jimmy_mem.add_note(sujet, contenu, "Discussions", "discussion,reprise", 2)
            saved += 1
        except ValueError:
            continue     # ressemble à un secret : on ne l'enregistre pas
    return saved


def handoff(workdir: str, session_id: str, name: str, delete: bool = True, days: int = 7) -> dict:
    """Reprise de contexte : notes en mémoire, puis suppression de l'ancienne (copie en corbeille) ou simple marque « pleine ».

    Renvoie {"saved": nb de notes, "deleted": bool, "goal": but, "message": mini-message pour la nouvelle discussion}."""
    goal = goal_of(workdir, session_id)
    saved = save_handoff_memory(workdir, session_id, name)
    deleted = False
    if delete:
        deleted = delete_session(workdir, session_id, trash=True, days=days)
    if not deleted:
        mark_full(session_id)
    return {"saved": saved, "deleted": deleted, "goal": goal, "message": mini_message(name, goal)}


# ------------------------------------------------------------------ ménage des anciennes « Reprise de la discussion précédente »
def _scan(workdir: str) -> dict:
    """{id: infos} pour toutes les discussions du dossier (pas seulement les 60 de la liste)."""
    folder = project_dir(workdir)
    out = {}
    for f in folder.glob("*.jsonl"):
        first_raw, users, first_ts = "", [], ""
        for d in _entries(f):
            if not first_ts:
                first_ts = str(d.get("timestamp") or "")
            if d["type"] == "user":
                raw = _user_text((d.get("message") or {}).get("content"), raw=True)
                if raw:
                    first_raw = first_raw or raw
                    users.append(raw)
        out[f.stem] = {"id": f.stem, "path": f, "mtime": f.stat().st_mtime, "first": first_raw, "users": users,
                       "is_resume": first_raw.startswith(RESUME_MARK), "start": first_ts}
    return out


def _find_parent(r: dict, all_: dict):
    """Ancienne discussion dont une des dernières demandes est recopiée dans le résumé de la reprise `r`."""
    quotes = [q.strip().rstrip("…").strip() for q in re.findall(r"Utilisateur : (.+)", r["first"])]
    quotes = [q for q in quotes if len(q) > 12]
    if not quotes:
        return None
    best, score = None, 0
    for sid, c in all_.items():
        if sid == r["id"] or c["mtime"] > r["mtime"]:
            continue
        flat = [" ".join(u.split()) for u in c["users"] if not u.startswith(RESUME_MARK)]
        hits = sum(1 for q in quotes if any(u.startswith(q[:200]) or q[:200] in u for u in flat))
        if hits > score or (hits == score and hits and best and c["mtime"] > all_[best]["mtime"]):
            best, score = sid, hits
    return best if score else None


def plan_cleanup(workdir: str, protect_minutes: int = 15, protect_ids=()) -> dict:
    """Prépare le ménage sans rien modifier. {"keep": {id: nom}, "remove": [id...], "names": {id: nom}}.

    Chaque chaîne (ancienne -> reprise -> reprise...) ne garde que sa dernière discussion, avec le nom d'origine."""
    all_ = _scan(workdir)
    names = load_names()
    parent = {}
    for sid, r in all_.items():
        if r["is_resume"]:
            p = _find_parent(r, all_)
            if p:
                parent[sid] = p

    def root_of(sid):
        seen = set()
        while sid in parent and sid not in seen:
            seen.add(sid)
            sid = parent[sid]
        return sid

    def own_name(sid):
        n = (names.get(sid) or {}).get("name")
        if n:
            return n
        return _title(all_[sid]["path"])

    groups = {}
    for sid in all_:
        r = root_of(sid)
        if r != sid or any(root_of(x) == r and x != r for x in parent):
            groups.setdefault(r, set()).add(sid)
    now = time.time()
    keep, remove, newnames, rname = {}, [], {}, {}
    for root, members in groups.items():
        members = sorted(members, key=lambda s: all_[s]["mtime"])
        last = members[-1]
        base = names.get(root) or {}
        nm = base.get("name") or own_name(root)
        if nm in ("(conversation vide)",) or nm.startswith("↺"):
            nm = own_name(last)
        keep[last] = nm
        newnames[last] = {"name": nm, "manual": bool(base.get("manual"))}
        for s in members[:-1]:
            if s in protect_ids or now - all_[s]["mtime"] < protect_minutes * 60:
                continue          # jamais une discussion modifiée à l'instant (peut-être en cours d'utilisation)
            remove.append(s)
            rname[s] = nm
    # reprises sans parent retrouvé : on leur donne un titre tiré de leur contenu
    for sid, r in all_.items():
        if r["is_resume"] and sid not in keep and sid not in remove:
            nm = own_name(sid)
            if sid not in names and nm != "(conversation vide)":
                newnames[sid] = {"name": nm, "manual": False}
                keep[sid] = nm
    return {"keep": keep, "remove": remove, "names": newnames, "remove_names": rname}


def apply_cleanup(workdir: str, plan: dict, days: int = 14) -> dict:
    """Applique le ménage : mémoire d'abord, puis suppression (copie en corbeille), puis noms."""
    done = {"removed": 0, "saved": 0, "renamed": 0, "failed": 0}
    all_names = load_names()
    for sid in plan["remove"]:
        nm = (plan.get("remove_names") or {}).get(sid) or (all_names.get(sid) or {}).get("name") or display_name(workdir, sid)
        if nm.startswith("↺") or nm == "(conversation vide)":
            nm = "Discussion ancienne"
        when = time.strftime(" (%d/%m)", time.localtime((project_dir(workdir) / f"{sid}.jsonl").stat().st_mtime))
        done["saved"] += save_handoff_memory(workdir, sid, nm, stamp=when)
        if delete_session(workdir, sid, trash=True, days=days):
            done["removed"] += 1
        else:
            done["failed"] += 1
    for sid, meta in plan["names"].items():
        if (project_dir(workdir) / f"{sid}.jsonl").exists() and not (all_names.get(sid) or {}).get("manual"):
            set_name(sid, meta["name"], manual=meta.get("manual", False))
            done["renamed"] += 1
    return done


def _full_path() -> Path:
    from config import data_dir
    return data_dir() / "full_sessions.json"


def full_ids() -> set:
    """Conversations trop grosses pour continuer (affichées en gris dans la liste)."""
    try:
        return set(json.loads(_full_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def mark_full(session_id: str) -> None:
    ids = full_ids() | {session_id}
    try:
        _full_path().write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except OSError:
        pass


def unmark_full(session_id: str) -> None:
    ids = full_ids()
    if session_id in ids:
        ids.discard(session_id)
        try:
            _full_path().write_text(json.dumps(sorted(ids)), encoding="utf-8")
        except OSError:
            pass
