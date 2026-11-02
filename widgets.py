"""Éléments visuels cyberpunk de Jimmy : boutons à coins coupés (aplats néon, sans dégradé), cadres « HUD »
à crochets d'angle, icônes dessinées, et effets de glitch léger pour les changements de discussion."""
import math
import random

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QPushButton, QWidget

from icons import draw_icon

# Couleurs du thème (modifiables dans Réglages > Apparence).
THEME = {"accent": "#22d3ee", "accent2": "#7c3aed", "effects": True}


def _accent(color):
    return QColor(THEME["accent"] if color in (None, "#22d3ee") else color)


class GlowButton(QPushButton):
    """Bouton à coins coupés, contour néon, balayage lumineux au survol, halo qui pulse quand il est actif."""

    def __init__(self, text: str = "", accent=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._accent_arg = accent
        self._icon = None
        self._active = False
        self._hover = 0.0
        self._sweep = -1.0
        self._fx = QGraphicsDropShadowEffect(self)
        self._fx.setOffset(0, 0)
        self._fx.setBlurRadius(0)
        self._fx.setColor(_accent(accent))
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"blurRadius", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._pulse = QPropertyAnimation(self._fx, b"blurRadius", self)
        self._pulse.setDuration(1100)
        self._pulse.setStartValue(6)
        self._pulse.setKeyValueAt(0.5, 34)
        self._pulse.setEndValue(6)
        self._pulse.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse.setLoopCount(-1)
        self._sw = QVariantAnimation(self)
        self._sw.setDuration(520)
        self._sw.setStartValue(-0.2)
        self._sw.setEndValue(1.2)
        self._sw.setEasingCurve(QEasingCurve.OutCubic)
        self._sw.valueChanged.connect(self._on_sweep)
        self.toggled.connect(lambda _on: self._glow_to(self._rest()))

    # ------------------------------------------------------------ état
    def set_icon(self, name) -> None:
        self._icon = name
        self.update()

    def set_accent(self, color: str) -> None:
        self._accent_arg = color
        self._fx.setColor(_accent(color))
        self.update()

    def refresh_theme(self) -> None:
        self._fx.setColor(_accent(self._accent_arg))
        self.update()

    def _rest(self) -> float:
        return 12 if self.isChecked() else 0

    def _glow_to(self, value: float) -> None:
        if self._active:
            return
        self._anim.stop()
        self._anim.setStartValue(self._fx.blurRadius())
        self._anim.setEndValue(value)
        self._anim.start()

    def _on_sweep(self, v) -> None:
        self._sweep = float(v)
        self.update()

    def set_active(self, on: bool) -> None:
        """Mode actif (ex. Jimmy écoute) : couleur pleine + pulsation lumineuse."""
        on = bool(on)
        if on == self._active:
            return
        self._active = on
        self.setProperty("active", on)
        if on:
            self._anim.stop()
            self._pulse.start()
        else:
            self._pulse.stop()
            self._glow_to(self._rest())
        self.update()

    # ------------------------------------------------------------ souris
    def mousePressEvent(self, e) -> None:
        self._anim.stop()
        self._anim.setDuration(90)
        self._anim.setStartValue(self._fx.blurRadius())
        self._anim.setEndValue(48)
        self._anim.start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._anim.setDuration(380)
        self._glow_to(22 if self.underMouse() else self._rest())
        super().mouseReleaseEvent(e)

    def enterEvent(self, e) -> None:
        self._hover = 1.0
        self._glow_to(22)
        if THEME.get("effects", True):
            self._sw.stop()
            self._sw.start()
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = 0.0
        self._glow_to(self._rest())
        self.update()
        super().leaveEvent(e)

    # ------------------------------------------------------------ dessin
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        acc = _accent(self._accent_arg)
        w, h = self.width() - 2.0, self.height() - 2.0
        c = 6.0 if w < 56 else 10.0
        poly = QPolygonF([QPointF(1 + c, 1), QPointF(1 + w, 1), QPointF(1 + w, 1 + h - c),
                          QPointF(1 + w - c, 1 + h), QPointF(1, 1 + h), QPointF(1, 1 + c)])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()

        enabled = self.isEnabled()
        down = self.isDown()
        checked = self.isChecked()
        hover = self._hover > 0 and enabled
        primary = self.objectName() == "primary"

        # fond : aplat sombre teinté par la couleur d'accent (aucun dégradé)
        base = QColor(15, 17, 29)

        def tint(alpha):
            t = QColor(acc)
            t.setAlpha(alpha)
            return t

        if self._active:
            fill = QColor(acc)
        else:
            alpha = 0
            if primary:
                alpha = 92 if hover else 62
            elif checked:
                alpha = 58 if hover else 42
            elif hover:
                alpha = 34
            if down:
                alpha += 30
            fill = base
        p.fillPath(path, fill)
        if not self._active and alpha:
            p.fillPath(path, tint(alpha))

        # balayage lumineux au survol
        if THEME.get("effects", True) and 0.0 <= self._sweep <= 1.1 and hover:
            p.save()
            p.setClipPath(path)
            x = self._sweep * (self.width() + 40) - 20
            sg = QLinearGradient(x - 18, 0, x + 18, 0)
            sw = QColor(255, 255, 255, 0)
            mid = QColor(acc.lighter(160))
            mid.setAlpha(100)
            sg.setColorAt(0, sw)
            sg.setColorAt(0.5, mid)
            sg.setColorAt(1, sw)
            p.fillRect(QRectF(x - 18, 0, 36, self.height()), sg)
            p.restore()

        # contour néon
        edge = QColor(acc)
        edge.setAlpha(255 if (hover or checked or self._active or primary) else 105)
        if not enabled:
            edge = QColor(60, 66, 90)
        p.setPen(QPen(edge, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if enabled:
            p.setPen(QPen(QColor(acc.lighter(150)), 2.4, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(QPointF(1, 1 + c), QPointF(1 + c, 1))
            p.drawLine(QPointF(1 + w, 1 + h - c), QPointF(1 + w - c, 1 + h))

        # contenu : icône dessinée et/ou texte
        if not enabled:
            tc = QColor(90, 96, 125)
        elif self._active:
            tc = QColor(6, 20, 28)
        elif primary:
            tc = QColor(255, 255, 255)
        elif checked:
            tc = QColor(acc.lighter(170))
        elif hover:
            tc = QColor(255, 255, 255)
        else:
            tc = QColor(214, 220, 238)
        text = self.text()
        f = QFont(self.font())
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.5 if w > 56 else 0)
        p.setFont(f)
        dy = 1 if down else 0
        if self._icon:
            isz = 19.0 if not text else 16.0
            tw = QFontMetrics(f).horizontalAdvance(text) if text else 0
            gap = 8.0 if text else 0.0
            total = isz + gap + tw
            x0 = (self.width() - total) / 2.0
            draw_icon(p, self._icon, QRectF(x0, (self.height() - isz) / 2.0 + dy, isz, isz), tc)
            if text:
                p.setPen(tc)
                p.drawText(QRectF(x0 + isz + gap, dy, tw + 4, self.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        else:
            p.setPen(tc)
            p.drawText(QRectF(0, dy, self.width(), self.height()), Qt.AlignCenter, text)
        p.end()


class HudFrame(QFrame):
    """Cadre avec crochets lumineux dans les angles (style écran de visée / HUD)."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(THEME["accent"])
        w, h, L = self.width() - 1, self.height() - 1, 16
        col.setAlpha(230)
        p.setPen(QPen(col, 2))
        for x, y, dx, dy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
            p.drawLine(x, y, x + dx * L, y)
            p.drawLine(x, y, x, y + dy * L)
        p.end()


class SweepOverlay(QWidget):
    """Glitchs « cyberpsychose » par-dessus toute la fenêtre : morceaux d'écran qui se décalent, double image
    cyan/magenta, déchirures et parasites. Deux modes : « switch » (changement de discussion : balayage + glitch
    sur la zone de texte, repart de zéro si on rechange vite) et « micro » (apparition aléatoire de temps en temps)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._v = 0.0
        self._boost = 1.0
        self._kind = "switch"
        self._pix = None
        self._cy = None
        self._mg = None
        self._region = QRectF()
        self._rng = random.Random()
        self._seed = 0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self._done)
        self.hide()

    def running(self) -> bool:
        return self._anim.state() == QVariantAnimation.Running

    def cancel(self) -> None:
        self._anim.stop()
        self._done()

    def play(self, kind: str = "switch", region=None, boost: float = 1.0) -> None:
        """kind « switch » : relance toujours l'effet depuis le début ; « micro » : ignoré si un effet tourne."""
        if not THEME.get("effects", True):
            return
        if self.running():
            if kind == "micro":
                return
            self.cancel()                      # on change de page en plein effet : on repart de zéro
        par = self.parentWidget()
        self.hide()                            # la capture ne doit pas contenir l'effet précédent
        pix = par.grab()
        w, h = par.width(), par.height()
        self._pix = pix
        for attr, color in (("_cy", QColor(0, 255, 255)), ("_mg", QColor(255, 0, 255))):
            t = pix.copy()
            q = QPainter(t)
            q.setCompositionMode(QPainter.CompositionMode_Multiply)
            q.fillRect(QRectF(0, 0, w, h), color)
            q.end()
            setattr(self, attr, t)
        self._kind = kind
        self._boost = max(1.0, boost)
        self._region = QRectF(region) if region is not None else QRectF(0, 0, w, h)
        self._seed = random.randint(0, 100_000)
        self._anim.setDuration(1250 if kind == "switch" else int(560 * (0.8 + 0.5 * self._boost)))
        self.setGeometry(par.rect())
        self.raise_()
        self.show()
        self._anim.start()

    def _done(self) -> None:
        self._pix = self._cy = self._mg = None
        self.hide()

    def _tick(self, v) -> None:
        self._v = float(v)
        self.update()

    @staticmethod
    def _smooth(x: float) -> float:
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    def _block(self, p, rect: QRectF, dx: float, chroma: float, alpha: float) -> None:
        """Un morceau d'écran décalé (avec double image cyan / magenta de chaque côté)."""
        dpr = self._pix.devicePixelRatio() or 1.0
        src = QRectF(rect.x() * dpr, rect.y() * dpr, rect.width() * dpr, rect.height() * dpr)
        if chroma > 0:
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            p.setOpacity(0.75 * alpha)
            p.drawPixmap(rect.translated(dx - chroma, 0), self._cy, src)
            p.drawPixmap(rect.translated(dx + chroma, 0), self._mg, src)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setOpacity(alpha)
        p.drawPixmap(rect.translated(dx, 0), self._pix, src)

    def _glitch_layer(self, p, area: QRectF, power: float, rng) -> None:
        """Rectangles décalés, déchirures fines, pixels parasites : `power` de 0 à 1."""
        if power <= 0.02:
            return
        n = int(2 + 9 * power)
        for _ in range(n):
            bw = rng.randint(70, int(max(120, area.width() * 0.55)))
            bh = rng.randint(3, int(6 + 34 * power))
            x = area.x() + rng.random() * max(1.0, area.width() - bw)
            y = area.y() + rng.random() * max(1.0, area.height() - bh)
            dx = rng.choice((-1, 1)) * rng.randint(8, int(14 + 70 * power))
            self._block(p, QRectF(x, y, bw, bh), dx, rng.randint(2, int(3 + 6 * power)), 0.95)
        for _ in range(int(1 + 3 * power)):      # déchirures fines sur toute la largeur
            bh = rng.randint(1, 4)
            y = area.y() + rng.random() * max(1.0, area.height() - bh)
            self._block(p, QRectF(area.x(), y, area.width(), bh), rng.choice((-1, 1)) * rng.randint(10, 60), 0, 0.9)
        p.setOpacity(1.0)
        p.setPen(Qt.NoPen)
        for _ in range(int(14 + 70 * power)):    # parasites
            r = rng.random()
            col = QColor(0, 255, 255, rng.randint(80, 220)) if r < 0.4 else \
                QColor(255, 0, 200, rng.randint(80, 220)) if r < 0.75 else QColor(255, 255, 255, rng.randint(60, 180))
            p.setBrush(col)
            p.drawRect(QRectF(area.x() + rng.random() * area.width(), area.y() + rng.random() * area.height(),
                              rng.randint(2, 22), rng.choice((1, 1, 2, 3))))

    def paintEvent(self, _event) -> None:
        if self._pix is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        v = self._v
        step = int(v * self._anim.duration() / 55)          # nouvelle disposition ~ toutes les 55 ms
        rng = self._rng
        rng.seed(self._seed + step)
        acc = QColor(THEME["accent"])
        if self._kind == "switch":
            r = self._region
            p.setClipRect(r)
            run = 0.60
            y = r.y() + self._smooth(min(1.0, v / run)) * r.height()
            fade = 1.0 if v < run else (1.0 - self._smooth((v - run) / (1 - run)))
            g = QLinearGradient(0, y - 140, 0, y)
            c0, c1 = QColor(acc), QColor(acc)
            c0.setAlpha(0)
            c1.setAlpha(int(70 * fade))
            g.setColorAt(0, c0)
            g.setColorAt(1, c1)
            p.fillRect(QRectF(r.x(), max(r.y(), y - 140), r.width(), min(140.0, y - r.y())), g)
            line = QColor(acc.lighter(160))
            line.setAlpha(int(240 * fade))
            p.setPen(QPen(line, 2))
            p.drawLine(int(r.x()), int(y), int(r.right()), int(y))
            # glitch : fort au début, puis qui s'éteint avec la ligne
            burst = fade * (1.0 if v < 0.3 else 0.6)
            if rng.random() < 0.85:
                self._glitch_layer(p, r, 0.75 * burst, rng)
        else:
            env = math.sin(math.pi * v)
            if rng.random() < min(0.95, 0.75 + 0.1 * (self._boost - 1)):   # saccades : l'effet « saute » d'une image à l'autre
                self._glitch_layer(p, self._region, min(1.5, (0.35 + 0.65 * env) * self._boost), rng)
        p.setOpacity(1.0)
        p.end()
