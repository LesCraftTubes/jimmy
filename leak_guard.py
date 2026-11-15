"""Garde anti-fuites : refuse une publication qui contiendrait des données privées de l'auteur.

Lance avant chaque release (release.ps1 l'appelle) : python leak_guard.py
Regarde tout ce que Git publierait (fichiers suivis + nouveaux fichiers non ignorés) et échoue si elle trouve :
  - des fichiers de données (bases, index, packs, mémoire) ;
  - des adresses de réseau privé, des chemins de lecteur réseau, des noms de projets ou de serveurs privés ;
  - des secrets (clés, jetons, mots de passe).
Les mots interdits sont dans PRIVATE_WORDS : ajoute-y tout ce qui ne doit jamais apparaître dans le dépôt public.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Noms qui ne doivent jamais apparaître dans le dépôt public (insensible à la casse).
PRIVATE_WORDS = ["negan", "blackroast", "legendead", "beginith", "gunscarz", "evan", "ssh negan", "wiki_user"]
# Fichiers de données privés (jamais publiés, quel que soit leur contenu).
PRIVATE_FILES = re.compile(r"(\.db(-wal|-shm)?$|\.npy$|(^|/)chunks\.json$|(^|/)packs/|(^|/)private/|(^|/)brouillons/|"
                           r"(^|/)memoire|config\.json$|state\.json$|\.sqlite3?$|\.pem$|\.key$|id_(rsa|ed25519))", re.I)
PATTERNS = [
    (re.compile(r"\b(192\.168|10\.\d{1,3}|172\.(1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"), "adresse de réseau privé"),
    (re.compile(r"(?<![A-Za-z])[S-Z]:\\(home|srv|Users)\\", re.I), "chemin de lecteur réseau ou de dossier personnel"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{12,}|-----BEGIN [A-Z ]*PRIVATE"), "secret"),
    (re.compile(r"(password|passwd|mot de passe|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.I), "secret possible"),
]
# Fichiers où certains mots sont normaux (auteur du dépôt, licence...).
ALLOW = {
    "version.py": ["lescrafttubes"],
    "LICENSE": ["negan", "lescrafttubes"],
    "leak_guard.py": ["*"],          # ce fichier liste les mots interdits
    "CHANGELOG.md": [],
}
SELF = {"leak_guard.py"}


def publishable_files() -> list:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return [f for f in out.splitlines() if f]


def main() -> int:
    problems = []
    for rel in publishable_files():
        name = Path(rel).name
        if name in SELF:
            continue
        if PRIVATE_FILES.search(rel.replace("\\", "/")):
            problems.append(f"{rel} : fichier de données privé (ne doit pas être publié)")
            continue
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        allowed = ALLOW.get(name, [])
        for w in PRIVATE_WORDS:
            rx = re.compile(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", re.I)
            m = rx.search(text)
            if m and w not in allowed and "*" not in allowed:
                problems.append(f"{rel}:{text[:m.start()].count(chr(10)) + 1} : mot privé « {w} »")
        for rx, why in PATTERNS:
            m = rx.search(text)
            if m and m.group(0) == "10.255.255.255":
                continue          # astuce standard pour connaître sa propre adresse Wi-Fi (aucun paquet envoyé)
            if m and "*" not in allowed:
                line = text[:m.start()].count("\n") + 1
                problems.append(f"{rel}:{line} : {why}")
    if problems:
        print("GARDE ANTI-FUITES : publication REFUSÉE.")
        for p in problems[:60]:
            print("  -", p)
        return 1
    print("Garde anti-fuites : rien de privé dans ce qui sera publié.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
