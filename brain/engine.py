"""Connexion à un moteur d'IA locale par son API compatible OpenAI (LM Studio, Bionic, Ollama, llama.cpp).

Aucune dépendance : urllib seulement. Rien n'est envoyé sur Internet : l'adresse est toujours locale
(ou celle que l'utilisateur a choisie dans les réglages).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

NOWIN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
# Ports habituels : LM Studio / Bionic (1234, parfois 1235), Ollama (11434), llama.cpp (8080).
CANDIDATES = (1234, 1235, 11434, 8080, 1236)
EMBED_HINTS = ("embed", "nomic", "bge", "e5", "gte")


class LocalError(Exception):
    """Le moteur local n'a pas répondu comme attendu (message montrable à l'utilisateur)."""


def _get(url: str, timeout: float = 2.5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _post(url: str, body: dict, timeout: float = 900):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise LocalError(f"le moteur local a refusé la demande ({e.code}) : {detail}") from e
    except (urllib.error.URLError, OSError) as e:
        raise LocalError(f"moteur local injoignable ({e})") from e


def list_models(base: str) -> list:
    try:
        return [m.get("id", "") for m in _get(base.rstrip("/") + "/models").get("data", [])]
    except Exception:  # noqa: BLE001
        return []


def is_embedding(model_id: str) -> bool:
    low = model_id.lower()
    return any(h in low for h in EMBED_HINTS)


def discover(cfg=None) -> dict:
    """Cherche un moteur local qui répond. -> {"base": url ou "", "models": [...], "chat": id, "embed": id}."""
    urls = []
    custom = str(cfg.get("local_url") or "").strip() if cfg else ""
    if custom:
        urls.append(custom.rstrip("/"))
    urls += [f"http://127.0.0.1:{p}/v1" for p in CANDIDATES]
    for base in urls:
        models = list_models(base)
        if not models:
            continue
        want = str(cfg.get("local_model") or "") if cfg else ""
        chats = [m for m in models if not is_embedding(m)]
        embeds = [m for m in models if is_embedding(m)]
        chat = want if want in models else (chats[0] if chats else "")
        return {"base": base, "models": models, "chat": chat, "embed": embeds[0] if embeds else ""}
    return {"base": "", "models": [], "chat": "", "embed": ""}


# ------------------------------------------------------------------ moteurs installés sur le PC
def lms_cli() -> str:
    """Chemin de la commande « lms » (LM Studio / Bionic) si elle existe."""
    p = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
    return str(p) if p.exists() else ""


def ollama_cli() -> str:
    import shutil
    return shutil.which("ollama") or ""


def installed_engines() -> list:
    out = []
    if lms_cli():
        out.append("LM Studio / Bionic")
    if ollama_cli():
        out.append("Ollama")
    return out


def _run(cmd: list, timeout: float = 600) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NOWIN,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return f"erreur : {e}"


def start_engine(cfg=None, model: str = "", context: int = 16384) -> dict:
    """Démarre le serveur local (LM Studio / Bionic) et charge le modèle demandé s'il ne l'est pas déjà.
    Ne télécharge rien. -> le résultat de discover()."""
    found = discover(cfg)
    lms = lms_cli()
    if not found["base"] and lms:
        _run([lms, "server", "start"], 60)
        for _ in range(10):
            time.sleep(1)
            found = discover(cfg)
            if found["base"]:
                break
    model = model or (str(cfg.get("local_model") or "") if cfg else "")
    if lms and model and found["base"]:
        loaded = _run([lms, "ps"], 30)
        if model not in loaded:
            _run([lms, "load", model, "--gpu", "max", "--context-length", str(context), "-y"], 300)
            found = discover(cfg)
    return found


def unload_all() -> str:
    """Mode « je joue » : libère la carte graphique (LM Studio / Bionic)."""
    lms = lms_cli()
    return _run([lms, "unload", "--all"], 60) if lms else "aucun moteur pilotable trouvé"


def downloaded_models() -> str:
    lms = lms_cli()
    if lms:
        return _run([lms, "ls"], 30)
    if ollama_cli():
        return _run([ollama_cli(), "list"], 30)
    return ""


# ------------------------------------------------------------------ appels
class Engine:
    """Un moteur local prêt à répondre. `base`, `chat_model`, `embed_model` viennent de discover()."""

    def __init__(self, base: str, chat_model: str, embed_model: str = ""):
        self.base = base.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model

    @classmethod
    def from_cfg(cls, cfg=None, start: bool = True) -> "Engine":
        found = start_engine(cfg) if start else discover(cfg)
        if not found["base"]:
            raise LocalError("aucune IA locale ne répond sur cet ordinateur (LM Studio, Bionic ou Ollama doit être lancé).")
        if not found["chat"]:
            raise LocalError("le moteur local tourne, mais aucun modèle de discussion n'est chargé.")
        return cls(found["base"], found["chat"], found["embed"])

    def chat(self, messages: list, tools: list = None, max_tokens: int = 1800, temperature: float = 0.2) -> dict:
        """-> le message de l'assistant (dict OpenAI : content, tool_calls éventuels)."""
        body = {"model": self.chat_model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            body["tools"] = tools
        data = _post(self.base + "/chat/completions", body)
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise LocalError(f"réponse inattendue du moteur local : {str(data)[:300]}") from e

    def embed(self, texts: list) -> list:
        if not self.embed_model:
            raise LocalError("aucun modèle d'embedding chargé")
        out = []
        for i in range(0, len(texts), 16):
            data = _post(self.base + "/embeddings", {"model": self.embed_model, "input": texts[i:i + 16]}, 300)
            out += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        return out
