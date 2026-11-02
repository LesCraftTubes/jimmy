"""Chef d'orchestre de l'appli mobile : serveur local + tunnel éventuel, selon les réglages."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from remote import RemoteServer, lan_ip
from tunnel import Tunnel

MODES = ("lan", "tunnel", "custom")


class RemoteManager(QObject):
    changed = Signal()     # l'état a changé (appareils, tunnel, serveur) : la fenêtre de réglages se rafraîchit

    def __init__(self, cfg, handlers):
        super().__init__()
        self.cfg = cfg
        self.server = RemoteServer(cfg, handlers)
        self.server.on_change = self.changed.emit
        self.tunnel = Tunnel(on_change=self.changed.emit)
        self._bound_all: bool | None = None

    # ----------------------------------------------------------- cycle de vie
    def mode(self) -> str:
        m = self.cfg.get("remote_mode", "lan")
        return m if m in MODES else "lan"

    def apply(self) -> None:
        """Démarre, arrête ou reconfigure selon les réglages actuels."""
        if not self.cfg.get("remote_enabled"):
            self.shutdown()
            self.changed.emit()
            return
        mode = self.mode()
        bind_all = mode != "tunnel"            # en mode tunnel, seul le PC lui-même (cloudflared) peut joindre le serveur
        port = int(self.cfg.get("remote_port", 8765))
        if self.server.running and (self._bound_all != bind_all or self.server.port != port):
            self.server.stop()
        if not self.server.running:
            self.server.port = port
            self.server.start(bind_all=bind_all)
            self._bound_all = bind_all
        if mode == "tunnel":
            self.tunnel.start(port)
        else:
            self.tunnel.stop()
        self.changed.emit()

    def shutdown(self) -> None:
        self.tunnel.stop()
        self.server.stop()
        self._bound_all = None

    # ----------------------------------------------------------------- adresses
    def base_url(self) -> str:
        mode = self.mode()
        if mode == "tunnel":
            return self.tunnel.url
        if mode == "custom":
            return str(self.cfg.get("remote_custom_url", "")).strip().rstrip("/")
        return f"http://{lan_ip()}:{int(self.cfg.get('remote_port', 8765))}"

    def pair_url(self) -> str:
        base = self.base_url()
        return f"{base}/#pair={self.server.current_code()}" if base else ""

    def secure(self) -> bool:
        """Le micro du téléphone n'est autorisé que sur une adresse https."""
        return self.base_url().startswith("https://")

    # ------------------------------------------------------------------ état
    def status_text(self) -> str:
        if not self.cfg.get("remote_enabled"):
            return "Désactivée."
        if self.server.error:
            return self.server.error
        if not self.server.running:
            return "Démarrage…"
        mode = self.mode()
        if mode == "tunnel":
            if self.tunnel.error:
                return self.tunnel.error
            if self.tunnel.status == "téléchargement":
                return "Téléchargement du tunnel Cloudflare (une seule fois)…"
            if not self.tunnel.url:
                return "Ouverture du tunnel Internet…"
        if mode == "custom" and not self.base_url():
            return "Indique ton adresse (https://…) ci-dessous."
        n = self.server.client_count()
        return f"Prête · {n} téléphone{'s' if n > 1 else ''} connecté{'s' if n > 1 else ''}" if n else "Prête · aucun téléphone connecté."

    def emit(self, event: dict) -> None:
        self.server.emit(event)
