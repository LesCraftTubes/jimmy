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


# ------------------------------------------------------------------ sites connus + exploration
SITE = ""                 # site de l'utilisateur : réglage « site_url » de la configuration (vide = aucun)
SITE_DOC = ""             # page de départ de sa documentation : réglage « site_doc » (ex. /wiki/)
_SITE_RE = None           # fautes de frappe courantes du nom du site : réglage « site_alias » (expression régulière sur le nom de domaine)


def configure(cfg) -> None:
    """Lit le site de l'utilisateur dans la configuration (appelé par les outils avant de lire ou d'explorer)."""
    global SITE, SITE_DOC, _SITE_RE
    try:
        SITE = str(cfg.get("site_url") or "").rstrip("/")
        SITE_DOC = str(cfg.get("site_doc") or "")
        alias = str(cfg.get("site_alias") or "")
        _SITE_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:" + alias + r")(?=[/?#]|$)", re.I) if alias and SITE else None
    except Exception:  # noqa: BLE001
        SITE, SITE_DOC, _SITE_RE = "", "", None


def resolve(url: str) -> str:
    """Complète et corrige une adresse : ajoute https://, et remplace les fautes courantes du nom du site de l'utilisateur."""
    u = (url or "").strip().strip("«»\"' ")
    if _SITE_RE and _SITE_RE.match(u):
        return SITE + _SITE_RE.sub("", u)
    if u and not re.match(r"^https?://", u, re.I) and re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I):
        u = "https://" + u
    return u


def fix_alias(url: str, cfg=None) -> str:
    """Corrige seulement la faute de frappe du site de l'utilisateur (pour le navigateur d'Aurélie) ; toute autre adresse reste telle quelle."""
    if cfg is not None:
        configure(cfg)
    u = (url or "").strip()
    return resolve(u) if _SITE_RE and _SITE_RE.match(u) else u


def _links(raw: str, base: str) -> list:
    host = urllib.parse.urlparse(base).netloc
    out = []
    for m in re.finditer(r"""<a\s[^>]*href=["']([^"'#]+)["']""", raw, re.I):
        href = urllib.parse.urljoin(base, html.unescape(m.group(1))).split("#")[0]
        p = urllib.parse.urlparse(href)
        if p.scheme in ("http", "https") and p.netloc == host and not re.search(
                r"\.(css|js|png|jpe?g|gif|webp|svg|ico|pdf|zip|woff2?)$|/(auth|staff|logout|mot-de-passe)\b", p.path, re.I):
            if href not in out:
                out.append(href)
    return out


def _text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|header|svg|noscript)[^>]*>.*?</\1>", " ", raw)
    txt = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", txt).strip()


last_ranked = []      # [(nom, rang, effet)] des éléments de rang le plus haut trouvés (demandes « les plus puissants »)
last_full = ""        # texte COMPLET des pages lues par le dernier crawl (sert à vérifier que la réponse n'invente rien)

_STOP = set("""dans avec pour cette votre notre leurs elles vraiment potentiellement genre quand alors aussi comme faire elle cherche chercher trouve trouver
regarde regarder voir site page pages mettre mets veux voudrais aimerais peux pouvoir moyen donne donner liste meilleurs meilleur meilleure puissant puissants
puissante vraiment sentir tout tous toutes fait faut plus moins entre parmi leur ceux celles sont sera serait etre avoir encore deja jamais toujours""".split())


_RANKS = {"S+": 0, "S": 1, "A": 2}
_CONN = {"du", "de", "la", "le", "les", "des", "l", "d", "au", "aux", "et", "en"}
_WANT_BEST = re.compile(r"(puissan|meilleur|plus fort|top ?\d|best|l[ée]gendaire|ultime)", re.I)


