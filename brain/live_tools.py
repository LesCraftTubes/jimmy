"""Les outils « PC » d'Aurélie : voir un site comme un humain (navigateur intégré), prendre des captures, regarder une image.

Règle portée par le CODE : cliquer, écrire dans un champ et capturer tout l'écran ne partent que si l'utilisateur l'a demandé dans son
message de ce tour (comme les outils qui écrivent). Quand c'est Jimmy qui lui délègue un travail (lecture seule), ils sont refusés.
Ouvrir, lire, contrôler, défiler, capturer une page et analyser une image sont libres : ils ne modifient rien.
"""
from __future__ import annotations

from pathlib import Path

from . import live, vision

_ORDER_UI = r"(?i)\b(clique[rz]?|clic|appuie|appuyer|remplis|remplir|saisis|écris|ecris|tape[rz]?|teste[rz]?|essaie|navigue[rz]?|parcours|connecte)"
_ORDER_SCREEN = r"(?i)(écran|ecran|screenshot|capture d)"


def _lb():
    if live.instance is None:
        raise RuntimeError("le navigateur intégré n'est pas disponible dans cette fenêtre")
    return live.instance


def _fmt_report(rep: dict) -> str:
    r = rep.get("report") or {}
    lines = [f"Titre : {r.get('title') or '(aucun)'} · {r.get('page_height', '?')} px de haut"]
    if r.get("headings"):
        lines.append("Titres : " + " | ".join(r["headings"][:8]))
    lines.append(f"{r.get('links', 0)} liens, {r.get('buttons', 0)} boutons, {r.get('forms', 0)} formulaires, {r.get('images', 0)} images.")
    problems = []
    if r.get("broken_images"):
        problems.append("images cassées : " + ", ".join(r["broken_images"][:4]))
    if r.get("overflow_x"):
        problems.append("la page déborde en largeur" + (f" (à cause de : {', '.join(r['too_wide'])})" if r.get("too_wide") else ""))
    if not r.get("viewport_meta"):
        problems.append("pas de balise viewport (affichage mobile douteux)")
    if r.get("no_alt"):
        problems.append(f"{r['no_alt']} image(s) sans texte alternatif")
    if r.get("small_targets"):
        problems.append(f"{r['small_targets']} élément(s) cliquable(s) très petit(s)")
    if r.get("console_errors"):
        problems.append("erreurs JavaScript : " + " ; ".join(r["console_errors"][:4]))
    lines.append("Problèmes : " + ("; ".join(problems) if problems else "aucun détecté") + ".")
    return "\n".join(lines)


def _t_open(a, ctx):
    res = _lb().open(str(a.get("adresse", "")))
    if not res.get("ok"):
        return f"Impossible d'ouvrir la page : {res.get('error') or 'échec du chargement'}."
    txt = _lb().text(500).get("text", "")
    return (f"Page ouverte : « {res.get('title') or '(sans titre)'} » ({res['url']}), chargée en {res['ms']} ms, "
            f"{res.get('errors', 0)} erreur(s) JavaScript.\nDébut du texte affiché : {' '.join(txt.split())[:350]}")


def _t_text(a, ctx):
    res = _lb().text(5500)
    if not res.get("ok"):
        return f"Aucune page lisible : {res.get('error')}."
    return f"Texte affiché sur « {res.get('title')} » :\n{res['text']}"


def _t_report(a, ctx):
    res = _lb().report()
    return _fmt_report(res) if res.get("ok") else f"Contrôle impossible : {res.get('error')}."


def _t_capture(a, ctx):
    lb = _lb()
    url = str(a.get("adresse", "")).strip()
    if url:
        res = lb.open(url)
        if not res.get("ok"):
            return f"Impossible d'ouvrir la page : {res.get('error') or 'échec du chargement'}."
    full = str(a.get("plein_ecran", "")).strip().lower() in ("oui", "true", "1", "vrai", "entiere", "entière", "page entière")
    try:
        width = int(str(a.get("largeur", "0") or "0"))
    except ValueError:
        width = 0
    res = lb.capture(full=full, selector=str(a.get("element", "")).strip(), width=width, caption=str(a.get("legende", "")).strip(),
                     who="local")
    if not res.get("ok"):
        return f"Capture impossible : {res.get('error')}."
    ctx.notes["last_capture"] = res["file"]
    return (f"Capture enregistrée ({res['w']}×{res['h']} px) : {res['file']}\nElle est DÉJÀ affichée dans la discussion : ne la recopie pas. "
            "Pour la décrire, utilise analyser_image ou rapport_page.")


def _t_click(a, ctx):
    res = _lb().click(str(a.get("cible", "")))
    if not res.get("ok"):
        return f"Clic impossible : {res.get('error')}."
    return (f"Cliqué sur « {res.get('clicked')} ». Page : « {res.get('title')} » ({res.get('url')})"
            + (" — la page a changé." if res.get("navigated") else " — même page."))


