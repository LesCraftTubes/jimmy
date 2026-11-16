"""Chef d'orchestre de l'appli mobile : serveur local + tunnel éventuel, selon les réglages."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from remote import RemoteServer, lan_ip
from tunnel import Tunnel

MODES = ("lan", "tunnel", "custom", "permanent")


class RemoteManager(QObject):
    changed = Signal()     # l'état a changé (appareils, tunnel, serveur) : la fenêtre de réglages se rafraîchit

    def __init__(self, cfg, handlers):
        super().__init__()
        self.cfg = cfg
        self.server = RemoteServer(cfg, handlers)
        self.server.on_change = self.changed.emit
        self.tunnel = Tunnel(on_change=self.changed.emit)
        self._bound_all: bool | None = None
        self.setup_msg = ""           # progression de la création du lien permanent
        self.setting_up = False

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
        bind_all = mode not in ("tunnel", "permanent")      # derrière un tunnel, seul le PC lui-même (cloudflared) peut joindre le serveur
        port = int(self.cfg.get("remote_port", 8765))
        if self.server.running and (self._bound_all != bind_all or self.server.port != port):
            self.server.stop()
        if not self.server.running:
            self.server.port = port
            self.server.start(bind_all=bind_all)
            self._bound_all = bind_all
        if mode == "tunnel":
            self.tunnel.start(port)
        elif mode == "permanent" and self.permanent_spec():
            self.tunnel.start(port, named=self.permanent_spec())
        else:
            self.tunnel.stop()
        self.changed.emit()

    # ------------------------------------------------------- lien permanent (nom fixe sur TON domaine)
    def permanent_spec(self):
        host, tid, cred, name = (str(self.cfg.get(k, "")) for k in ("remote_perm_host", "remote_perm_id", "remote_perm_cred", "remote_perm_name"))
        return {"host": host, "id": tid, "cred": cred, "name": name} if host and tid and cred and name else None

    def setup_permanent(self, hostname: str) -> None:
        """Crée le lien permanent en arrière-plan (une seule connexion Cloudflare demandée à l'utilisateur)."""
        import threading
        if self.setting_up:
            return
        self.setting_up = True

        def say(t: str) -> None:
            self.setup_msg = t
            self.changed.emit()

        def work() -> None:
            try:
                ok, msg, spec = self.tunnel.setup_named(hostname, progress=say)
                if ok and spec:
                    for k, v in (("remote_perm_host", spec["host"]), ("remote_perm_id", spec["id"]), ("remote_perm_cred", spec["cred"]),
                                 ("remote_perm_name", spec["name"]), ("remote_mode", "permanent"), ("remote_enabled", True)):
                        self.cfg.set(k, v)
                    self.tunnel.stop()
                    self.apply()
                say(msg)
            except Exception as e:  # noqa: BLE001
                say(f"Création impossible : {e}")
            finally:
                self.setting_up = False
                self.changed.emit()
        threading.Thread(target=work, daemon=True, name="jimmy-perm-setup").start()

    def shutdown(self) -> None:
        self.tunnel.stop()
        self.server.stop()
        self._bound_all = None

    # ----------------------------------------------------------------- adresses
    def base_url(self) -> str:
        mode = self.mode()
        if mode == "tunnel":
            return self.tunnel.url
        if mode == "permanent":
            spec = self.permanent_spec()
            return f"https://{spec['host']}" if spec else ""
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
        if mode == "permanent":
            if self.setting_up or (self.setup_msg and not self.permanent_spec()):
                return self.setup_msg or "Création du lien permanent…"
            if not self.permanent_spec():
                return "Lien permanent pas encore créé : clique sur le bouton ci-dessous."
            if self.tunnel.error:
                return self.tunnel.error
            if self.tunnel.status != "prêt":
                return f"Connexion du lien permanent ({self.base_url()})…"
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