def ranked_rows(txt: str, limit: int = 14) -> list:
    """Lignes de tableau « Nom RANG effet... » (rangs S+, S, A) d'une page : [(nom, rang, effet)], les plus hauts d'abord."""
    toks = txt.split()
    rows, seen = [], set()
    for i, t in enumerate(toks):
        if t not in _RANKS or i == 0 or i + 1 >= len(toks) or not toks[i + 1][:1].isupper():
            continue
        name = []
        for p in reversed(toks[max(0, i - 7):i]):
            core = p.strip("'" + chr(8217))
            if core[:1].isupper() or core.lower() in _CONN or core.lower().rstrip("'" + chr(8217)) in _CONN:
                name.append(p)
            else:
                break
        while name and name[-1].lower() in _CONN:      # un nom ne commence pas par « du »
            name.pop()
        name = " ".join(reversed(name)).strip()
        if len(name) < 5 or name in seen:
            continue
        eff = toks[i + 1:i + 14]
        for k in range(2, len(eff)):
            if eff[k] == eff[0]:                  # le même effet répété = la colonne « 5 étoiles » : on s'arrête
                eff = eff[:k]
                break
        while eff and eff[-1] in ("·", "%"):
            eff.pop()
        seen.add(name)
        rows.append((name, t, " ".join(eff)[:110]))
    rows.sort(key=lambda r: _RANKS[r[1]])
    return rows[:limit]


def keywords_of(text: str) -> list:
    """Mots utiles d'une demande (5 lettres et plus, sans les mots courants) : servent à choisir les pages à lire."""
    out = []
    for w in re.findall(r"\w{5,}", (text or "").lower()):
        if w not in _STOP and w not in out:
            out.append(w)
    return out[:14]


def _anchors(raw: str, base: str) -> dict:
    """adresse -> texte du lien (pour deviner quelles pages parlent du sujet)."""
    out = {}
    for m in re.finditer(r"""(?is)<a\s[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""", raw):
        out.setdefault(urllib.parse.urljoin(base, html.unescape(m.group(1))).split("#")[0], _clean(m.group(2)).lower())
    return out


def best_window(text: str, question: str, size: int = 3500) -> str:
    """Extrait de `text` (la page lue) le plus riche en mots de la question : sert à reposer la question au modèle sur un texte COURT."""
    words = keywords_of(question)
    low = text.lower()
    pos = [m.start() for wd in words[:8] for m in re.finditer(re.escape(wd), low)]
    if len(text) <= size or not pos:
        return text[:size]
    start = max(range(0, len(text) - size + 1, 200), key=lambda s: sum(1 for p in pos if s <= p < s + size))
    start = max(0, start - 600)          # un peu avant : le premier élément d'une liste est souvent juste au-dessus de la zone la plus dense
    return text[start:start + size + 600]



# ------------------------------------------------------------------ listes longues : composées par le CODE (le petit modèle invente au-delà de ~40 éléments)
last_html = {}            # adresse -> HTML des pages lues par le dernier crawl
last_top_url = ""         # la page la plus pertinente du dernier crawl
_FULL_LIST = re.compile(r"(tous|toutes|liste (compl[èe]te|enti[èe]re|de tous|de toutes|exhaustive)|l['’]ensemble|chacun|chacune|au complet|en entier|exhaustif)", re.I)
_VOID = {"img", "br", "hr", "input", "meta", "link", "source", "wbr", "area", "col"}


