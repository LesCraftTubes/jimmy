"""L'orbe de Jimmy : un cœur lumineux entouré d'anneaux, qui réagit à l'état et à la voix."""
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

COLORS = {
    "loading": (110, 110, 160),
    "idle": (80, 86, 120),
    "muted": (120, 60, 80),
    "wake": (168, 85, 247),
    "listening": (34, 211, 238),
    "thinking": (251, 191, 36),
    "speaking": (232, 77, 245),
    "error": (244, 63, 94),
}


class Orb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self._state = "loading"
        self._palette = dict(COLORS)
        self._color = list(COLORS["loading"])
        self._level = 0.0
        self._ext = 0.0
        self._t = 0.0
        self._t0 = time.perf_counter()
        self._sides_on = True
        self._sats_on = True
        self._psy = 0.0       # cyberpsychose : 0 = calme, 1 = à fond
        self._psy_goal = 0.0
        self._ripples = []   # ondes de choc lancées à chaque changement d'état : instants de départ
        # Petits satellites lumineux : (rayon relatif, phase, vitesse, taille)
        self._sats = [(0.52 + 0.40 * ((i * 37) % 100) / 100.0, i * 2.399, 0.25 + 0.5 * ((i * 53) % 100) / 100.0,
                       1.1 + 1.6 * ((i * 29) % 100) / 100.0) for i in range(30)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_state(self, state: str) -> None:
        new = state if state in self._palette else "idle"
        if new != self._state:
            self._ripples = (self._ripples + [time.perf_counter() - self._t0])[-3:]
        self._state = new

    def set_palette(self, overrides: dict) -> None:
        """Couleurs par état suivant le thème choisi ({} = couleurs d'origine)."""
        self._palette = dict(COLORS)
        self._palette.update(overrides or {})

    def set_options(self, sides: bool = True, sats: bool = True) -> None:
        self._sides_on, self._sats_on = bool(sides), bool(sats)

    def set_psychosis(self, level: float) -> None:
        """0 = rien. Au-dessus : glitch, double image rouge, parasites (tant que le niveau reste haut)."""
        self._psy_goal = max(0.0, min(1.0, level))

    def set_level(self, rms: float) -> None:
        self._ext = max(0.0, min(1.0, rms * 14.0))

    def _tick(self) -> None:
        t = time.perf_counter() - self._t0
        self._t = t
        s = self._state
        if s == "listening":
            target = self._ext
        elif s == "speaking":
            target = 0.30 + 0.30 * abs(math.sin(t * 7.0)) * (0.6 + 0.4 * math.sin(t * 2.3))
        elif s == "thinking":
            target = 0.18 + 0.08 * math.sin(t * 3.0)
        elif s == "wake":
            target = 0.05 + 0.03 * math.sin(t * 1.2)
        else:
            target = 0.02
        self._level += (target - self._level) * 0.2
        self._ext *= 0.9
        self._psy += (self._psy_goal - self._psy) * 0.05
        goal = self._palette.get(s, self._palette["idle"])
        if self._psy > 0.01:   # la couleur vire au rouge néon, par à-coups
            k = self._psy * (0.45 + 0.2 * math.sin(t * 9.0) * math.sin(t * 3.1))
            goal = tuple(goal[i] * (1 - k) + (255, 30, 70)[i] * k for i in range(3))
        for i in range(3):
            self._color[i] += (goal[i] - self._color[i]) * 0.08
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._sides(p)
        if self._psy < 0.02:
            self._scene(p)
        else:
            dpr = self.devicePixelRatioF()
            pix = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.transparent)
            q = QPainter(pix)
            q.setRenderHint(QPainter.Antialiasing, True)
            self._scene(q)
            q.end()
            self._glitch(p, pix, dpr)
        p.end()

    def _sides(self, p) -> None:
        """Flux de données, barres et lasers qui s'étendent à gauche et à droite de l'orbe."""
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        R = min(w, h) / 2.0 - 4
        t, lvl = self._t, self._level
        col = QColor(int(self._color[0]), int(self._color[1]), int(self._color[2]))
        span = cx - R * 1.04
        if span < 20 or not self._sides_on:
            return
        energy = 0.35 + 1.4 * lvl + (0.5 if self._state == "thinking" else 0.0)
        flow = 60 + 160 * energy
        for side in (-1, 1):
            x0 = cx + side * R * 1.04
            for i, dy in enumerate((-0.55, -0.32, -0.14, 0.0, 0.14, 0.32, 0.55)):
                y = cy + dy * R
                reach = span * (0.55 + 0.45 * math.sin(t * 0.7 + i * 1.3 + side) ** 2)
                c = QColor(col)
                for seg in range(12):
                    c.setAlpha(int(60 * (1 - seg / 12) ** 1.5))
                    p.setPen(QPen(c, 1))
                    p.drawLine(QPointF(x0 + side * reach * seg / 12, y), QPointF(x0 + side * reach * (seg + 1) / 12, y))
                pos = (t * flow * (0.6 + 0.15 * i) + i * 53) % max(reach, 1.0)
                c.setAlpha(int(230 * (1 - pos / max(reach, 1.0))))
                p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x0 + side * pos, y), QPointF(x0 + side * (pos + 14 + 20 * energy), y))
            n = int(span // 9)
            for k in range(n):
                f = k / max(n, 1)
                x = x0 + side * (6 + k * 9)
                noise = 0.5 + 0.5 * math.sin(t * (2.2 + 1.7 * math.sin(k * 1.9)) + k * 0.8 + side)
                hh = R * 0.30 * (1 - f) ** 1.2 * (0.12 + noise * (0.3 + 0.9 * energy))
                c = QColor(col)
                c.setAlpha(int(150 * (1 - f)))
                p.setPen(QPen(c, 2.2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x, cy - hh), QPointF(x, cy + hh))
            for k in range(6):
                f = (t * 0.12 * (1 + k * 0.2) + k / 6.0) % 1.0
                yy = cy + (R * 0.78 if k % 2 else -R * 0.78)
                c = QColor(col)
                c.setAlpha(int(140 * (1 - f)))
                p.setPen(QPen(c, 1))
                p.drawRect(QRectF(x0 + side * span * f - 4, yy - 2, 8, 4))

    def _glitch(self, p, pix, dpr) -> None:
        """Cyberpsychose : double image rouge, bandes décalées, parasites, scintillement."""
        w, h = self.width(), self.height()
        t, psy = self._t, self._psy
        rng = random.Random(int(t * 14))
        flicker = 1.0 if rng.random() > 0.08 * psy else 0.55
        off = 3 + 7 * psy * (0.5 + 0.5 * math.sin(t * 17))
        p.setOpacity(0.38 * flicker)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        p.drawPixmap(int(-off), 0, pix)
        p.drawPixmap(int(off), 0, pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setOpacity(flicker)
        burst = (math.sin(t * 2.7) + math.sin(t * 5.3 + 1.3)) > 1.45 - 0.9 * psy
        if burst:
            y = 0
            while y < h:
                bh = rng.randint(6, 26)
                dx = rng.randint(-int(30 * psy) - 4, int(30 * psy) + 4) if rng.random() < 0.55 else 0
                p.drawPixmap(QRectF(dx, y, w, bh), pix, QRectF(0, y * dpr, w * dpr, bh * dpr))
                y += bh
        else:
            p.drawPixmap(0, 0, pix)
        p.setOpacity(1.0)
        p.setPen(QPen(QColor(0, 0, 0, int(55 * psy)), 1))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)
        p.setPen(Qt.NoPen)
        for _ in range(int(30 * psy) + (60 if burst else 0)):
            c = QColor(255, 30, 70, rng.randint(60, 200)) if rng.random() < 0.6 else QColor(34, 211, 238, rng.randint(40, 150))
            p.setBrush(c)
            p.drawRect(QRectF(rng.random() * w, rng.random() * h, rng.randint(2, 18), rng.choice((1, 1, 2))))

    def _scene(self, p) -> None:
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        R = min(w, h) / 2.0 - 4
        t = self._t
        lvl = self._level
        state = self._state
        col = QColor(int(self._color[0]), int(self._color[1]), int(self._color[2]))
        spin = {"thinking": 3.2, "listening": 1.6, "speaking": 1.2}.get(state, 0.6)
        center = QPointF(cx, cy)

        # Halo
        halo = QRadialGradient(center, R)
        c0, c1, c2 = QColor(col), QColor(col), QColor(col)
        c0.setAlpha(int(70 + 120 * lvl))
        c1.setAlpha(int(18 + 20 * lvl))
        c2.setAlpha(0)
        halo.setColorAt(0.0, c0)
        halo.setColorAt(0.45, c1)
        halo.setColorAt(1.0, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(center, R, R)

        # Cœur
        breath = 0.5 + 0.5 * math.sin(t * 1.6)
        core_r = R * (0.26 + 0.015 * breath + 0.10 * lvl)
        core = QRadialGradient(QPointF(cx, cy - core_r * 0.25), core_r * 1.3)
        ca = QColor(255, 255, 255, 235)
        cb = QColor(col)
        cb.setAlpha(230)
        cc = QColor(col).darker(220)
        core.setColorAt(0.0, ca)
        core.setColorAt(0.35, cb)
        core.setColorAt(1.0, cc)
        p.setBrush(QBrush(core))
        p.drawEllipse(center, core_r, core_r)

        # Anneau ondulant (réagit à la voix)
        n = 120
        base = R * 0.46
        amp = R * (0.012 + 0.07 * lvl)
        path = QPainterPath()
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            k = math.sin(a * 5 + t * spin * 2.2) * math.sin(a * 3 - t * 1.3)
            r = base + amp * k * (1 + 0.6 * math.sin(a * 9 + t * 3))
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 220), 2.0))
        p.drawPath(path)

        # Arcs tournants
        specs = [(0.60, 38, 2.2, 70), (0.72, -26, 1.6, 110), (0.86, 14, 1.2, 160)]
        for idx, (rf, speed, width, span) in enumerate(specs):
            rr = R * rf
            rect = QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr)
            ac = QColor(col)
            ac.setAlpha(200 - idx * 45)
            p.setPen(QPen(ac, width, Qt.SolidLine, Qt.RoundCap))
            start0 = t * speed * spin
            for j in range(3):
                p.drawArc(rect, int((start0 + j * 120) * 16), int(span * 16))

        # Graduations extérieures
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 70), 1))
        drift = t * (48 if state == "thinking" else 4)
        for i in range(60):
            a = math.radians(i * 6 + drift)
            r1 = R * 0.93
            r2 = R * (0.96 if i % 5 else 0.985)
            ca_, sa_ = math.cos(a), math.sin(a)
            p.drawLine(QPointF(cx + r1 * ca_, cy + r1 * sa_), QPointF(cx + r2 * ca_, cy + r2 * sa_))

        # Ondes de choc au changement d'état
        for t0 in self._ripples:
            age = t - t0
            if 0 <= age < 1.4:
                k = age / 1.4
                rc = QColor(col)
                rc.setAlpha(int(150 * (1 - k) ** 2))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(rc, 2.4 * (1 - k) + 0.6))
                p.drawEllipse(center, R * (0.30 + 0.68 * k), R * (0.30 + 0.68 * k))
        self._ripples = [t0 for t0 in self._ripples if t - t0 < 1.4]

        # Satellites lumineux (additifs, scintillent, accélèrent quand Jimmy travaille)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        p.setPen(Qt.NoPen)
        speed = {"thinking": 1.6, "speaking": 0.9, "listening": 0.7}.get(state, 0.35)
        for rf, ph, sp, size in (self._sats if self._sats_on else ()):
            a = ph + t * sp * speed
            rr = R * (rf + 0.02 * math.sin(t * 1.3 + ph) + 0.05 * lvl)
            tw = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.1 + ph * 3))
            sc = QColor(col)
            sc.setAlpha(int(40 + 150 * tw))
            p.setBrush(sc)
            p.drawEllipse(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)), size, size)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # Reflet sur le cœur
        gl = QRadialGradient(QPointF(cx - core_r * 0.35, cy - core_r * 0.4), core_r * 0.55)
        gl.setColorAt(0.0, QColor(255, 255, 255, 120))
        gl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gl))
        p.setPen(Qt.NoPen)
        p.drawEllipse(center, core_r, core_r)
