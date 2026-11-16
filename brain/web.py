"""Accès à Internet pour l'IA locale : c'est Jimmy qui va chercher la page et la donne au modèle comme TEXTE.

Ce texte est une information, jamais un ordre : le modèle est prévenu, et les outils qui écrivent quelque part
ne peuvent de toute façon être déclenchés que par une demande de l'utilisateur (vérifiée dans le code).

Recherche : d'abord le navigateur intégré de Jimmy (invisible, vrais résultats Bing / DuckDuckGo), puis l'API de Wikipédia, puis
DuckDuckGo en direct, car les moteurs bloquent ou dégradent souvent les programmes simples. Aucune fenêtre de navigateur n'est ouverte : tout se fait en arrière-plan.
"""
from __future__ import annotations

import base64
import html
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}
last_source = ""          # quelle source a répondu à la dernière recherche (affiché dans les étapes)
browser_search = None     # fonction (requête, n) -> [(titre, adresse, extrait)] fournie par la fenêtre : recherche par le navigateur intégré


def _get(url: str, data: bytes | None = None, timeout: int = 20, limit: int = 1_500_000) -> str:
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit).decode("utf-8", "replace")


def fetch(url: str, maxc: int = 6000) -> str:
    """Texte lisible d'une page (balises, scripts et styles retirés), limité à maxc caractères."""
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("adresse refusée : seules les adresses http(s) sont lues")
    raw = _get(url)
    raw = re.sub(r"(?is)<(script|style|nav|footer|header|svg|noscript)[^>]*>.*?</\1>", " ", raw)
    txt = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\r\f]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    return txt[:maxc]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _unwrap_bing(href: str) -> str:
    """Les liens de Bing passent par un redirecteur : l'adresse réelle est dans le paramètre u (base64)."""
    href = html.unescape(href)
    if "bing.com/ck/a" in href:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            u = u[2:]
            try:
                return base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                return ""
    return href


def _wikipedia(query: str, n: int) -> list:
    out = []
    for lang in ("fr", "en"):
        data = json.loads(_get(f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit={n}&srsearch="
                               + urllib.parse.quote(query)))
        for it in data.get("query", {}).get("search", []):
            title = it.get("title", "")
            out.append((f"{title} (Wikipédia {lang})", f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                        _clean(it.get("snippet", ""))))
        if out:
            break
    return out[:n]


def _ddg(query: str, n: int) -> list:
    page = _get("https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query))
    out = []
    for m in re.finditer(r"<a\s([^>]*class=['\"]result-link['\"][^>]*)>(.*?)</a>", page, re.S):
        h = re.search(r"href=['\"]([^'\"]+)['\"]", m.group(1))
        if not h:
            continue
        href = html.unescape(h.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if "uddg" in q:
            href = q["uddg"][0]
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("http"):
            out.append((_clean(m.group(2)), href, ""))
        if len(out) >= n:
            break
    return out


def search_full(query: str, n: int = 5) -> list:
    """Recherche -> [(titre, adresse, extrait)]. Essaie plusieurs sources ; lève une erreur claire seulement si TOUTES échouent."""
    global last_source
    errors = []
    sources = [("Wikipédia", _wikipedia), ("DuckDuckGo", _ddg)]
    if browser_search:
        sources.insert(0, ("Navigateur de Jimmy", browser_search))
    for name, fn in sources:
        try:
            res = fn(query, n)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} : {e}")
            continue
        if res:
            if name != "Navigateur de Jimmy":
                last_source = name
            return res
        errors.append(f"{name} : aucun résultat")
    last_source = ""
    raise RuntimeError("Aucune source de recherche n'a répondu (" + " ; ".join(errors) + "). Vérifie la connexion Internet.")


def search(query: str, n: int = 5) -> list:
    """Compatibilité : -> [(titre, adresse)]."""
    return [(t, u) for t, u, _s in search_full(query, n)]
