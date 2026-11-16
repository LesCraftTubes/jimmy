"""Audit visuel d'une page affichée : les MESURES exactes que ni un modèle de vision ni la lecture du texte ne donnent.

Prises directement dans la page réellement dessinée par le navigateur d'Aurélie (styles calculés), donc fiables :
- la palette : couleurs de fond et de texte, avec leur part de la surface et leur NOM (« bleu nuit », « orange vif »...) ;
- les contrastes texte / fond (norme WCAG : 4,5 pour du texte normal, 3 pour un grand texte), avec les pires cas ;
- les polices et les tailles (texte trop petit) ;
- ce qui se chevauche, ce qui est coupé, ce qui dépasse de l'écran ;
- les images déformées ou étirées (floues), les images cassées ;
- la structure : en-tête, menu, zones, colonnes.

Ces faits servent seuls (sans modèle de vision) et sont donnés au modèle de vision pour qu'il s'appuie dessus.
"""
from __future__ import annotations

import colorsys
import json
import re

AUDIT_JS = r"""(() => {
  const vw = innerWidth, vh = innerHeight, d = document;
  const parse = c => { const m = String(c).match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, base) => ({ r: top.r * top.a + base.r * (1 - top.a), g: top.g * top.a + base.g * (1 - top.a), b: top.b * top.a + base.b * (1 - top.a), a: 1 });
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/)[0] : '');
  /* fond réel d'un élément : on remonte jusqu'à un fond opaque ; image ou dégradé = non mesurable */
  const bgOf = e => { let layers = [], unknown = false, n = e;
    while (n && n.nodeType === 1) { const s = getComputedStyle(n); if (s.backgroundImage && s.backgroundImage !== 'none') unknown = true;
      const c = parse(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 0.99) break; } n = n.parentElement; }
    let base = { r: 255, g: 255, b: 255, a: 1 }; for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base); return { c: base, unknown }; };
  const bgArea = {}, fgArea = {}, fonts = {}, worst = [], small = [], clipped = [], blurry = [], stretched = [], broken = [];
  let total = vw * vh, textLen = 0;
  const q = c => hex({ r: Math.round(c.r / 17) * 17, g: Math.round(c.g / 17) * 17, b: Math.round(c.b / 17) * 17 });
  const all = [...d.querySelectorAll('body, body *')].filter(vis);
  for (const e of all) {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    const w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)), h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    const bc = parse(s.backgroundColor);
    if (bc && bc.a > 0.5 && w * h > 0) { const k = q(bc); bgArea[k] = (bgArea[k] || 0) + w * h / (e === d.body ? 1 : 1); }
    const own = [...e.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (own.length) {
      const t = own.map(n => n.textContent.trim()).join(' '), fg0 = parse(s.color), fs = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 700;
      if (!fg0) continue; textLen += t.length;
      const bg = bgOf(e), fg = over(fg0, bg.c), k = q(fg); fgArea[k] = (fgArea[k] || 0) + t.length;
      const fam = s.fontFamily.split(',')[0].replace(/["']/g, '').trim(); fonts[fam] = (fonts[fam] || 0) + t.length;
      const big = fs >= 24 || (fs >= 18.66 && bold), cr = ratio(fg, bg.c), need = big ? 3 : 4.5;
      if (cr < need && r.bottom > 0 && r.top < vh * 3) worst.push({ el: sel(e), text: t.slice(0, 40), ratio: Math.round(cr * 100) / 100, need, fg: hex(fg), bg: hex(bg.c), size: Math.round(fs), approx: bg.unknown });
      if (fs < 12 && r.top < vh * 3) small.push({ el: sel(e), text: t.slice(0, 30), size: Math.round(fs) });
      if ((s.overflow === 'hidden' || s.textOverflow === 'ellipsis') && e.scrollWidth > e.clientWidth + 2 && e.clientWidth > 20) clipped.push({ el: sel(e), text: t.slice(0, 40), kind: s.textOverflow === 'ellipsis' ? 'coupé avec « … »' : 'coupé' });
      else if (s.overflow === 'hidden' && e.scrollHeight > e.clientHeight + 4 && e.clientHeight > 12) clipped.push({ el: sel(e), text: t.slice(0, 40), kind: 'coupé en hauteur' });
    }
    if (e.tagName === 'IMG' && e.complete) {
      if (e.naturalWidth === 0) broken.push(e.getAttribute('src') || '');
      else { const rw = r.width, rh = r.height, ar = (e.naturalWidth / e.naturalHeight) / (rw / rh);
        if (ar > 1.18 || ar < 0.85) stretched.push({ el: sel(e), src: (e.getAttribute('src') || '').split('/').pop().slice(0, 40), natural: e.naturalWidth + '×' + e.naturalHeight, shown: Math.round(rw) + '×' + Math.round(rh) });
        if (rw > e.naturalWidth * 1.5 && rw > 120) blurry.push({ el: sel(e), src: (e.getAttribute('src') || '').split('/').pop().slice(0, 40), natural: e.naturalWidth, shown: Math.round(rw) }); }
    }
  }
  /* chevauchements entre blocs de texte */
  const boxes = all.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1) && getComputedStyle(e).position !== 'static' || ['H1','H2','H3','P','A','BUTTON','LI','SPAN'].includes(e.tagName))
    .filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1)).slice(0, 220).map(e => ({ e, r: e.getBoundingClientRect() }));
  const overlaps = [];
  for (let i = 0; i < boxes.length && overlaps.length < 6; i++) for (let j = i + 1; j < boxes.length && overlaps.length < 6; j++) {
    const a = boxes[i], b = boxes[j]; if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
    const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (w > 4 && h > 4) { const sm = Math.min(a.r.width * a.r.height, b.r.width * b.r.height); if (w * h > 0.25 * sm) overlaps.push([sel(a.e) + ' « ' + a.e.innerText.trim().slice(0, 25) + ' »', sel(b.e) + ' « ' + b.e.innerText.trim().slice(0, 25) + ' »']); }
  }
  const agg = (o, n) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n);
  const bgTot = Object.values(bgArea).reduce((a, b) => a + b, 0) || 1, fgTot = Object.values(fgArea).reduce((a, b) => a + b, 0) || 1, fTot = Object.values(fonts).reduce((a, b) => a + b, 0) || 1;
  const bodyBg = bgOf(d.body).c;
  const lands = ['header', 'nav', 'main', 'aside', 'footer', 'section'].flatMap(t => [...d.querySelectorAll(t)].slice(0, 3).filter(vis).map(e => { const r = e.getBoundingClientRect(); return { tag: t, x: Math.round(100 * Math.max(0, r.left) / vw), y: Math.round(r.top + scrollY), w: Math.round(100 * Math.min(r.width, vw) / vw), h: Math.round(r.height) }; }));
  const cols = new Set(all.filter(e => { const s = getComputedStyle(e); return s.display === 'flex' || s.display === 'grid'; }).map(e => e.children.length).filter(n => n >= 2 && n <= 6)).size;
  return JSON.stringify({
    bg_page: hex(bodyBg), bg: agg(bgArea, 6).map(([c, v]) => [c, Math.round(100 * v / bgTot)]), fg: agg(fgArea, 5).map(([c, v]) => [c, Math.round(100 * v / fgTot)]),
    fonts: agg(fonts, 4).map(([f, v]) => [f, Math.round(100 * v / fTot)]), contrast_bad: worst.sort((a, b) => a.ratio - b.ratio).slice(0, 8), contrast_bad_count: worst.length,
    small_text: small.slice(0, 5), small_count: small.length, clipped: clipped.slice(0, 5), overlaps, stretched: stretched.slice(0, 4), blurry: blurry.slice(0, 4), broken: broken.slice(0, 4),
    landmarks: lands, flex_groups: cols, text_chars: textLen, viewport: [vw, vh], page_h: d.documentElement.scrollHeight });
})()"""


