"""Icônes de Jimmy dessinées en vectoriel (angles vifs, trait néon) : même taille, même style,
et elles prennent la couleur du thème. Chaque icône est tracée dans un carré de 24 x 24."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF


def _poly(points, close=True) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    if close:
        path.closeSubpath()
    return path


def _gear() -> QPainterPath:
    pts = []
    for i in range(16):
        a = math.pi * 2 * i / 16 - math.pi / 16
        r = 10.2 if (i // 2) % 2 == 0 else 7.6
        pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
    return _poly(pts)


def draw_icon(p: QPainter, name: str, rect: QRectF, color: QColor, fill_alpha: int = 60) -> None:
    """Dessine l'icône `name` dans `rect` avec la couleur donnée."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    s = min(rect.width(), rect.height()) / 24.0
    p.translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s)
    p.scale(s, s)
    pen = QPen(color, 1.9, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
    p.setPen(pen)
    soft = QColor(color)
    soft.setAlpha(fill_alpha)
    p.setBrush(Qt.NoBrush)

    def stroke(path, fill=False):
        p.setBrush(soft if fill else Qt.NoBrush)
        p.drawPath(path)

    if name == "speaker":
        stroke(_poly([(3, 9), (8, 9), (13, 4.5), (13, 19.5), (8, 15), (3, 15)]), True)
        stroke(_poly([(16, 8.5), (18.5, 12), (16, 15.5)], False))
        stroke(_poly([(19, 5), (22.5, 12), (19, 19)], False))
    elif name == "wave":
        for x, hh in ((3.5, 4), (7, 11), (10.5, 17), (14, 9), (17.5, 14), (21, 5)):
            p.drawLine(QPointF(x, 12 - hh / 2.0), QPointF(x, 12 + hh / 2.0))
    elif name == "play":
        stroke(_poly([(7, 4.5), (19.5, 12), (7, 19.5)]), True)
    elif name == "radar":
        p.drawEllipse(QPointF(12, 12), 2.2, 2.2)
        p.drawArc(QRectF(5, 5, 14, 14), 40 * 16, 100 * 16)
        p.drawArc(QRectF(5, 5, 14, 14), 220 * 16, 100 * 16)
        p.drawArc(QRectF(1.5, 1.5, 21, 21), 40 * 16, 100 * 16)
        p.drawArc(QRectF(1.5, 1.5, 21, 21), 220 * 16, 100 * 16)
    elif name == "repeat":
        stroke(_poly([(4, 12), (4, 7), (19, 7)], False))
        stroke(_poly([(16, 3.5), (20.5, 7), (16, 10.5)], False))
        stroke(_poly([(20, 12), (20, 17), (5, 17)], False))
        stroke(_poly([(8, 13.5), (3.5, 17), (8, 20.5)], False))
    elif name == "long":
        for y, x2 in ((6, 21), (12, 21), (18, 14)):
            p.drawLine(QPointF(3, y), QPointF(x2, y))
        stroke(_poly([(17, 15), (21, 18), (17, 21)], False))
    elif name == "pen":
        stroke(_poly([(4, 20), (5, 14.5), (15.5, 4), (20, 8.5), (9.5, 19)]), True)
        p.drawLine(QPointF(13, 6.5), QPointF(17.5, 11))
    elif name == "gear":
        stroke(_gear(), True)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(12, 12), 3.1, 3.1)
    elif name == "power":
        p.drawArc(QRectF(4, 4.5, 16, 16), 125 * 16, 290 * 16)
        p.drawLine(QPointF(12, 2.5), QPointF(12, 11.5))
    elif name in ("mic", "mic_off"):
        stroke(_poly([(9, 5), (10.5, 2.8), (13.5, 2.8), (15, 5), (15, 12), (13.5, 14), (10.5, 14), (9, 12)]), True)
        stroke(_poly([(5.5, 11), (5.5, 14), (9, 18), (15, 18), (18.5, 14), (18.5, 11)], False))
        p.drawLine(QPointF(12, 18), QPointF(12, 21.5))
        p.drawLine(QPointF(8, 21.5), QPointF(16, 21.5))
        if name == "mic_off":
            slash = QPen(color, 2.4, Qt.SolidLine, Qt.SquareCap)
            p.setPen(slash)
            p.drawLine(QPointF(3.5, 3.5), QPointF(20.5, 20.5))
    elif name == "send":
        stroke(_poly([(2.5, 11.5), (21.5, 3.5), (15, 20.5), (11.5, 13.5)]), True)
        p.drawLine(QPointF(11.5, 13.5), QPointF(21.5, 3.5))
    elif name == "stop":
        stroke(_poly([(5.5, 5.5), (18.5, 5.5), (18.5, 18.5), (5.5, 18.5)]), True)
    elif name == "plus":
        p.drawLine(QPointF(12, 4.5), QPointF(12, 19.5))
        p.drawLine(QPointF(4.5, 12), QPointF(19.5, 12))
    elif name == "terminal":
        stroke(_poly([(2.5, 4.5), (21.5, 4.5), (21.5, 19.5), (2.5, 19.5)]), True)
        stroke(_poly([(6.5, 9), (11, 12), (6.5, 15)], False))
        p.drawLine(QPointF(13, 15.5), QPointF(17.5, 15.5))
    elif name == "folder":
        stroke(_poly([(2.5, 5.5), (9.5, 5.5), (11.5, 8), (21.5, 8), (21.5, 19.5), (2.5, 19.5)]), True)
    p.restore()
