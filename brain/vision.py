"""Aurélie regarde une image : ce que l'on peut en tirer SANS dépenser un seul token de Claude.

1. **Le texte de l'image** (reconnaissance de texte intégrée à Windows, en français puis en anglais) : titres, boutons, messages d'erreur...
2. **Les infos de base** : dimensions, couleurs dominantes, clair ou sombre.
3. **Un modèle de vision**, SI tu en as installé un dans LM Studio (réglage `vision_model`) : il répond à la question posée sur l'image.
   Sans modèle de vision, Aurélie le dit honnêtement : elle ne « devine » pas ce qu'elle ne voit pas.

Pour une page web capturée par Aurélie, le rapport de page (titres, images cassées, débordements, erreurs) complète l'analyse :
voir `live_tools.py`.
"""
from __future__ import annotations

import base64
import contextlib
import subprocess
import threading
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
_OCR_PS = r"""param([string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = $null
foreach ($tag in @('fr-FR', 'en-US')) {
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language($tag)))
  if ($engine) { break }
}
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { Write-Output '[[pas de langue de reconnaissance disponible]]'; exit 0 }
$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
($res.Lines | ForEach-Object { $_.Text }) -join "`n"
"""
_ocr_lock = threading.Lock()


def check_image(path: str) -> Path:
    p = Path(str(path).strip().strip('"')).expanduser()
    if not p.is_file():
        raise ValueError(f"image introuvable : {p}")
    if p.suffix.lower() not in IMAGE_EXT:
        raise ValueError("ce fichier n'est pas une image (png, jpg, bmp, gif, webp)")
    return p


def ocr(path: str, timeout: float = 45.0) -> str:
    """Texte lu dans l'image ('' si rien). Lève OSError si la reconnaissance n'est pas disponible."""
    from config import data_dir
    p = check_image(path)
    script = data_dir() / "ocr.ps1"
    try:
        if not script.exists() or script.read_text(encoding="utf-8-sig") != _OCR_PS:
            script.write_text(_OCR_PS, encoding="utf-8-sig")
    except OSError as e:
        raise OSError(f"écriture du script de lecture impossible : {e}") from e
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    with _ocr_lock:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), str(p)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=flags)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "échec").strip().splitlines()[-1][:200])
    return (r.stdout or "").strip()