# ------------------------------------------------------------------ noms de couleurs
def color_name(hexc: str) -> str:
    """Nom courant d'une couleur (« bleu nuit », « gris clair », « orange vif »...)."""
    m = re.match(r"^#?([0-9a-fA-F]{6})$", str(hexc or ""))
    if not m:
        return "couleur inconnue"
    v = m.group(1)
    r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h *= 360
    if l < 0.09:
        return "noir"
    if l > 0.975:
        return "blanc"
    if l > 0.9 and s < 0.25:
        return "blanc cassé"
    if s < 0.10:
        return "gris très foncé" if l < 0.22 else "gris foncé" if l < 0.4 else "gris" if l < 0.62 else "gris clair"
    if h < 15 or h >= 345:
        base = "rouge"
    elif h < 40:
        base = "orange" if l > 0.35 else "marron"
    elif h < 65:
        base = "jaune" if l > 0.4 else "ocre"
    elif h < 90:
        base = "vert jaune"
    elif h < 165:
        base = "vert"
    elif h < 195:
        base = "turquoise"
    elif h < 250:
        base = "bleu"
    elif h < 290:
        base = "violet"
    elif h < 345:
        base = "rose" if l > 0.5 else "magenta"
    else:
        base = "rouge"
    if base == "marron":
        return "marron clair" if l > 0.5 else "marron"
    tone = " nuit" if (l < 0.22 and base in ("bleu", "violet")) else " foncé" if l < 0.28 else " clair" if l > 0.72 else " vif" if s > 0.7 and 0.4 < l < 0.65 else ""
    return base + tone


