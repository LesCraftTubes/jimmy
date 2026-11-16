"""Aurélie relit les fichiers que Jimmy vient de modifier : contrôles de SYNTAXE et recherche de SECRETS écrits en dur.

Tout est fait par le code (aucun token, aucun modèle) et en lecture seule :
- Python : compilation (sans exécuter) ; JSON : lecture ; JavaScript : `node --check` si Node est installé ;
- HTML : balises jamais fermées ou fermées sans avoir été ouvertes ; CSS : accolades et guillemets équilibrés ;
- tous les textes : mot de passe, jeton, clé d'API ou clé privée écrits en clair dans le fichier (la valeur n'est JAMAIS recopiée, seulement la ligne).
Les fichiers qui s'appellent comme un secret (.env, clés, config.php...) ne sont pas lus du tout.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 1_500_000
_SECRET_NAME = re.compile(r"(\.env\b|\.pem$|\.key$|\.ppk$|id_rsa|id_ed25519|credentials|secret|passw|token|\.kdbx|config\.php|wp-config)", re.I)
_SECRET_LINE = [
    (re.compile(r"""(?i)(?<![A-Za-z0-9])(pass(?:word|wd)?|pwd|secret|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token)\s*[=:]\s*(['"])(?!\s*\2)([^'"\s$%{][^'"]{5,})\2"""), "mot de passe, jeton ou clé écrit en clair"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "clé privée"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "clé d'accès AWS"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "jeton GitHub"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"), "clé d'API"),
]
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_SKIP_HTML = {"script", "style"}


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for open_tag, line in self.stack[i + 1:]:
                    if open_tag not in ("p", "li", "td", "tr", "th", "dt", "dd", "option", "tbody", "thead"):      # fermetures facultatives en HTML
                        self.problems.append(f"balise <{open_tag}> ouverte ligne {line} jamais fermée")
                del self.stack[i:]
                return
        self.problems.append(f"</{tag}> ligne {self.getpos()[0]} ferme une balise qui n'a pas été ouverte")


def _syntax(path: Path, text: str) -> list:
    ext = path.suffix.lower()
    out = []
    if ext == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as e:
            out.append(f"erreur de syntaxe Python ligne {e.lineno} : {e.msg}")
    elif ext == ".json":
        try:
            json.loads(text)
        except ValueError as e:
            out.append(f"JSON invalide : {e}")
    elif ext in (".js", ".mjs", ".cjs"):
        node = shutil.which("node")
        if node:
            try:
                r = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode != 0:
                    msg = [l for l in (r.stderr or "").splitlines() if l.strip()]
                    out.append("erreur de syntaxe JavaScript : " + " ".join(msg[:3])[:240])
            except (OSError, subprocess.SubprocessError):
                pass
    elif ext in (".html", ".htm"):
        body = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", "", text)           # le contenu des scripts n'est pas du HTML
        body = re.sub(r"(?s)<!--.*?-->", "", body)
        p = _Tags()
        try:
            p.feed(body)
            p.close()
        except Exception:  # noqa: BLE001
            return out
        out += p.problems[:4]
        out += [f"balise <{t}> ouverte ligne {ln} jamais fermée" for t, ln in p.stack if t not in ("html", "body", "p", "li")][:3]
    elif ext in (".css", ".scss"):
        clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        clean = re.sub(r"""(["'])(?:\\.|(?!\1).)*\1""", "", clean)
        if clean.count("{") != clean.count("}"):
            out.append(f"accolades déséquilibrées ({clean.count('{')} ouvrantes, {clean.count('}')} fermantes)")
    elif ext == ".php":
        php = shutil.which("php")
        if php:
            try:
                r = subprocess.run([php, "-l", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode != 0:
                    out.append("erreur PHP : " + " ".join((r.stdout or r.stderr).split())[:240])
            except (OSError, subprocess.SubprocessError):
                pass
    return out


def _secrets(text: str) -> list:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000:
            continue
        for rx, what in _SECRET_LINE:
            if rx.search(line):
                found.append(f"{what} ligne {n}")
                break
        if len(found) >= 4:
            break
    return found


def check_file(path: str) -> dict:
    """-> {"file", "ok", "problems": [...], "skipped": raison ou ""} (jamais d'exception, jamais de valeur secrète recopiée)."""
    p = Path(str(path))
    res = {"file": p.name, "path": str(p), "ok": True, "problems": [], "skipped": ""}
    if _SECRET_NAME.search(p.name):
        res["skipped"] = "fichier de secrets : non lu"
        return res
    try:
        if not p.is_file():
            res["skipped"] = "fichier introuvable (supprimé ou sur un autre disque)"
            return res
        if p.stat().st_size > MAX_BYTES:
            res["skipped"] = "fichier trop gros"
            return res
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        res["skipped"] = f"illisible : {e}"
        return res
    if "\x00" in text[:2000]:
        res["skipped"] = "fichier binaire"
        return res
    res["problems"] = _syntax(p, text) + [f"SECRET POSSIBLE : {s}" for s in _secrets(text)]
    res["ok"] = not res["problems"]
    return res


def check_files(paths) -> list:
    seen, out = set(), []
    for x in paths:
        if x in seen:
            continue
        seen.add(x)
        out.append(check_file(x))
    return out


def summary(results: list) -> str:
    """Une phrase par fichier à problème, ou une phrase si tout est bon."""
    done = [r for r in results if not r["skipped"]]
    bad = [r for r in done if not r["ok"]]
    skipped = [r for r in results if r["skipped"]]
    if not results:
        return "aucun fichier à relire"
    parts = []
    if bad:
        parts.append("; ".join(f"{r['file']} : " + " / ".join(r["problems"][:3]) for r in bad))
    if done and not bad:
        parts.append(f"{len(done)} fichier(s) relu(s), aucun problème de syntaxe ni de secret écrit en clair")
    elif done and bad:
        parts.append(f"les {len(done) - len(bad)} autre(s) fichier(s) sont corrects")
    if skipped:
        parts.append("non lus : " + ", ".join(f"{r['file']} ({r['skipped']})" for r in skipped[:3]))
    return " ; ".join(parts)