def extract_groups(page_html: str) -> list:
    """Groupes de lignes d'une page : [(titre, [ligne, ...])]. Une ligne = un <li> ou un <tr> ; le titre = le <summary> ou le titre (h2-h4) qui précède.
    Les blocs de description (classe « desc ») sont ignorés : il reste le nom et les chiffres (étoiles, mana, recharge...)."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(s):
            super().__init__(convert_charrefs=True)
            s.groups, s.stack, s.skip, s.desc = [], [], 0, 0
            s.head, s.head_buf, s.row, s.row_in = "", None, None, 0
            s.has_td = s.has_th = False

        def handle_starttag(s, tag, attrs):
            if tag in _VOID:
                return
            cls = dict(attrs).get("class", "") or ""
            is_desc = bool(re.search(r"desc", cls, re.I))
            skip = tag in ("script", "style", "nav", "header", "footer", "svg", "noscript")
            s.stack.append((tag, is_desc, skip))
            s.skip += skip
            s.desc += is_desc
            if s.skip:
                return
            if tag in ("summary", "h2", "h3", "h4"):
                s.head_buf = []
            if tag in ("li", "tr"):
                s.row_in += 1
                if s.row_in == 1:
                    s.row, s.has_td, s.has_th = [], False, False
            if tag == "td":
                s.has_td = True
            if tag == "th":
                s.has_th = True

        def handle_endtag(s, tag):
            if tag in _VOID:
                return
            for k in range(len(s.stack) - 1, -1, -1):
                if s.stack[k][0] == tag:
                    _t, is_desc, skip = s.stack.pop(k)
                    s.skip -= skip
                    s.desc -= is_desc
                    break
            if s.skip:
                return
            if tag in ("summary", "h2", "h3", "h4") and s.head_buf is not None:
                parts = [x for x in s.head_buf if x]
                s.head = (parts[0] if tag == "summary" and parts else " ".join(parts)).strip()
                s.head_buf = None
            if tag in ("li", "tr") and s.row_in:
                s.row_in -= 1
                if s.row_in == 0 and s.row is not None:
                    txt = re.sub(r"\s+", " ", " ".join(s.row)).strip()
                    if len(txt) >= 3 and not (s.has_th and not s.has_td):       # une ligne d'en-tête de tableau n'est pas un élément
                        if not s.groups or s.groups[-1][0] != s.head:
                            s.groups.append((s.head, []))
                        s.groups[-1][1].append(txt)
                    s.row = None

        def handle_data(s, data):
            d = data.strip()
            if not d or s.skip or s.desc:
                return
            if s.head_buf is not None:
                s.head_buf.append(d)
            if s.row is not None:
                s.row.append(d)

    p = P()
    try:
        p.feed(page_html)
    except Exception:  # noqa: BLE001
        pass
    return [(h, rows) for h, rows in p.groups if len(rows) >= 3]


def _row_tokens(row: str) -> set:
    return {("*" if "\u2605" in t else t.lower()) for t in re.findall(r"[A-Za-z\u00c0-\u00ff\u2605]+", row)}


def list_groups() -> list:
    """Les groupes de lignes (listes) de la page la plus pertinente : [(titre, [ligne...])], ceux qui se ressemblent (même structure)."""
    if not last_top_url or last_top_url not in last_html:
        return []
    groups = extract_groups(last_html[last_top_url])
    if not groups:
        return []
    # mots « de structure » : présents dans la plupart des lignes de plusieurs groupes (étoiles, « mana »...) ; les noms propres ne reviennent que dans un groupe
    cnt = {}
    for _h, rows in groups:
        toks = [_row_tokens(r) for r in rows]
        for t in set().union(*toks):
            if (t == "*" or len(t) >= 4) and sum(1 for x in toks if t in x) >= 0.7 * len(rows):
                cnt[t] = cnt.get(t, 0) + 1
    structural = {t for t, n in cnt.items() if n >= max(3, 0.3 * len(groups))}
    if structural:
        keep = [(h, rows) for h, rows in groups if sum(1 for r in rows if structural & _row_tokens(r)) >= 0.7 * len(rows)]
    else:       # pas de mot commun : on garde les groupes de taille et de longueur de ligne comparables au plus grand
        ref = max(groups, key=lambda g: len(g[1]))
        ref_len = sum(len(r) for r in ref[1]) / len(ref[1])
        keep = [(h, rows) for h, rows in groups if len(rows) >= 5 and 0.5 * ref_len <= sum(len(r) for r in rows) / len(rows) <= 2 * ref_len]
    return keep if sum(len(r) for _h, r in keep) >= 10 else []


def structure_digest() -> str:
    """Comptage EXACT des groupes de la page (calculé par le code) : le petit modèle se trompait en comptant lui-même."""
    keep = list_groups()
    if not keep:
        return ""
    by = {}
    for h, r in keep:
        by.setdefault(len(r), []).append(h)
    dist = " ; ".join(f"{len(hs)} groupe(s) de {n} ligne(s) : {', '.join(hs)}" for n, hs in sorted(by.items(), key=lambda kv: -len(kv[1])))
    return ("STRUCTURE EXACTE DE LA PAGE (comptée par le code, fiable) : " + f"{len(keep)} groupes, {sum(len(r) for _h, r in keep)} lignes au total. "
            + "Répartition : " + dist + ". Détail : " + " ; ".join(f"{h} ({len(r)})" for h, r in keep) + ".")


def compose_list(question: str) -> str:
    """Si on demande une liste COMPLÈTE (« la liste de tous ») : recopie, telle qu'elle est écrite, la liste structurée de la page la plus pertinente."""
    if not _FULL_LIST.search(question or ""):
        return ""
    keep = list_groups()
    if not keep:
        return ""
    total = sum(len(r) for _h, r in keep)
    if total < 10:
        return ""
    out = [f"Voici la liste complète, recopiée telle qu'elle est écrite sur la page ({total} éléments, {len(keep)} groupes) :"]
    for head, rows in keep:
        out.append(f"**{head or 'Liste'}** ({len(rows)}) : " + " ; ".join(rows))
    return "\n\n".join(out)


