"""Serveur local (127.0.0.1) qui permet à JIMMY (Claude) de demander un travail à l'IA locale : chercher un fichier, lire, chercher sur
Internet... Gratuit pour l'abonnement. Un jeton secret évite que d'autres programmes s'en servent ; l'IA locale n'a ici que des
outils de LECTURE (jamais d'écriture ni de commande : elles ne partent que d'une demande de l'utilisateur).

Côté Claude, la commande est `jimmy_local.py ask "question"` (ou `Jimmy.exe --local ask "question"` sur la version installée).
"""
import json
import os
import secrets
import socket
import socketserver
import sys
import threading


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        srv = self.server
        try:
            req = json.loads(self.rfile.readline().decode("utf-8"))
        except ValueError:
            return
        if not secrets.compare_digest(str(req.get("token", "")), srv.token):
            self._send({"ok": False, "answer": "Jeton invalide."})
            return
        try:
            answer = srv.ask(str(req.get("question", ""))[:4000])
        except Exception as e:  # noqa: BLE001
            self._send({"ok": False, "answer": f"Erreur côté Jimmy : {e}"})
            return
        self._send({"ok": True, "answer": str(answer)[:6000]})

    def _send(self, obj) -> None:
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


class LocalServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, ask):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.ask = ask                       # ask(question) -> réponse (texte)
        self.token = secrets.token_hex(16)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.server_address[1]

    def env(self) -> dict:
        """Variables d'environnement à donner à Claude pour qu'il puisse appeler l'IA locale."""
        return {"JIMMY_LOCAL_PORT": str(self.port), "JIMMY_LOCAL_TOKEN": self.token}


def ask(question: str, port=None, token=None, timeout: float = 240.0) -> tuple:
    """Côté client : (ok, réponse)."""
    port = port or os.environ.get("JIMMY_LOCAL_PORT")
    token = token or os.environ.get("JIMMY_LOCAL_TOKEN")
    if not port or not token:
        return False, "L'IA locale n'est pas joignable (IA locale coupée ou Jimmy fermé) : fais ce travail toi-même."
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=10) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps({"token": token, "question": question}, ensure_ascii=False) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        res = json.loads(data.decode("utf-8"))
        return bool(res.get("ok")), str(res.get("answer", ""))
    except (OSError, ValueError) as e:
        return False, f"L'IA locale ne répond pas ({e}) : fais ce travail toi-même."


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] != "ask":
        print('Usage : jimmy_local.py ask "ta question pour l\'IA locale"')
        return 2
    ok, answer = ask(" ".join(argv[1:]))
    print(answer)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
