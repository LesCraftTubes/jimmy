"""Icône de Jimmy : un « J » néon dans un hexagone, dessinée en code (aucun fichier image requis)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient

MAGENTA = QColor(255, 43, 214)
CYAN = QColor(0, 240, 255)


def make_pixmap(size: int = 256, cyan=None, magenta=None) -> QPixmap:
    """cyan / magenta : couleurs du thème (None = couleurs d'origine de Jimmy)."""
    CYAN_, MAGENTA_ = (QColor(cyan) if cyan else CYAN), (QColor(magenta) if magenta else MAGENTA)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = size / 2.0
    r = size * 0.46

    hexagon = QPolygonF(
        [QPointF(c + r * math.cos(math.radians(60 * i - 90)), c + r * math.sin(math.radians(60 * i - 90)))
         for i in range(6)]
    )
    glow = QRadialGradient(QPointF(c, c), r)
    glow.setColorAt(0.0, QColor(70, 10, 90) if not magenta else MAGENTA_.darker(330))
    glow.setColorAt(1.0, QColor(10, 4, 22) if not magenta else MAGENTA_.darker(900))
    p.setBrush(glow)
    p.setPen(QPen(MAGENTA_, max(2.0, size * 0.035)))
    p.drawPolygon(hexagon)

    inner = QPolygonF([QPointF(c + (pt.x() - c) * 0.84, c + (pt.y() - c) * 0.84) for pt in hexagon])
    p.setBrush(Qt.NoBrush)
    inner_c = QColor(CYAN_)
    inner_c.setAlpha(150)
    p.setPen(QPen(inner_c, max(1.0, size * 0.012)))
    p.drawPolygon(inner)

    font = QFont("Bahnschrift", 1, QFont.Black)
    font.setPixelSize(int(size * 0.5))
    p.setFont(font)
    rect = QRectF(0, 0, size, size)
    # Décalage façon « glitch » : copie cyan derrière le J magenta.
    off = size * 0.025
    p.setPen(CYAN_)
    p.drawText(rect.translated(-off, off * 0.5), Qt.AlignCenter, "J")
    p.setPen(QColor(255, 255, 255))
    p.drawText(rect.translated(off * 0.4, 0), Qt.AlignCenter, "J")
    p.setPen(MAGENTA_)
    p.drawText(rect.translated(off, -off * 0.3), Qt.AlignCenter, "J")
    p.end()
    return pm


def make_icon(size: int = 256, cyan=None, magenta=None) -> QIcon:
    icon = QIcon()
    for s in sorted({16, 24, 32, 48, 64, 128, 256, size}):
        icon.addPixmap(make_pixmap(s, cyan, magenta))
    return icon


if __name__ == "__main__":
    # python icon.py : écrit jimmy.ico (utilisé pour le .exe et le raccourci).
    import sys
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    out = Path(__file__).resolve().parent / "jimmy.ico"
    print("OK" if make_pixmap(256).save(str(out), "ICO") else "échec", out)
