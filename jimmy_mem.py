"""Mémoire persistante de Jimmy : petites notes dans memoire.db (SQLite + recherche plein texte FTS5).

Utilisation en ligne de commande (réponses très courtes, pour consommer peu de tokens) :
  jimmy_mem.py add "sujet" "contenu court" [--projet X] [--tags a,b] [--imp 1|2|3]
  jimmy_mem.py search "mots"          -> #id [projet] sujet : début du contenu
  jimmy_mem.py get 12                 -> la note entière
  jimmy_mem.py list [--projet X]      -> les dernières notes (titres seulement)
  jimmy_mem.py forget 12              -> supprime la note

Le fichier est dans %APPDATA%\\Jimmy\\memoire.db. Jamais de mot de passe, clé, jeton ni donnée personnelle :
`add` refuse ce qui y ressemble. Une note avec le même projet et le même sujet est mise à jour (pas de doublon).
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

SNIPPET = 110

# Ce qui ressemble à un secret : refusé à l'enregistrement.
_SECRET = re.compile(
    r"((mot de passe|password|passwd|mdp|api[_ -]?key|secret|token|jeton)\s*(est|=|:)\s*\S{4,}"
    r"|bearer\s+\S{8,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}"
    r"|-----BEGIN [A-Z ]*PRIVATE|[A-Fa-f0-9]{32,})", re.I)


def db_path() -> Path:
    base = os.environ.get("JIMMY_MEM_DIR") or (Path(os.environ.get("APPDATA") or Path.home()) / "Jimmy")
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    return base / "memoire.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            projet TEXT NOT NULL DEFAULT '',
            sujet TEXT NOT NULL,
            contenu TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            importance INTEGER NOT NULL DEFAULT 2
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            projet, sujet, contenu, tags,
            content='notes', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, projet, sujet, contenu, tags)
            VALUES (new.id, new.projet, new.sujet, new.contenu, new.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, projet, sujet, contenu, tags)
            VALUES ('delete', old.id, old.projet, old.sujet, old.contenu, old.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, projet, sujet, contenu, tags)
            VALUES ('delete', old.id, old.projet, old.sujet, old.contenu, old.tags);
            INSERT INTO notes_fts(rowid, projet, sujet, contenu, tags)
            VALUES (new.id, new.projet, new.sujet, new.contenu, new.tags);
        END;
    """)
    return con


def add_note(sujet: str, contenu: str, projet: str = "", tags: str = "", importance: int = 2) -> int:
    """Ajoute (ou met à jour si même projet + même sujet) une note. Renvoie son id. ValueError si secret."""
    sujet, contenu = " ".join(sujet.split()), contenu.strip()
    projet, tags = projet.strip(), tags.strip()
    if not sujet or not contenu:
        raise ValueError("sujet et contenu obligatoires")
    if _SECRET.search(f"{sujet} {contenu} {tags}"):
        raise ValueError("refusé : ça ressemble à un secret (mot de passe, clé, jeton). Pas de secret dans la mémoire.")
    importance = max(1, min(3, int(importance)))
    now = time.strftime("%Y-%m-%d")
    with connect() as con:
        row = con.execute("SELECT id FROM notes WHERE projet=? AND sujet=?", (projet, sujet)).fetchone()
        if row:
            con.execute("UPDATE notes SET date=?, contenu=?, tags=?, importance=? WHERE id=?",
                        (now, contenu, tags, importance, row["id"]))
            return row["id"]
        cur = con.execute(
            "INSERT INTO notes(date, projet, sujet, contenu, tags, importance) VALUES (?,?,?,?,?,?)",
            (now, projet, sujet, contenu, tags, importance))
        return cur.lastrowid


def _short(r: sqlite3.Row) -> str:
    text = " ".join(r["contenu"].split())
    if len(text) > SNIPPET:
        text = text[:SNIPPET].rstrip() + "…"
    proj = f"[{r['projet']}] " if r["projet"] else ""
    return f"#{r['id']} {proj}{r['sujet']} : {text}"


def search(query: str, limit: int = 8) -> list:
    words = re.findall(r"\w+", query, re.U)
    if not words:
        return []
    match = " OR ".join(f'"{w}"*' for w in words)
    with connect() as con:
        return con.execute(
            "SELECT n.* FROM notes_fts f JOIN notes n ON n.id=f.rowid WHERE notes_fts MATCH ? "
            "ORDER BY n.importance DESC, bm25(notes_fts) LIMIT ?", (match, limit)).fetchall()


def get(note_id: int):
    with connect() as con:
        return con.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()


def list_notes(projet: str = "", limit: int = 20) -> list:
    with connect() as con:
        if projet:
            return con.execute("SELECT * FROM notes WHERE projet=? COLLATE NOCASE ORDER BY importance DESC, id DESC LIMIT ?",
                               (projet, limit)).fetchall()
        return con.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def forget(note_id: int) -> bool:
    with connect() as con:
        return con.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount > 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="jimmy_mem.py", description="Mémoire de Jimmy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("sujet")
    a.add_argument("contenu")
    a.add_argument("--projet", default="")
    a.add_argument("--tags", default="")
    a.add_argument("--imp", type=int, default=2)
    s = sub.add_parser("search")
    s.add_argument("mots", nargs="+")
    s.add_argument("-n", type=int, default=8)
    g = sub.add_parser("get")
    g.add_argument("id", type=int)
    li = sub.add_parser("list")
    li.add_argument("--projet", default="")
    li.add_argument("-n", type=int, default=20)
    f = sub.add_parser("forget")
    f.add_argument("id", type=int)
    args = ap.parse_args(argv)

    if args.cmd == "add":
        try:
            nid = add_note(args.sujet, args.contenu, args.projet, args.tags, args.imp)
        except ValueError as e:
            print(e)
            return 1
        print(f"ok #{nid}")
    elif args.cmd == "search":
        rows = search(" ".join(args.mots), args.n)
        print("\n".join(_short(r) for r in rows) if rows else "rien")
    elif args.cmd == "get":
        r = get(args.id)
        if not r:
            print("introuvable")
            return 1
        print(f"#{r['id']} {r['date']} [{r['projet']}] {r['sujet']} (importance {r['importance']}, tags: {r['tags']})\n{r['contenu']}")
    elif args.cmd == "list":
        rows = list_notes(args.projet, args.n)
        print("\n".join(f"#{r['id']} [{r['projet']}] {r['sujet']}" for r in rows) if rows else "rien")
    elif args.cmd == "forget":
        print("supprimé" if forget(args.id) else "introuvable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
