"""Serveur local (127.0.0.1) qui permet à JIMMY (Claude) de demander un travail à l'IA locale : chercher un fichier, lire, chercher sur
Internet... Gratuit pour l'abonnement. Un jeton secret évite que d'autres programmes s'en servent ; l'IA locale n'a ici que des
outils de LECTURE (jamais d'écriture ni de commande : elles ne partent que d'une demande de l'utilisateur).

Côté Claude, trois commandes (ou `Jimmy.exe --local ...` sur la version installée) :
  jimmy_local.py ask "question"                      : travail de lecture / recherche
  jimmy_local.py capture ADRESSE [--full] [--width N] [--element SELECTEUR] [--caption TEXTE]
                                                     : Aurélie ouvre la page dans son navigateur, la capture (visible par l'utilisateur dans la
                                                       discussion et dans le panneau de droite) et renvoie un rapport texte + le texte lu
  jimmy_local.py see CHEMIN_IMAGE ["question"]       : Aurélie analyse une image (texte lu, couleurs, modèle de vision s'il y en a un)
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
            cmd = str(req.get("cmd") or "ask")
            if cmd == "ask":
                answer = srv.ask(str(req.get("question", ""))[:4000])
            elif cmd in ("capture", "see") and srv.act:
                answer = srv.act(cmd, {k: v for k, v in req.items() if k not in ("token", "cmd")})
            else:
                answer = "Commande inconnue ou non disponible."
        except Exception as e:  # noqa: BLE001
            self._send({"ok": False, "answer": f"Erreur côté Jimmy : {e}"})
            return
        self._send({"ok": True, "answer": str(answer)[:6000]})

    def _send(self, obj) -> None:
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


class LocalServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, ask, act=None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.ask = ask                       # ask(question) -> réponse (texte)
        self.act = act                       # act(commande, paramètres) -> réponse (texte) : capture, see
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
    return request({"cmd": "ask", "question": question}, port, token, timeout)


def request(payload: dict, port=None, token=None, timeout: float = 240.0) -> tuple:
    """Côté client : envoie une commande à Jimmy. (ok, réponse)."""
    port = port or os.environ.get("JIMMY_LOCAL_PORT")
    token = token or os.environ.get("JIMMY_LOCAL_TOKEN")
    if not port or not token:
        return False, "L'IA locale n'est pas joignable (IA locale coupée ou Jimmy fermé) : fais ce travail toi-même."
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=10) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps({**payload, "token": token}, ensure_ascii=False) + "\n").encode("utf-8"))
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


USAGE = ('Usage : jimmy_local.py ask "question" | capture ADRESSE [--full] [--width N] [--element SELECTEUR] [--caption TEXTE] '
         '| see CHEMIN_IMAGE ["question"]')


def _opt(args: list, name: str, default=""):
    """Retire `--name valeur` de la liste et renvoie la valeur."""
    if name in args:
        i = args.index(name)
        val = args[i + 1] if i + 1 < len(args) else default
        del args[i:i + 2]
        return val
    return default


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("ask", "capture", "see") or len(argv) < 2:
        print(USAGE)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "ask":
        ok, answer = ask(" ".join(rest))
    elif cmd == "capture":
        full = "--full" in rest
        rest = [a for a in rest if a != "--full"]
        width, element, caption = _opt(rest, "--width", "0"), _opt(rest, "--element"), _opt(rest, "--caption")
        ok, answer = request({"cmd": "capture", "url": rest[0] if rest else "", "full": full, "width": width, "element": element,
                              "caption": caption})
    else:
        ok, answer = request({"cmd": "see", "path": rest[0], "question": " ".join(rest[1:])})
    print(answer)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
