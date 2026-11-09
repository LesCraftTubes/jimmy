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
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

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
    box = QMessageBox(win)
    box.setWindowTitle("Mise à jour de Jimmy")
    box.setText(f"Jimmy {update.version} est disponible (tu as la {__version__}).")
    if update.notes:
        box.setInformativeText(update.notes)
    if not updater.can_self_update():
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
        return
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.button(QMessageBox.Yes).setText("Installer maintenant")
    box.button(QMessageBox.No).setText("Plus tard")
    if box.exec() != QMessageBox.Yes:
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
    import setup_wizard
    setup_wizard.run_if_needed(cfg)

    from window import JimmyWindow
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