def crawl(start: str, keywords: str = "", max_pages: int = 12, per_page: int = 1500, on_page=None) -> str:
    """Parcourt un site à partir d'une page (liens du même site) et renvoie le texte des pages lues.
    Avec des mots-clés, les liens dont l'adresse ou le texte parlent du sujet sont suivis en premier (c'est elle qui cherche),
    puis les pages qui contiennent les mots passent en tête du résultat, avec seulement les passages utiles."""
    start = resolve(start) or (SITE + SITE_DOC)
    if not start:
        raise ValueError("aucune adresse donnée et aucun site configuré : trouve l'adresse avec chercher_web ou la mémoire, sans rien demander à l'utilisateur")
    if not re.match(r"^https?://", start, re.I):
        raise ValueError("adresse refusée : seules les adresses http(s) sont lues")
    words = keywords_of(keywords)
    if words:
        max_pages = max(max_pages, 20)
    stems = [w[:5] for w in words]
    global last_full, last_ranked, last_html, last_top_url
    last_html, last_top_url = {}, ""
    last_full = ""
    last_ranked = []
    queue, seen, pages = [start], {start}, []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        try:
            raw = _get(url, timeout=15)
        except Exception as e:  # noqa: BLE001
            pages.append((0, url, f"(illisible : {e})"))        # chaîne = page illisible
            continue
        txt = _text(raw)
        title = (re.search(r"(?is)<title[^>]*>(.*?)</title>", raw) or [None, url])[1]
        last_full += "\n" + txt
        last_html[url] = raw
        if _WANT_BEST.search(keywords or ""):
            last_ranked = (last_ranked + [r for r in ranked_rows(txt) if r[0] not in [x[0] for x in last_ranked]])
            last_ranked.sort(key=lambda r: _RANKS[r[1]])
        low = txt.lower()
        score = sum(low.count(w) for w in words)
        pages.append((score, url, (_clean(title)[:80], txt)))        # le texte est découpé à la fin, quand on sait quelle page est la plus pertinente
        if on_page:
            try:
                on_page(url, _clean(title)[:70], len(pages), max_pages)
            except Exception:  # noqa: BLE001
                pass
        base = start.rsplit("/", 1)[0] + "/"
        anchors = _anchors(raw, url)

        def prio(l):
            hay = (urllib.parse.unquote(l) + " " + anchors.get(l, "")).lower()
            return (0 if any(st in hay for st in stems) else 1, 0 if l.startswith(base) else 1)
        new = [l for l in _links(raw, url) if l not in seen]
        seen.update(new)
        queue = sorted(queue + new, key=prio)        # les liens qui parlent du sujet passent devant
    pages.sort(key=lambda p: -p[0])
    total = len(pages)
    if words:
        top = [p for p in pages if p[0]]
        last_top_url = top[0][1] if top else ""
    if words:
        pages = [p for p in pages if p[0]][:4] or pages[:3]      # seulement les pages qui parlent du sujet
    parts = []
    for rank, (score, url, body) in enumerate(pages):
        if isinstance(body, str):                                 # page illisible
            parts.append(f"[Page {url}]\n{body}")
            continue
        title, txt = body
        low = txt.lower()
        if words and score:
            # fenêtre la plus riche en mots du sujet : grande pour la meilleure page, courte pour les autres
            size = 14000 if rank == 0 else 700
            pos = [m.start() for w in words[:6] for m in re.finditer(re.escape(w), low)]
            start_at = max(range(0, max(1, len(txt) - size + 1), 300), key=lambda s: sum(1 for p in pos if s <= p < s + size), default=0) if len(txt) > size else 0
            snip = txt[start_at:start_at + size]
        else:
            snip = txt[:per_page]
        parts.append(f"[Page {url}]\n{title}\n{snip}")
    if last_ranked:
        parts.insert(0, "[ÉLÉMENTS DE RANG LE PLUS HAUT trouvés (S+ d'abord) : pour « les plus puissants », choisis UNIQUEMENT parmi eux]\n" + "\n".join(f"- {n} (rang {r}) : {e}" for n, r, e in last_ranked))
    return "\n\n".join(parts) + f"\n\n({total} pages lues, {len(seen)} adresses repérées sur le site)"
