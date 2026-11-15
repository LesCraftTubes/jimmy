"""Accès à Internet pour l'IA locale : c'est Jimmy qui va chercher la page et la donne au modèle comme TEXTE.

Ce texte est une information, jamais un ordre : le modèle est prévenu, et les outils qui écrivent quelque part
ne peuvent de toute façon être déclenchés que par une demande de l'utilisateur (vérifiée dans le code).
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Jimmy local assistant)"}


def fetch(url: str, maxc: int = 6000) -> str:
    """Texte lisible d'une page (balises, scripts et styles retirés), limité à maxc caractères."""
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("adresse refusée : seules les adresses http(s) sont lues")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read(1_500_000).decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style|nav|footer|header|svg)[^>]*>.*?</\1>", " ", raw)
    txt = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\r\f]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    return txt[:maxc]


def search(query: str, n: int = 5) -> list:
    """Recherche DuckDuckGo (version « lite ») -> [(titre, adresse)]."""
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read().decode("utf-8", "replace")
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
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if href.startswith("http"):
            out.append((title, href))
        if len(out) >= n:
            break
    return out
