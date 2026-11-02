"""Conversations de Claude Code : Jimmy lit les mêmes fichiers que `claude --resume`.

Chaque conversation est un fichier ~/.claude/projects/<dossier encodé>/<id>.jsonl, donc tout ce
qui est fait dans Jimmy se retrouve dans Claude Code, et inversement.
"""
import json
import re
import shutil
import time
from pathlib import Path

_SKIP_PREFIXES = ("<command", "<local-command", "<system-reminder", "Caveat:", "[Request interrupted")


_TECH_TAGS = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout|local-command-caveat|"
    r"task-notification|ide_opened_file|ide_selection|user-prompt-submit-hook|bash-input|bash-stdout|bash-stderr)"
    r"(?:\s[^>]*)?>.*?</\1>", re.S)


def projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def project_dir(workdir: str) -> Path:
    return projects_root() / re.sub(r"[^A-Za-z0-9]", "-", str(Path(workdir).resolve()))


def _user_text(content) -> str:
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
    if text.startswith("[Reprise de contexte"):
        return "↺ Reprise de la discussion précédente."
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


def _title(path: Path) -> str:
    for d in _entries(path):
        if d["type"] == "user":
            text = _user_text((d.get("message") or {}).get("content"))
            if text:
                text = " ".join(text.split())
                return text if len(text) <= 60 else text[:57] + "…"
    return "(conversation vide)"


def delete_session(workdir: str, session_id: str) -> bool:
    """Supprime une conversation (aussi pour Claude Code : c'est le même fichier)."""
    if not re.fullmatch(r"[\w-]+", session_id or ""):
        return False
    folder = project_dir(workdir)
    try:
        (folder / f"{session_id}.jsonl").unlink(missing_ok=True)
    except OSError:
        return False
    side = folder / session_id   # sous-agents et fichiers liés à la conversation
    if side.is_dir():
        shutil.rmtree(side, ignore_errors=True)
    return True


def list_sessions(workdir: str, limit: int = 60) -> list:
    """[(id, titre, date lisible)] des conversations Claude Code de ce dossier, plus récentes d'abord."""
    folder = project_dir(workdir)
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        title = _title(f)
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


def recap(workdir: str, session_id: str, last: int = 6) -> str:
    """Petit résumé pour repartir dans une nouvelle discussion : le but de départ + les derniers échanges."""
    msgs = load_messages(workdir, session_id)
    if not msgs:
        return ""
    tail = msgs[-last:]
    lines = ["[Reprise de contexte : la discussion précédente était presque pleine (limite de taille). "
             "Voici l'essentiel, ne relis pas tout l'historique."]
    if msgs[0][0] == "user" and tail[0] is not msgs[0]:
        lines.append("Au départ, l'utilisateur voulait : " + _short(msgs[0][1], 300))
    lines.append("Derniers échanges :")
    for role, text in tail:
        lines.append(("Utilisateur : " if role == "user" else "Jimmy : ") + _short(text, 700))
    lines.append("Continue à partir de là ; pour un détail, regarde les fichiers du projet ou demande-moi.]")
    return "\n".join(lines)


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
