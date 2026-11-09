"""Mini serveur MCP lancé par Claude Code : transmet les demandes d'autorisation à la fenêtre de Jimmy.

Claude Code l'appelle (--permission-prompt-tool) chaque fois qu'une action demande une validation.
On relaie la demande à Jimmy (socket local), qui l'affiche à l'écran, puis on renvoie sa réponse.
Variables : JIMMY_PERM_PORT et JIMMY_PERM_TOKEN. En cas de souci, on refuse (jamais d'autorisation par défaut).
"""
import json
import os
import socket
import sys

TOOL = {
    "name": "approve",
    "description": "Demande à l'utilisateur, dans la fenêtre de Jimmy, d'autoriser une action.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "input": {"type": "object"},
            "tool_use_id": {"type": "string"},
        },
        "required": ["tool_name", "input"],
    },
}


def _ask_jimmy(tool_name: str, tool_input) -> dict:
    try:
        port = int(os.environ["JIMMY_PERM_PORT"])
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.settimeout(float(os.environ.get("JIMMY_PERM_WAIT", "150")))   # un peu plus que le délai de la fenêtre
            req = {"token": os.environ.get("JIMMY_PERM_TOKEN", ""), "tool_name": tool_name, "input": tool_input}
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"allow": False, "message": f"Pas de réponse de Jimmy à la demande d'autorisation ({e}). Ne réessaie pas en boucle : dis-le à l'utilisateur."}


def _decision(args: dict) -> str:
    tool_name = str(args.get("tool_name", ""))
    tool_input = args.get("input") or {}
    ans = _ask_jimmy(tool_name, tool_input)
    if ans.get("allow") is True:
        return json.dumps({"behavior": "allow", "updatedInput": tool_input})
    return json.dumps({"behavior": "deny", "message": ans.get("message") or "L'utilisateur a refusé cette action."})


def _reply(msg_id, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        method, msg_id = req.get("method"), req.get("id")
        if msg_id is None:       # notification (initialized...) : pas de réponse
            continue
        if method == "initialize":
            ver = (req.get("params") or {}).get("protocolVersion") or "2024-11-05"
            _reply(msg_id, {
                "protocolVersion": ver,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jimmyperm", "version": "1.0"},
            })
        elif method == "tools/list":
            _reply(msg_id, {"tools": [TOOL]})
        elif method == "tools/call":
            params = req.get("params") or {}
            if params.get("name") != "approve":
                _reply(msg_id, error={"code": -32602, "message": "outil inconnu"})
                continue
            _reply(msg_id, {"content": [{"type": "text", "text": _decision(params.get("arguments") or {})}]})
        elif method == "ping":
            _reply(msg_id, {})
        else:
            _reply(msg_id, error={"code": -32601, "message": "méthode inconnue"})


if __name__ == "__main__":
    main()
