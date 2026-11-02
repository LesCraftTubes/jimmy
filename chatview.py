"""Zone de discussion de Jimmy : markdown lisible, blocs de code avec bouton « Copier »,
et texte qui s'écrit en direct pendant que Jimmy parle (effet « décodage » cyber)."""
import html
import random
import re
import time

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser

import theme
from textutils import prepare_markdown

_CODE_RE = re.compile(r"```([\w+#.-]*)[^\n]*\n(.*?)```", re.S)
_GLYPHS = "▓▒░<>/\\|_#@$%&01ア力ヌ"

DOC_CSS = """
p { margin-top: 2px; margin-bottom: 6px; }
a { color: #22d3ee; }
code { color: #a5f3fc; font-family: Consolas, monospace; }
"""


def _insert(cur, html_text: str) -> None:
    cur.insertHtml(theme.themed_text(html_text))


class ChatView(QTextBrowser):
    copied = Signal(str)

    def apply_theme(self) -> None:
        self.document().setDefaultStyleSheet(theme.themed_text(DOC_CSS))

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self.document().setDefaultStyleSheet(theme.themed_text(DOC_CSS))
        self.document().setDocumentMargin(14)
        self._snippets = []
        # État de l'écriture en direct
        self._live_header = None
        self._live_start = None
        self._done_text = ""
        self._current = ""
        self._shown = 0.0
        self._chunk_t0 = 0.0
        self._duration = 1.0
        self._marks = []
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    # ---------------------------------------------------------------- helpers
    def _end_cursor(self) -> QTextCursor:
        cur = self.textCursor()
        cur.movePosition(QTextCursor.End)
        return cur

    def _scroll(self) -> None:
        if self.textCursor().hasSelection():
            return           # tu sélectionnes du texte : la vue ne bouge pas
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _header(self, cur: QTextCursor, label: str, color: str) -> None:
        if not self.document().isEmpty():
            cur.insertBlock()
            _insert(cur, "<span style='font-size:6px;'>&nbsp;</span>")
            cur.insertBlock()
        _insert(cur, 
            f'<span style="color:{color};font-weight:700;font-size:12px;'
            f'font-family:Consolas;letter-spacing:2px;">▸ {label}</span>'
        )
        cur.insertBlock()

    def clear(self) -> None:
        self._timer.stop()
        self._live_header = self._live_start = None
        self._snippets = []
        super().clear()

    # ---------------------------------------------------------------- messages
    def add_user(self, text: str) -> None:
        cur = self._end_cursor()
        self._header(cur, "TOI", "#22d3ee")
        _insert(cur, 
            '<span style="color:#d6f6fb;">' + html.escape(text).replace("\n", "<br>") + "</span>"
        )
        self._scroll()

    def add_system(self, text: str) -> None:
        cur = self._end_cursor()
        if not self.document().isEmpty():
            cur.insertBlock()
        _insert(cur, 
            f'<span style="color:#6b7190;font-size:12px;font-family:Consolas;">// {html.escape(text)}</span>'
        )
        self._scroll()

    def add_step(self, text: str, first: bool = False) -> None:
        """Étape de travail (lecture, modification...) : discrète, jamais lue à voix haute."""
        cur = self._end_cursor()
        if first:
            self._header(cur, "ÉTAPES", "#5eead4")
        elif not self.document().isEmpty():
            cur.insertBlock()
        kind, _, detail = text.partition(" · ")
        _insert(cur, 
            '<span style="font-family:Consolas;font-size:12px;">'
            '<span style="color:#2dd4bf;">&nbsp;&nbsp;⟩&nbsp;</span>'
            f'<span style="color:#5eead4;font-weight:700;">{html.escape(kind)}</span>'
            + (f'<span style="color:#a3b1c6;">&nbsp;&nbsp;{html.escape(detail)}</span>' if detail else "")
            + "</span>"
        )
        self._scroll()

    def add_assistant(self, text: str) -> None:
        cur = self._end_cursor()
        self._header(cur, "JIMMY", "#e84df5")
        self._insert_body(cur, text)
        self._scroll()

    def _insert_body(self, cur: QTextCursor, text: str) -> None:
        pos = 0
        for m in _CODE_RE.finditer(text):
            self._insert_markdown(cur, text[pos:m.start()])
            self._insert_code(cur, m.group(1), m.group(2).rstrip("\n"))
            pos = m.end()
        self._insert_markdown(cur, text[pos:])

    def _insert_markdown(self, cur: QTextCursor, part: str) -> None:
        part = prepare_markdown(part)
        if not part.strip():
            return
        try:
            cur.setCharFormat(QTextCharFormat())     # repart d'un style neutre (rien ne « fuit » du texte précédent)
            cur.setBlockFormat(QTextBlockFormat())
            start = cur.position()
            cur.insertMarkdown(part)
            self._style_headings(start, cur.position())
        except Exception:  # noqa: BLE001
            _insert(cur, html.escape(part).replace("\n", "<br>"))
        cur.insertBlock()
        cur.setBlockFormat(QTextBlockFormat())    # le bloc suivant ne garde pas le style d'un titre
        cur.setCharFormat(QTextCharFormat())

    def _style_headings(self, start: int, end: int) -> None:
        """Titres markdown : bien plus gros que le texte, en couleur d'accent, avec de l'air autour
        (le rendu par défaut de Qt les distingue à peine)."""
        base = self.font().pointSizeF()
        if base <= 0:
            base = 10.0
        scale = {1: 1.9, 2: 1.55, 3: 1.3, 4: 1.15}
        doc = self.document()
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            level = block.blockFormat().headingLevel()
            if level:
                c = QTextCursor(block)
                c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cf = QTextCharFormat()
                cf.setFontPointSize(base * scale.get(level, 1.1))
                cf.setFontWeight(700)
                cf.setForeground(QColor(theme.shift_hex("#22d3ee") if level <= 2 else theme.shift_hex("#a5f3fc")))
                c.mergeCharFormat(cf)
                bf = QTextBlockFormat()
                bf.setTopMargin(12 if level <= 2 else 8)
                bf.setBottomMargin(4)
                c.mergeBlockFormat(bf)
            block = block.next()

    def _insert_code(self, cur: QTextCursor, lang: str, code: str) -> None:
        idx = len(self._snippets)
        self._snippets.append(code)
        _insert(cur, 
            '<table width="100%" cellspacing="0" cellpadding="8" border="0" bgcolor="#0b0d16">'
            '<tr>'
            f'<td bgcolor="#151827"><span style="color:#22d3ee;font-family:Consolas;font-size:12px;">'
            f'{html.escape(lang or "code")}</span></td>'
            f'<td bgcolor="#151827" align="right"><a href="copy:{idx}" style="color:#e84df5;'
            'text-decoration:none;font-family:Consolas;font-weight:700;font-size:12px;">⧉ COPIER</a></td>'
            '</tr><tr><td colspan="2">'
            # pre-wrap : les lignes trop longues passent à la ligne dans le bloc au lieu
            # d'élargir toute la discussion (le bouton COPIER reste toujours visible).
            '<p style="white-space:pre-wrap;font-family:Consolas,monospace;color:#a5f3fc;font-size:13px;">'
            f"{html.escape(code)}</p></td></tr></table>"
        )
        cur.movePosition(QTextCursor.End)
        cur.insertBlock()

    def _on_anchor(self, url: QUrl) -> None:
        if url.scheme() == "copy":
            try:
                code = self._snippets[int(url.path())]
            except (ValueError, IndexError):
                return
            QGuiApplication.clipboard().setText(code)
            self.copied.emit(code)
        else:
            QDesktopServices.openUrl(url)

    # ------------------------------------------------------- écriture en direct
    def begin_live(self) -> None:
        cur = self._end_cursor()
        self._live_header = cur.position()
        self._header(cur, "JIMMY", "#e84df5")
        self._live_start = cur.position()
        self._done_text, self._current, self._shown = "", "", 0.0
        self._timer.start()

    def live_chunk(self, text: str, duration: float, words=None) -> None:
        """Nouveau morceau lu à voix haute. Avec les instants des mots (voix Edge), chaque mot
        s'écrit au moment exact où il est prononcé ; sinon on suit la durée du morceau."""
        if self._live_start is None:
            return
        if self._current:
            self._done_text += self._current + " "
        self._current = text
        self._shown = 0.0
        self._chunk_t0 = time.monotonic()
        self._duration = max(0.3, duration)
        # [(instant, position de fin du mot dans le texte)]
        self._marks = []
        pos = 0
        for t, word in words or []:
            i = text.find(word, pos)
            if i < 0:
                continue
            pos = i + len(word)
            self._marks.append((t, pos))

    def end_live(self, full_text: str) -> None:
        """Fin de la parole : le message définitif (markdown, code) remplace l'écriture en direct."""
        self._timer.stop()
        if self._live_header is None:
            self.add_assistant(full_text)
            return
        cur = self.textCursor()
        cur.setPosition(self._live_header)
        cur.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cur.removeSelectedText()
        self._live_header = self._live_start = None
        self.add_assistant(full_text)

    def _tick(self) -> None:
        if self._live_start is None:
            self._timer.stop()
            return
        if self.textCursor().hasSelection():
            return           # on ne réécrit pas le texte sous ta sélection (le texte reprend ensuite)
        elapsed = time.monotonic() - self._chunk_t0
        if elapsed >= self._duration:
            self._shown = len(self._current)
        elif self._marks:
            # Le mot apparaît dès qu'il commence à être prononcé (petite avance pour l'effet).
            self._shown = max([p for t, p in self._marks if t <= elapsed + 0.08] or [0])
        else:
            self._shown = len(self._current) * elapsed / self._duration
        typed = self._done_text + self._current[: int(self._shown)]
        typing = self._shown < len(self._current)
        tail = "".join(random.choice(_GLYPHS) for _ in range(3)) if typing else ""
        cursor_on = typing or int(time.monotonic() * 2.5) % 2 == 0  # curseur qui clignote
        cur = self.textCursor()
        cur.setPosition(self._live_start)
        cur.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        _insert(cur, 
            '<span style="color:#e6e8f2;">' + html.escape(typed).replace("\n", "<br>") + "</span>"
            + (f'<span style="color:#22d3ee;font-family:Consolas;">{html.escape(tail)}</span>' if tail else "")
            + ('<span style="color:#e84df5;">▌</span>' if cursor_on else "")
        )
        self._scroll()
