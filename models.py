"""Suivi du téléchargement du modèle vocal (faster-whisper) : le premier lancement est long, on l'affiche."""
import os
from pathlib import Path

EXPECTED_MB = {"tiny": 75, "base": 145, "small": 480, "medium": 1500, "large-v2": 3000, "large-v3": 3000}


def _hub() -> Path:
    base = os.environ.get("HF_HOME") or os.path.join(Path.home(), ".cache", "huggingface")
    return Path(os.environ.get("HF_HUB_CACHE") or Path(base) / "hub")


def whisper_progress(model: str):
    """(Mo déjà téléchargés, Mo attendus) ou None si le modèle est inconnu ou absent."""
    exp = EXPECTED_MB.get(model)
    folder = _hub() / f"models--Systran--faster-whisper-{model}"
    if not exp or not folder.is_dir():
        return None
    total = 0
    for f in (folder / "blobs").glob("*") if (folder / "blobs").is_dir() else []:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total / 1_000_000, float(exp)
