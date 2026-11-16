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
    counts, total = {}, 0.0
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            key = (c.red() // 32, c.green() // 32, c.blue() // 32)
            counts[key] = counts.get(key, 0) + 1
            total += 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    n = small.width() * small.height()
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    colors = [("#%02x%02x%02x" % (k[0] * 32 + 16, k[1] * 32 + 16, k[2] * 32 + 16), round(100 * v / n)) for k, v in top]
    lum = total / n
    return {"w": w, "h": h, "colors": colors, "tone": "sombre" if lum < 90 else "clair" if lum > 170 else "moyen", "luma": round(lum)}


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


def vision_model(cfg) -> str:
    return str((cfg.get("vision_model") if cfg is not None else "") or "").strip()


def ask_vision(cfg, path: str, question: str) -> str:
    """Réponse du modèle de vision de LM Studio ('' s'il n'y en a pas de configuré). Lève LocalError s'il ne répond pas."""
    model = vision_model(cfg)
    if not model:
        return ""
    from .engine import Engine
    base = Engine.from_cfg(cfg, start=False)
    eng = Engine(base.base, model)
    msg = eng.chat([{"role": "user", "content": [
        {"type": "text", "text": (question or "Décris précisément ce que montre cette image : mise en page, textes, couleurs, "
                                  "problèmes visibles (texte coupé, éléments qui se chevauchent, images cassées).")},
        {"type": "image_url", "image_url": {"url": _data_url(path)}}]}], max_tokens=700)
    return str(msg.get("content") or "").strip()


def analyze(cfg, path: str, question: str = "", maxc: int = 3500) -> str:
    """Analyse complète d'une image, en texte. Dit clairement ce qui a été fait et ce qui manque."""
    p = check_image(path)
    parts, notes = [f"Image : {p.name}"], []
    try:
        b = basics(str(p))
        cols = ", ".join(f"{c} ({pc} %)" for c, pc in b["colors"])
        parts.append(f"Taille {b['w']}×{b['h']} px, ton {b['tone']}. Couleurs dominantes : {cols}.")
    except Exception as e:  # noqa: BLE001
        notes.append(f"infos de base indisponibles ({e})")
    try:
        txt = ocr(str(p))
        parts.append("Texte lu dans l'image :\n" + (txt[:2400] if txt else "(aucun texte reconnu)"))
    except Exception as e:  # noqa: BLE001
        notes.append(f"lecture du texte indisponible ({e})")
    if vision_model(cfg):
        try:
            ans = ask_vision(cfg, str(p), question)
            if ans:
                parts.append("Ce que voit le modèle de vision :\n" + ans[:1500])
        except Exception as e:  # noqa: BLE001
            notes.append(f"modèle de vision indisponible ({str(e)[:120]})")
    else:
        notes.append("aucun modèle de vision n'est installé : je n'ai lu que le texte et les couleurs, je ne peux pas juger l'aspect visuel (alignements, style)")
    if notes:
        parts.append("Limites : " + " ; ".join(notes) + ".")
    return "\n".join(parts)[:maxc]
