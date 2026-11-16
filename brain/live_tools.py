"""Les outils « PC » d'Aurélie : voir un site comme un humain (navigateur intégré), prendre des captures, regarder une image.

Règle portée par le CODE : cliquer, écrire dans un champ et capturer tout l'écran ne partent que si l'utilisateur l'a demandé dans son
message de ce tour (comme les outils qui écrivent). Quand c'est Jimmy qui lui délègue un travail (lecture seule), ils sont refusés.
Ouvrir, lire, contrôler, défiler, capturer une page et analyser une image sont libres : ils ne modifient rien.
"""
from __future__ import annotations

import re
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


def _t_judge(a, ctx):
    """Ouvre la page (si une adresse est donnée), la capture, la mesure (couleurs, contrastes, polices...) et la regarde avec le modèle de vision."""
    lb = _lb()
    url = str(a.get("adresse", "")).strip()
    if url:
        res = lb.open(url)
        if not res.get("ok"):
            return f"Impossible d'ouvrir la page : {res.get('error') or 'échec du chargement'}."
    try:
        width = int(str(a.get("largeur", "0") or "0"))
    except ValueError:
        width = 0
    cap = lb.capture(width=width, caption=str(a.get("legende", "")).strip() or "Rendu à juger", who="local")
    if not cap.get("ok"):
        return f"Capture impossible : {cap.get('error')}."
    ctx.notes["last_capture"] = cap["file"]
    ctx.step("Regard", "j'analyse le rendu" + (" avec le modèle de vision" if vision.vision_model(ctx.cfg) else " avec les mesures de la page"))
    q = str(a.get("question", "")).strip() or "Le rendu est-il réussi ? Que penses-tu des couleurs, de la lisibilité et de la mise en page ?"
    from .tools import FINAL
    return FINAL + vision.judge_reply(vision.inspect(ctx.cfg, cap["file"], q), cap.get("title") or "")


def _t_jimmy_work(a, ctx):
    """Ce que Jimmy fait (ou vient de faire), lu dans le fil d'activité de la discussion : aucun token."""
    import extras
    import time as _t
    sid = ctx.notes.get("session_id")
    if not sid:
        return "Je n'ai pas de discussion en cours : je ne vois pas encore de travail de Jimmy."
    items = extras.load(sid, kinds=("work",))
    if not items:
        return "Jimmy n'a encore rien fait de visible dans cette discussion (aucun fichier lu ou modifié, aucune commande)."
    last, task = items[-1]["ts"], []
    for it in reversed(items):                                 # la « dernière tâche » = jusqu'à une pause de plus de 8 minutes
        if last - it["ts"] > 480:
            break
        task.append(it)
        last = it["ts"]
    task.reverse()
    starts = [i for i in task if i.get("phase") == "start"]
    ends = {i.get("id"): i for i in task if i.get("phase") == "end"}
    kinds = {"Read": 0, "Edit": 0, "MultiEdit": 0, "Write": 0, "cmd": 0, "other": 0}
    files, failed = [], []
    for st in starts:
        tool = st.get("tool", "")
        k = tool if tool in kinds else ("cmd" if tool in ("Bash", "PowerShell") else "other")
        kinds[k] += 1
        if tool in ("Edit", "MultiEdit", "Write") and st.get("target"):
            files.append(Path(st["target"]).name)
        e = ends.get(st.get("id"))
        if e is not None and not e.get("ok"):
            failed.append(f"{st.get('label', tool)} : {str(e.get('out', ''))[:90]}")
    running = [s for s in starts if s.get("id") not in ends]
    ago = int(_t.time() - task[-1]["ts"])
    out = [f"Dernière activité de Jimmy : il y a {ago} s." if ago < 3600 else "Dernière activité de Jimmy : il y a plus d'une heure.",
           f"Dans cette tâche : {kinds['Read']} lecture(s), {kinds['Edit'] + kinds['MultiEdit'] + kinds['Write']} modification(s), {kinds['cmd']} commande(s), {kinds['other']} autre(s) action(s)."]
    if files:
        out.append("Fichiers modifiés : " + ", ".join(dict.fromkeys(files)) + ".")
    if running:
        out.append("En ce moment : " + str(running[-1].get("label", "une action")) + ".")
    if failed:
        out.append("Actions en échec : " + " ; ".join(failed[:3]) + ".")
    says = [i for i in task if i.get("phase") == "say"]
    if says:
        out.append("Dernière chose qu'il a dite : « " + str(says[-1].get("text", ""))[:200] + " »")
    return "\n".join(out)


def _t_check_files(a, ctx):
    """Relit des fichiers : syntaxe et secrets écrits en clair (lecture seule)."""
    from . import checks
    raw = str(a.get("chemins", "")).replace("\n", ";")
    paths = [x.strip().strip('"') for x in re.split(r"[;,]", raw) if x.strip()]
    if not paths:
        return "Donne le chemin d'au moins un fichier."
    base = Path(str(ctx.cfg.get("workdir") or Path.home()))
    full = [str(Path(x) if Path(x).is_absolute() else base / x) for x in paths[:12]]
    res = checks.check_files(full)
    return checks.summary(res)


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
    reg.add(Tool("travail_de_jimmy", "Dit ce que JIMMY est en train de faire ou vient de faire (fichiers lus et modifiés, commandes, échecs), d'après le fil d'activité. "
                 "À utiliser pour « que fait Jimmy ? », « où en est-il ? », « qu'a-t-il modifié ? ».", {"_": "(aucun paramètre)"}, _t_jimmy_work, required=[], step="Activité"))
    reg.add(Tool("relire_fichiers", "Relit des fichiers (par exemple ceux que Jimmy vient de modifier) : erreurs de syntaxe (Python, JSON, JavaScript, HTML, CSS) et mots de passe ou clés écrits en clair.",
                 {"chemins": "chemins séparés par des points-virgules"}, _t_check_files, step="Relecture"))
    reg.add(Tool("juger_rendu", "REGARDE vraiment le rendu d'une page : l'ouvre, la capture, mesure ses couleurs, contrastes et polices, et la regarde avec le modèle de vision. "
                 "À utiliser pour juger le design, les couleurs, la lisibilité ou la mise en page d'un site.",
                 {"adresse": "adresse à ouvrir d'abord (facultatif si une page est déjà ouverte)", "question": "ce que tu veux savoir (facultatif)",
                  "largeur": "largeur en pixels, ex. 390 pour un mobile (facultatif)", "legende": "légende courte (facultatif)"}, _t_judge, required=[], step="Regard"))
    reg.add(Tool("analyser_image", "Regarde une image (capture, photo, fichier) : texte qu'elle contient, couleurs, et description si un modèle de vision est installé. "
                 "Sans chemin, prend la dernière capture.",
                 {"chemin": "chemin de l'image (vide = dernière capture)", "question": "ce que tu veux savoir (facultatif)"}, _t_image,
                 required=[], step="Image"))