def _t_type(a, ctx):
    res = _lb().type_text(str(a.get("champ", "")), str(a.get("texte", "")))
    return "Texte écrit dans le champ (rien n'est envoyé : je n'appuie pas sur Entrée)." if res.get("ok") else f"Écriture impossible : {res.get('error')}."


def _t_scroll(a, ctx):
    res = _lb().scroll(str(a.get("sens", "bas")))
    if not res.get("ok"):
        return f"Défilement impossible : {res.get('error')}."
    p = res.get("pos") or {}
    return f"Position : {p.get('y', 0)} px sur {p.get('h', '?')} px (écran de {p.get('vh', '?')} px)."


def _t_screen(a, ctx):
    res = _lb().screen(caption=str(a.get("legende", "")).strip() or "Écran du PC")
    if not res.get("ok"):
        return f"Capture de l'écran impossible : {res.get('error')}."
    ctx.notes["last_capture"] = res["file"]
    return f"Capture de l'écran enregistrée ({res['w']}×{res['h']} px) : {res['file']}\nElle est déjà affichée dans la discussion."


def _t_image(a, ctx):
    path = str(a.get("chemin", "")).strip()
    if path.lower() in ("", "derniere", "dernière", "last", "la derniere capture", "la dernière capture"):
        path = ctx.notes.get("last_capture") or (live.instance.last_capture if live.instance else "")
        if not path and live.list_captures(1):
            path = live.list_captures(1)[0]["file"]
    if not path:
        return "Aucune image à analyser : donne le chemin d'une image ou prends d'abord une capture."
    p = Path(path)
    if live._SECRET.search(p.name):
        return "REFUSÉ : ce fichier pourrait contenir un secret."
    return vision.analyze(ctx.cfg, str(p), str(a.get("question", "")).strip())


def register(reg) -> None:
    from .tools import Tool
    reg.add(Tool("ouvrir_page", "Ouvre une page dans TON navigateur (comme un humain) : site, adresse locale ou fichier .html. Renvoie le titre et le début du texte affiché.",
                 {"adresse": "adresse http(s), localhost ou chemin d'un fichier .html"}, _t_open, step="Navigateur"))
    reg.add(Tool("lire_page_ouverte", "Lit le texte vraiment affiché par la page ouverte (JavaScript compris).", {"_": "(aucun paramètre)"},
                 _t_text, required=[], step="Navigateur"))
    reg.add(Tool("rapport_page", "Contrôle la page ouverte : titres, images cassées, débordement en largeur, erreurs JavaScript, éléments trop petits.",
                 {"_": "(aucun paramètre)"}, _t_report, required=[], step="Contrôle"))
    reg.add(Tool("capturer_page", "Prend une CAPTURE d'une page web (ouvre l'adresse si tu en donnes une) : écran visible, page entière ou un seul élément. "
                 "La capture s'affiche dans la discussion pour l'utilisateur et se range dans la galerie.",
                 {"adresse": "adresse à ouvrir d'abord (facultatif si une page est déjà ouverte)", "plein_ecran": "oui pour toute la page (facultatif)",
                  "element": "sélecteur CSS d'un élément à capturer seul (facultatif)", "largeur": "largeur en pixels, ex. 390 pour un mobile (facultatif)",
                  "legende": "légende courte (facultatif)"}, _t_capture, required=[], step="Capture"))
    reg.add(Tool("defiler", "Fait défiler la page ouverte.", {"sens": "haut, bas, page (une page plus bas) ou -page (une page plus haut)"},
                 _t_scroll, required=[], step="Navigateur"))
    reg.add(Tool("cliquer", "Clique sur un élément de la page ouverte (texte visible du bouton ou du lien, ou sélecteur CSS).",
                 {"cible": "texte visible ou sélecteur CSS"}, _t_click, order=_ORDER_UI, step="Clic"))
    reg.add(Tool("ecrire_dans", "Écrit un texte dans un champ de la page ouverte (n'envoie rien).",
                 {"champ": "nom, texte indicatif ou sélecteur du champ", "texte": "le texte à écrire"}, _t_type, required=["champ", "texte"],
                 order=_ORDER_UI, step="Saisie"))
    reg.add(Tool("capturer_ecran", "Capture TOUT l'écran du PC (seulement si l'utilisateur le demande).", {"legende": "légende courte (facultatif)"},
                 _t_screen, required=[], order=_ORDER_SCREEN, step="Capture"))
    reg.add(Tool("analyser_image", "Regarde une image (capture, photo, fichier) : texte qu'elle contient, couleurs, et description si un modèle de vision est installé. "
                 "Sans chemin, prend la dernière capture.",
                 {"chemin": "chemin de l'image (vide = dernière capture)", "question": "ce que tu veux savoir (facultatif)"}, _t_image,
                 required=[], step="Image"))