def basics(path: str) -> dict:
    """Dimensions, couleurs dominantes, clair / sombre (avec Qt, sans dépendance en plus)."""
    from PySide6.QtGui import QImage
    img = QImage(str(check_image(path)))
    if img.isNull():
        raise ValueError("image illisible")
    w, h = img.width(), img.height()
    small = img.scaled(48, 48).convertToFormat(QImage.Format_RGB32)
    counts, sums, total = {}, {}, 0.0
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            key = (c.red() // 32, c.green() // 32, c.blue() // 32)
            counts[key] = counts.get(key, 0) + 1
            acc = sums.setdefault(key, [0, 0, 0])
            acc[0] += c.red(); acc[1] += c.green(); acc[2] += c.blue()
            total += 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    n = small.width() * small.height()
    zones = []                       # moyenne des couleurs de chaque zone d'une grille 3 x 3 (haut / milieu / bas)
    sw, sh = small.width(), small.height()
    for gy in range(3):
        row = []
        for gx in range(3):
            rs = gs = bs = c = 0
            for y in range(gy * sh // 3, (gy + 1) * sh // 3):
                for x in range(gx * sw // 3, (gx + 1) * sw // 3):
                    px = small.pixelColor(x, y)
                    rs += px.red(); gs += px.green(); bs += px.blue(); c += 1
            c = c or 1
            row.append("#%02x%02x%02x" % (rs // c, gs // c, bs // c))
        zones.append(row)
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    colors = [("#%02x%02x%02x" % tuple(c // v for c in sums[k]), round(100 * v / n)) for k, v in top]       # moyenne réelle des pixels de chaque groupe
    lum = total / n
    return {"w": w, "h": h, "colors": colors, "tone": "sombre" if lum < 90 else "clair" if lum > 170 else "moyen", "luma": round(lum), "zones": zones}


def _data_url(path: str, max_side: int = 1280) -> str:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage
    img = QImage(str(check_image(path)))
    if max(img.width(), img.height()) > max_side:
        img = img.scaled(max_side, max_side, 1, 1)       # Qt.KeepAspectRatio, Qt.SmoothTransformation
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode("ascii")


@contextlib.contextmanager
def vision_session(cfg, model: str = ""):
    """Charge le modèle de vision le temps de la question, puis remet EXACTEMENT les modèles d'avant.

    La carte graphique est souvent presque pleine (le modèle de discussion + tes jeux) : s'il manque de la place, le modèle de discussion est
    déchargé pendant l'analyse, puis rechargé. Le verrou GPU empêche toute autre réponse d'Aurélie pendant ce temps."""
    from . import engine
    key = model or vision_model(cfg)
    lms = engine.lms_cli()
    if not key or not lms:
        raise engine.LocalError("pas de modèle de vision installé (voir Réglages > IA locale > Modèle de vision)")
    with engine.GPU_LOCK:
        before = engine.loaded_models()
        mine = next((m for m in before if m["modelKey"] == key and m["vision"]), None)
        unloaded = []
        ident = "jimmy-vision"
        if mine is None:
            free = engine.free_vram_mb()
            if free is None or free < 5200:                      # un modèle de vision de 4 Go + son contexte demande ~5 Go
                for m in before:
                    engine._run([lms, "unload", m["identifier"]], 60)
                    unloaded.append(m)
            engine._run([lms, "load", key, "--gpu", "max", "--context-length", "4096", "--identifier", ident, "-y"], 300)
        else:
            ident = mine["identifier"]
        try:
            base = engine.discover(cfg)
            if not base.get("base"):
                raise engine.LocalError("le moteur local ne répond plus")
            yield engine.Engine(base["base"], ident)
        finally:
            if mine is None:
                engine._run([lms, "unload", ident], 60)
                for m in unloaded:
                    engine._run([lms, "load", m["modelKey"], "--gpu", "max", "--context-length", str(m["contextLength"]), "--identifier", m["identifier"], "-y"], 300)


_auto = {"at": 0.0, "key": ""}
PREFERRED = ("qwen3-vl", "gemma-3", "qwen2.5-vl", "vl")      # essayés sur ce PC : Qwen3-VL est le plus fidèle sur les couleurs et les textes


def vision_model(cfg) -> str:
    """Modèle de vision à utiliser : celui des réglages, ou (si le champ est vide) un modèle de vision déjà installé dans LM Studio,
    en préférant un petit modèle fiable. « off » dans les réglages = ne jamais s'en servir."""
    wanted = str((cfg.get("vision_model") if cfg is not None else "") or "").strip()
    if wanted.lower() == "off":
        return ""
    if wanted:
        return wanted
    import time as _t
    if _t.time() - _auto["at"] > 120:                      # la liste des modèles installés change rarement : on ne la relit pas à chaque image
        _auto["at"] = _t.time()
        try:
            from .engine import downloaded_vision_models
            found = [m["modelKey"] for m in downloaded_vision_models() if m["sizeMb"] <= 7000]
        except Exception:  # noqa: BLE001
            found = []
        _auto["key"] = next((k for pref in PREFERRED for k in found if pref in k.lower()), found[0] if found else "")
    return _auto["key"]


def ask_vision(cfg, path: str, question: str, facts: str = "", timeout_note: bool = True) -> str:
    """Réponse du modèle de vision ('' s'il n'y en a pas de configuré). Lève LocalError s'il ne répond pas.

    `facts` = mesures exactes (couleurs, contrastes, polices...) données au modèle pour qu'il s'appuie dessus au lieu d'inventer."""
    model = vision_model(cfg)
    if not model:
        return ""
    prompt = (question or "Décris précisément ce que montre cette image : mise en page, textes, couleurs, problèmes visibles "
                          "(texte coupé, éléments qui se chevauchent, contraste faible, images cassées).")
    system = ("Tu es Aurélie, l'IA locale de Jimmy. Tu regardes une capture d'écran ou une image et tu réponds en français, précisément, à la première "
              "personne. Décris seulement ce que tu VOIS vraiment ; si tu n'es pas sûre, dis-le. Cite les couleurs avec leur nom courant (bleu nuit, "
              "orange vif...) et la zone concernée (en haut, à gauche, le bouton...). Quand des mesures exactes te sont données, elles priment sur ton impression.")
    if facts:
        prompt += "\n\nMesures exactes prises sur la page (fiables) :\n" + facts[:1800]
    with vision_session(cfg, model) as eng:
        msg = eng.chat([{"role": "system", "content": system},
                        {"role": "user", "content": [{"type": "text", "text": prompt},
                                                     {"type": "image_url", "image_url": {"url": _data_url(path)}}]}], max_tokens=700)
    return str(msg.get("content") or "").strip()


def inspect(cfg, path: str, question: str = "") -> dict:
    """Tout ce qu'on peut savoir d'une image, en données : {file, w, h, colors, zones, audit, facts, verdict, ocr, vlm, notes}."""
    from . import design, live
    p = check_image(path)
    info = {"file": p.name, "basics": None, "audit": live.load_audit(str(p)), "facts": "", "verdict": [], "ocr": "", "vlm": "", "vlm_model": "", "notes": []}
    try:
        info["basics"] = basics(str(p))
    except Exception as e:  # noqa: BLE001
        info["notes"].append(f"infos de base indisponibles ({e})")
    if info["audit"]:
        info["facts"] = design.format_audit(info["audit"])
        info["verdict"] = design.verdict(info["audit"])
    try:
        info["ocr"] = ocr(str(p))
    except Exception as e:  # noqa: BLE001
        info["notes"].append(f"lecture du texte indisponible ({e})")
    model = vision_model(cfg)
    if model:
        try:
            info["vlm"] = ask_vision(cfg, str(p), question, facts=info["facts"])
            info["vlm_model"] = model
        except Exception as e:  # noqa: BLE001
            info["notes"].append(f"modèle de vision indisponible ({str(e)[:140]})")
    elif not info["audit"]:
        info["notes"].append("aucun modèle de vision n'est installé : je n'ai lu que le texte et les couleurs, je ne peux pas juger l'aspect visuel (alignements, style)")
    else:
        info["notes"].append("pas de modèle de vision : mon jugement repose sur les mesures exactes de la page, pas sur une vraie vue de l'image")
    return info


def judge_reply(info: dict, title: str = "") -> str:
    """La réponse d'Aurélie quand on lui demande de JUGER un rendu : composée par le CODE à partir des mesures et du regard du modèle de vision.
    Elle ne passe pas par le petit modèle de discussion, qui adoucissait les chiffres (« 2,02:1, c'est acceptable » : faux)."""
    from . import design
    a = info.get("audit") or {}
    out = [f"Voilà ce que je vois sur **{title or info.get('file', 'cette page')}** (le rendu est dans la conversation)."]
    if a:
        bg = ", ".join(f"{design.color_name(c)} {c}" for c, _p in (a.get("bg") or [])[:3])
        fg = ", ".join(f"{design.color_name(c)} {c}" for c, _p in (a.get("fg") or [])[:3])
        out.append(f"**Couleurs** : fonds {bg or 'inconnus'} ; textes {fg or 'inconnus'}." + (f" Police : {a['fonts'][0][0]}." if a.get("fonts") else ""))
    elif info.get("basics"):
        out.append("**Couleurs** : " + ", ".join(f"{design.color_name(c)} {c} ({p} %)" for c, p in info["basics"]["colors"][:4]) + ".")
    v = info.get("verdict") or []
    if a:
        out.append("**Verdict des mesures** : " + (", ".join(v) + "." if v else "aucun défaut mesuré (contrastes, texte coupé, chevauchements, images)."))
        for b in (a.get("contrast_bad") or [])[:4]:
            out.append(f"- « {b['text']} » : contraste **{b['ratio']}:1** ({design.color_name(b['fg'])} {b['fg']} sur {design.color_name(b['bg'])} {b['bg']}, {b['size']} px) : "
                       f"insuffisant, il faut au moins {str(b['need']).replace('.', ',')}:1.")
        for c in (a.get("clipped") or [])[:2]:
            out.append(f"- Texte coupé : « {c['text']} » ({c['kind']}).")
        for x, y in (a.get("overlaps") or [])[:2]:
            out.append(f"- Chevauchement : {x} avec {y}.")
        for i in (a.get("stretched") or [])[:2]:
            out.append(f"- Image déformée : {i['src']} (réelle {i['natural']}, affichée {i['shown']}).")
        if a.get("small_count"):
            out.append(f"- {a['small_count']} texte(s) de moins de 12 px (trop petit).")
    if info.get("vlm"):
        out.append(f"**Ce que voit mon modèle de vision** ({info.get('vlm_model', '')}) : " + " ".join(info["vlm"].split())[:900])
        if a:
            out.append("_Si mon regard et les mesures ne sont pas d'accord, ce sont les mesures qui font foi : elles sont prises dans la page elle-même._")
    elif info.get("notes"):
        out.append("_" + info["notes"][-1][0].upper() + info["notes"][-1][1:] + "._")
    return "\n".join(out)


def analyze(cfg, path: str, question: str = "", maxc: int = 4200) -> str:
    """Analyse complète d'une image, en texte pour Aurélie / Jimmy. Dit clairement ce qui a été fait et ce qui manque."""
    from . import design
    info = inspect(cfg, path, question)
    parts = [f"Image : {info['file']}"]
    b = info["basics"]
    if b:
        cols = ", ".join(f"{design.color_name(c)} {c} ({pc} %)" for c, pc in b["colors"])
        parts.append(f"Taille {b['w']}×{b['h']} px, ton {b['tone']}. Couleurs dominantes (mesurées sur les pixels) : {cols}.")
        lab = ("haut", "milieu", "bas"), ("à gauche", "au centre", "à droite")
        parts.append("Répartition des couleurs : " + " ; ".join(
            lab[0][y] + " : " + ", ".join(f"{lab[1][x]} {design.color_name(b['zones'][y][x])}" for x in range(3)) for y in range(3)) + ".")
    if info["facts"]:
        parts.append("MESURES EXACTES prises dans la page au moment de la capture (fiables) :\n" + info["facts"])
        parts.append("VERDICT DES MESURES (à reprendre tel quel, sans l'adoucir) : " + (
            ", ".join(info["verdict"]) + ". Un contraste sous 4,5:1 (3:1 pour un grand texte) n'est JAMAIS acceptable." if info["verdict"] else "aucun défaut mesuré."))
    if info["ocr"] or not any("texte" in n for n in info["notes"]):
        parts.append("Texte lu dans l'image :\n" + (info["ocr"][:1800] or "(aucun texte reconnu)"))
    if info["vlm"]:
        parts.append("Ce que voit le modèle de vision (" + info["vlm_model"] + ") :\n" + info["vlm"][:1600])
    if info["notes"]:
        parts.append("Limites : " + " ; ".join(info["notes"]) + ".")
    return "\n".join(parts)[:maxc]
