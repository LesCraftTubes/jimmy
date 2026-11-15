"""Packs de connaissances : ce qu'une IA locale sait d'un projet précis, et les outils propres à ce projet.

Un pack est un dossier dans le dossier de données de l'utilisateur (%APPDATA%\\Jimmy\\packs\\<nom>), JAMAIS dans le
programme ni dans le dépôt public :

    pack.json     {"name", "title", "description", "always": ["docs/regles.md"], "keywords": ["skript", ...]}
    docs/*.md     guides ; ceux listés dans "always" sont donnés au modèle à chaque demande qui concerne le pack
    index/        chunks.json + emb.npy : morceaux de fichiers retrouvés par le sens (facultatif)
    tools.py      def register(registry, pack): ajoute des outils (facultatif)

Chacun peut fabriquer le sien (son serveur, son site, son jeu).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

from config import data_dir


def packs_dirs() -> list:
    dirs = [data_dir() / "packs"]
    appdata = Path(os.environ.get("APPDATA") or Path.home()) / "Jimmy" / "packs"
    if appdata not in dirs:
        dirs.append(appdata)
    return [d for d in dirs if d.is_dir()]


class Pack:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.meta = json.loads((path / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.meta = {}
        self.name = self.meta.get("name") or path.name
        self.title = self.meta.get("title") or self.name
        self._chunks = None
        self._emb = None

    # ---------------------------------------------------------------- pertinence
    def concerns(self, text: str) -> bool:
        """Le pack est-il concerné par cette demande ? (mots-clés du pack ; sans mots-clés : toujours)."""
        kws = self.meta.get("keywords") or []
        if not kws:
            return True
        low = text.lower()
        return any(re.search(r"(?<!\w)" + re.escape(k.lower()), low) for k in kws)

    def rules(self) -> str:
        parts = []
        for rel in self.meta.get("always") or []:
            f = self.path / rel
            if f.is_file():
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(parts)

    # ---------------------------------------------------------------- recherche par le sens
    def _load_index(self) -> bool:
        if self._chunks is not None:
            return bool(self._chunks)
        self._chunks = []
        folder = self.path / "index"
        try:
            import numpy as np
            self._chunks = json.loads((folder / "chunks.json").read_text(encoding="utf-8"))
            self._emb = np.load(folder / "emb.npy")
        except Exception:  # noqa: BLE001
            self._chunks = []
        return bool(self._chunks)

    def retrieve(self, engine, query: str, k: int = 5) -> list:
        """Les k morceaux les plus proches de la demande : [(score, {"path", "title", "text"})]."""
        if not self._load_index() or not engine or not engine.embed_model:
            return []
        import numpy as np
        try:
            q = np.array(engine.embed(["search_query: " + query])[0], dtype=np.float32)
        except Exception:  # noqa: BLE001
            return []
        q /= (np.linalg.norm(q) + 1e-9)
        scores = self._emb @ q
        return [(float(scores[i]), self._chunks[i]) for i in np.argsort(-scores)[:k]]

    # ---------------------------------------------------------------- outils du pack
    def register_tools(self, registry) -> None:
        f = self.path / (self.meta.get("tools") or "tools.py")
        if not f.is_file():
            return
        spec = importlib.util.spec_from_file_location(f"jimmy_pack_{self.name}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            mod.register(registry, self)


def load_all(cfg=None) -> list:
    off = set((cfg.get("packs_disabled") or []) if cfg else [])
    out, seen = [], set()
    for d in packs_dirs():
        for p in sorted(d.iterdir()):
            if p.is_dir() and (p / "pack.json").is_file() and p.name not in seen and p.name not in off:
                seen.add(p.name)
                out.append(Pack(p))
    return out
