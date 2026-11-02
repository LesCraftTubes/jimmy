"""Thème complet de Jimmy : une seule couleur d'accent recolore toute l'interface, la discussion et l'orbe."""
import colorsys
import re

from PySide6.QtGui import QColor

CYAN = "#22d3ee"
_CYAN_H = colorsys.rgb_to_hsv(0x22 / 255, 0xD3 / 255, 0xEE / 255)[0]
_STATE = {"accent": CYAN}


def set_accent(hexcolor: str) -> None:
    _STATE["accent"] = hexcolor


def accent() -> str:
    return _STATE["accent"]


def _is_default() -> bool:
    return _STATE["accent"].lower() == CYAN


def _hue() -> float:
    c = QColor(_STATE["accent"])
    return colorsys.rgb_to_hsv(c.redF(), c.greenF(), c.blueF())[0]


def shift_rgb(r: int, g: int, b: int):
    """Recolore une couleur du thème d'origine (cyan et fonds bleutés) vers la couleur d'accent."""
    if _is_default():
        return r, g, b
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    ah = _hue()
    cyan_family = 0.40 < h < 0.60 and s > 0.40 and v >= 0.35
    dark_bg = v < 0.35 and s > 0.15
    light_text = v >= 0.5 and s <= 0.35
    if cyan_family:
        h = ah
    elif dark_bg:
        h, s = ah, min(0.62, s * 1.05)
    elif light_text:
        h, s = ah, max(s, 0.10)
    else:
        return r, g, b          # rouge d'alerte, jaune d'avertissement, violet : on ne touche pas
    rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
    return int(rr * 255), int(gg * 255), int(bb * 255)


def shift_hex(color: str) -> str:
    if color.lower() == CYAN:
        return _STATE["accent"]
    c = QColor(color)
    r, g, b = shift_rgb(c.red(), c.green(), c.blue())
    return QColor(r, g, b).name()


_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_RGB = re.compile(r"(rgba?\()\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def themed_text(css: str) -> str:
    """Recolore toutes les couleurs (#rrggbb et rgb()/rgba()) d'un morceau de QSS ou de HTML."""
    if _is_default():
        return css
    css = _HEX.sub(lambda m: shift_hex(m.group(0)), css)
    return _RGB.sub(lambda m: "%s%d, %d, %d" % ((m.group(1),) + shift_rgb(int(m.group(2)), int(m.group(3)), int(m.group(4)))), css)


def orb_colors(accent2: str) -> dict:
    """Couleurs de l'orbe par état, dérivées de l'accent (le cyan d'origine reste inchangé)."""
    if _is_default():
        return {}
    a = QColor(_STATE["accent"])
    h, s, v = colorsys.rgb_to_hsv(a.redF(), a.greenF(), a.blueF())

    def hsv(hh, ss, vv):
        r, g, b = colorsys.hsv_to_rgb(hh % 1.0, max(0, min(1, ss)), max(0, min(1, vv)))
        return int(r * 255), int(g * 255), int(b * 255)

    c2 = QColor(accent2)
    return {
        "loading": hsv(h, s * 0.35, 0.62),
        "idle": hsv(h, s * 0.45, 0.48),
        "wake": (c2.red(), c2.green(), c2.blue()),
        "listening": (a.red(), a.green(), a.blue()),
        "speaking": hsv(h + 0.09, s * 0.9, min(1.0, v + 0.05)),
        "thinking": hsv(h - 0.10, 0.75, 1.0),
    }
