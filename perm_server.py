"""Serveur local (127.0.0.1) qui reçoit les demandes d'autorisation de perm_mcp.py.

Chaque demande est transmise à `ask(tool_name, input) -> (allow, remember)` (la fenêtre de Jimmy,
qui affiche la question à l'écran). Un jeton secret évite que d'autres programmes répondent à la place.
"""
import json
import secrets
import socketserver
import threading


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        srv = self.server
        try:
            req = json.loads(self.rfile.readline().decode("utf-8"))
        except ValueError:
            return
        if not secrets.compare_digest(str(req.get("token", "")), srv.token):
            self._send({"allow": False, "message": "Jeton invalide."})
            return
        try:
            allow, remember = srv.ask(str(req.get("tool_name", "")), req.get("input") or {})
        except Exception as e:  # noqa: BLE001
            self._send({"allow": False, "message": f"Erreur côté Jimmy : {e}"})
            return
        srv.answered += 1
        self._send({"allow": bool(allow), "remember": bool(remember),
                    "message": "" if allow else (srv.last_note or "L'utilisateur a refusé cette action.")})

    def _send(self, obj) -> None:
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))


class PermServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, ask):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.ask = ask
        self.token = secrets.token_hex(16)
        self.last_note = ""   # explication du dernier refus (ex. délai dépassé)
        self.answered = 0      # nombre de demandes traitées (remis à zéro à chaque tâche)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.server_address[1]
