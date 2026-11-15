"""Jimmy : assistant vocal relié à Claude Code."""
import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Jimmy.exe sert aussi de serveur d'autorisation pour Claude Code (sans Python installé sur le PC).
if "--perm-mcp" in sys.argv:
    import perm_mcp
    perm_mcp.main()
    sys.exit(0)


if "--mem" in sys.argv:
    # Mémoire de Jimmy en ligne de commande (Jimmy.exe --mem search mots) : sans Python installé.
    import jimmy_mem
    sys.exit(jimmy_mem.main([a for a in sys.argv[1:] if a != "--mem"]))


if "--webtest" in sys.argv:
    # Vérifie que l'interface web démarre (utile pour tester une version compilée) : écrit webtest.txt dans le dossier de données.
    import webwindow
    sys.exit(webwindow.selftest())


if "--selftest" in sys.argv:
    # Diagnostic sans interface : écrit selftest.txt dans le dossier de données.
    from main_streams import fix_streams
    fix_streams()
    import selftest
    print(selftest.run())
    sys.exit(0)


from main_streams import fix_streams

fix_streams()

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QMessageBox, QProgressDialog,
                               QTextBrowser, QVBoxLayout)

import updater
from config import Config
from icon import make_icon
from version import APP_NAME, UPDATE_REPO, __version__

SOCKET_NAME = "JimmyAssistantSingleInstance"


class _UpdateWorker(QObject):
    found = Signal(object)

    def __init__(self, repo: str):
        super().__init__()
        self.repo = repo

    def run(self) -> None:
        try:
            u = updater.check(self.repo)
        except Exception:  # noqa: BLE001
            u = None
        if u:
            self.found.emit(u)


class _UpdateReceiver(QObject):
    """Vit dans le fil de l'interface : la fenêtre de mise à jour ne doit jamais s'ouvrir depuis le fil réseau."""

    def __init__(self, win):
        super().__init__()
        self.win = win

    @Slot(object)
    def on_found(self, update) -> None:
        try:
            _offer_update(self.win, update)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()


def _offer_update(win, update) -> None:
    """Fenêtre de mise à jour : les nouveautés complètes, dans une zone qui défile (rien n'est coupé)."""
    can = updater.can_self_update()
    dlg0 = QDialog(win)
    dlg0.setWindowTitle("Mise à jour de Jimmy")
    dlg0.setMinimumSize(620, 460)
    lay = QVBoxLayout(dlg0)
    title = QLabel(f"<b>Jimmy {update.version}</b> est disponible (tu as la {__version__}).")
    title.setWordWrap(True)
    lay.addWidget(title)
    if update.notes:
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setMarkdown(update.notes)
        lay.addWidget(view, 1)
    buttons = QDialogButtonBox()
    if can:
        yes = buttons.addButton("Installer maintenant", QDialogButtonBox.AcceptRole)
        no = buttons.addButton("Plus tard", QDialogButtonBox.RejectRole)
        yes.clicked.connect(dlg0.accept)
        no.clicked.connect(dlg0.reject)
    else:
        ok = buttons.addButton("OK", QDialogButtonBox.AcceptRole)
        ok.clicked.connect(dlg0.accept)
    lay.addWidget(buttons)
    if dlg0.exec() != QDialog.Accepted or not can:
        return
    dlg = QProgressDialog("Téléchargement de la mise à jour…", None, 0, 100, win)
    dlg.setWindowTitle("Jimmy")
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()
    try:
        path = updater.download(update, lambda d, t: (dlg.setValue(int(d * 100 / t) if t else 0), QApplication.processEvents()))
    except Exception as e:  # noqa: BLE001
        dlg.close()
        QMessageBox.warning(win, "Jimmy", f"Téléchargement impossible : {e}")
        return
    dlg.close()
    updater.run_installer(path)
    QApplication.quit()


def _other_instance(wait: bool = False, patience: float = 20.0) -> bool:
    """True si un autre Jimmy tourne (on le réveille alors). Avec wait=True (redémarrage), on laisse
    d'abord à l'ancien Jimmy le temps de se fermer ; s'il est encore là après `patience` secondes, on le réveille."""
    import time
    deadline = time.monotonic() + (patience if wait else 0)
    while True:
        probe = QLocalSocket()
        probe.connectToServer(SOCKET_NAME)
        if not probe.waitForConnected(300):
            return False
        if wait and time.monotonic() < deadline:
            probe.abort()
            time.sleep(0.4)
            continue
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        return True


def _upgrade_voice(cfg) -> None:
    """Version 2 : une seule fois, un PC avec carte NVIDIA passe au modèle vocal le plus précis (large-v3-turbo) au lieu d'un modèle
    moyen sur le processeur. Les autres PC ne changent pas. Réversible dans Réglages › Audio."""
    if cfg.get("voice_v2"):
        return
    cfg.set("voice_v2", True)
    try:
        from listener import auto_choice
        model, device = auto_choice(cfg)
    except Exception:  # noqa: BLE001
        return
    if device == "cuda" and model == "large-v3-turbo" and cfg.get("whisper_model") in ("tiny", "base", "small", "medium"):
        cfg.set("whisper_model", model)
        cfg.set("whisper_device", device)


def main() -> None:
    restarting = "--restart" in sys.argv       # lancé par « redémarrer » : on attend la fermeture de l'ancien
    sys.argv = [a for a in sys.argv if a != "--restart"]
    if os.name == "nt":
        # Icône propre dans la barre des tâches (sinon Windows affiche celle de Python).
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Jimmy.Assistant")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(make_icon())

    # Une seule fenêtre de Jimmy : un second lancement réveille la première.
    # Sauf après « redémarrer » : l'ancienne fenêtre est en train de se fermer, on l'attend au lieu de la réveiller.
    if _other_instance(wait=restarting):
        return
    server = QLocalServer()
    QLocalServer.removeServer(SOCKET_NAME)
    server.listen(SOCKET_NAME)

    cfg = Config.load()
    _upgrade_voice(cfg)
    import setup_wizard
    setup_wizard.run_if_needed(cfg)

    from window import JimmyWindow
    win = None
    if cfg.get("ui", "web") != "classic" and "--classic" not in sys.argv:
        # Interface web (HTML/CSS) : si elle ne peut pas démarrer, l'ancienne fenêtre prend le relais.
        try:
            import webwindow
            if webwindow.available():
                win = webwindow.WebJimmyWindow(cfg)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            win = None
    if win is None:
        win = JimmyWindow(cfg)

    def _wake() -> None:
        conn = server.nextPendingConnection()
        if conn:
            conn.readAll()
            conn.close()
        win.showNormal()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(_wake)
    win.show_animated()
    if getattr(sys, "frozen", False) and not cfg.get("workdir") and not cfg.get("folder_prompted"):
        cfg.set("folder_prompted", True)      # une seule fois : Annuler garde le dossier personnel
        QTimer.singleShot(1200, win.on_folder)

    # Mises à jour : un coup d'œil discret au démarrage, sur le dépôt GitHub indiqué dans les réglages.
    thread = QThread()
    repo = str(cfg.get("update_repo") or UPDATE_REPO)
    worker = _UpdateWorker(repo)
    if cfg.get("update_check", True) and repo:
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        receiver = _UpdateReceiver(win)      # garde une référence : sinon il serait détruit
        worker.found.connect(receiver.on_found, Qt.QueuedConnection)
        QTimer.singleShot(8000, thread.start)
    app.aboutToQuit.connect(lambda: (thread.quit(), thread.wait(1500)))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