def names(pairs) -> str:
    return ", ".join(f"{color_name(c)} {c} ({p} %)" for c, p in pairs)


# ------------------------------------------------------------------ texte lisible
def format_audit(a: dict) -> str:
    """Les mesures, en phrases courtes (pour Aurélie, pour Jimmy, ou pour le modèle de vision)."""
    if not a:
        return "Aucune mesure disponible."
    out = [f"Fond de la page : {color_name(a.get('bg_page', ''))} {a.get('bg_page', '')}."]
    if a.get("bg"):
        out.append("Couleurs de fond (part de la surface) : " + names(a["bg"]) + ".")
    if a.get("fg"):
        out.append("Couleurs du texte (part du texte) : " + names(a["fg"]) + ".")
    if a.get("fonts"):
        out.append("Polices : " + ", ".join(f"{f} ({p} %)" for f, p in a["fonts"]) + ".")
    bad = a.get("contrast_bad") or []
    if bad:
        out.append(f"CONTRASTE INSUFFISANT sur {a.get('contrast_bad_count', len(bad))} texte(s) (minimum 4,5 pour un texte normal, 3 pour un grand texte). Les pires : " + " ; ".join(
            f"« {b['text']} » {b['ratio']}:1 ({color_name(b['fg'])} {b['fg']} sur {color_name(b['bg'])} {b['bg']}, {b['size']} px"
            + (", fond en image ou dégradé : mesure approximative" if b.get("approx") else "") + ")" for b in bad[:5]) + ".")
    else:
        out.append("Contrastes texte / fond : tous suffisants.")
    if a.get("small_count"):
        out.append(f"{a['small_count']} texte(s) trop petit(s) (< 12 px), par exemple : " + ", ".join(f"« {s['text']} » {s['size']} px" for s in a.get("small_text", [])[:3]) + ".")
    if a.get("clipped"):
        out.append("Texte coupé : " + " ; ".join(f"{c['el']} « {c['text']} » ({c['kind']})" for c in a["clipped"][:4]) + ".")
    if a.get("overlaps"):
        out.append("Éléments de texte qui se chevauchent : " + " ; ".join(f"{x} / {y}" for x, y in a["overlaps"][:3]) + ".")
    if a.get("stretched"):
        out.append("Images déformées : " + " ; ".join(f"{i['src']} (réelle {i['natural']}, affichée {i['shown']})" for i in a["stretched"]) + ".")
    if a.get("blurry"):
        out.append("Images agrandies (donc floues) : " + " ; ".join(f"{i['src']} ({i['natural']} px affichée en {i['shown']} px)" for i in a["blurry"]) + ".")
    if a.get("broken"):
        out.append("Images cassées : " + ", ".join(a["broken"]) + ".")
    lands = a.get("landmarks") or []
    if lands:
        out.append("Structure : " + ", ".join(f"{l['tag']} ({l['w']} % de large, à {l['y']} px du haut)" for l in lands[:7]) + ".")
    return "\n".join(out)


def verdict(a: dict) -> list:
    """Les problèmes de rendu trouvés, en une liste courte (vide = rien à signaler)."""
    out = []
    if a.get("contrast_bad"):
        out.append(f"{a.get('contrast_bad_count', 0)} texte(s) au contraste insuffisant")
    if a.get("small_count"):
        out.append(f"{a['small_count']} texte(s) trop petit(s)")
    if a.get("clipped"):
        out.append(f"{len(a['clipped'])} texte(s) coupé(s)")
    if a.get("overlaps"):
        out.append(f"{len(a['overlaps'])} chevauchement(s)")
    if a.get("stretched"):
        out.append(f"{len(a['stretched'])} image(s) déformée(s)")
    if a.get("broken"):
        out.append(f"{len(a['broken'])} image(s) cassée(s)")
    return out


def parse(raw) -> dict:
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return {}
