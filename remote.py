"""Serveur distant de Jimmy : l'appli mobile (PWA) s'y connecte pour parler à Jimmy et lui donner des ordres.

- Tourne dans Jimmy, sur le PC (un thread, aiohttp). Rien ne passe par un serveur tiers.
- Jumelage : un code à usage unique (affiché en QR sur le PC). Le téléphone reçoit alors une clé longue,
  gardée sur le téléphone ; seule son empreinte est stockée sur le PC (devices.json).
- Le téléphone voit la discussion en direct (WebSocket) et peut envoyer, stopper, démarrer une nouvelle discussion.
- Sécurité : clé de 256 bits, code de jumelage valable 10 minutes et à usage unique, tentatives limitées par adresse.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import socket
import threading
import time
from collections import deque
from pathlib import Path

from aiohttp import WSMsgType, web

from config import app_dir, data_dir

PAIR_TTL = 600               # secondes de validité d'un code de jumelage
PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans O/0/I/1/L : lisible à la main
MAX_TEXT = 20000
HISTORY_MAX = 200


def lan_ip() -> str:
    """Adresse du PC sur le réseau local (celle que le téléphone doit joindre en Wi-Fi)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mobile_dir() -> Path:
    return app_dir() / "mobile"


class RemoteServer:
    """handlers : objet avec remote_send(text), remote_stop(), remote_new(), remote_snapshot() -> dict.

    Ces méthodes sont appelées depuis le thread du serveur : elles doivent seulement poster un signal Qt.
    """

    def __init__(self, cfg, handlers):
        self.cfg = cfg
        self.h = handlers
        self.port = int(cfg.get("remote_port", 8765))
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._runner: web.AppRunner | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._history: deque = deque(maxlen=HISTORY_MAX)
        self._pair: dict | None = None            # {code, expires}
        self._fails: dict[str, list] = {}         # ip -> horodatages d'échecs de jumelage
        self._path = data_dir() / "devices.json"
        self._devices = self._load()
        self.error = ""
        self.running = False
        self.on_change = None                     # appelé quand les appareils ou l'état changent (pour la fenêtre de réglages)

    # ------------------------------------------------------------- appareils
    def _load(self) -> list:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._devices, indent=2), encoding="utf-8")
        except OSError:
            pass
        if self.on_change:
            self.on_change()

    def devices(self) -> list:
        return [{"id": d["id"], "name": d["name"], "created": d["created"], "last_seen": d.get("last_seen", 0)}
                for d in self._devices]

    def revoke(self, dev_id: str) -> None:
        self._devices = [d for d in self._devices if d["id"] != dev_id]
        self._save()
        for ws in list(self._clients):
            if getattr(ws, "_dev_id", None) == dev_id and self._loop:
                asyncio.run_coroutine_threadsafe(ws.close(), self._loop)

    def _device_for(self, token: str):
        if not token:
            return None
        h = _hash(token)
        for d in self._devices:
            if hmac.compare_digest(d["hash"], h):
                return d
        return None

    # -------------------------------------------------------------- jumelage
    def new_pair_code(self) -> str:
        code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(8))
        self._pair = {"code": code, "expires": time.time() + PAIR_TTL}
        if self.on_change:
            self.on_change()
        return code

    def current_code(self) -> str:
        if self._pair and self._pair["expires"] > time.time():
            return self._pair["code"]
        return self.new_pair_code()

    def pair_seconds_left(self) -> int:
        return max(0, int(self._pair["expires"] - time.time())) if self._pair else 0

    @staticmethod
    def _norm(code: str) -> str:
        return "".join(c for c in (code or "").upper() if c in PAIR_ALPHABET)

    def _client_ip(self, request: web.Request) -> str:
        ip = request.remote or "?"
        if ip in ("127.0.0.1", "::1"):                      # derrière un tunnel : l'adresse réelle est dans l'en-tête
            ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", ip).split(",")[0].strip()
        return ip

    def _blocked(self, ip: str) -> bool:
        now = time.time()
        fails = [t for t in self._fails.get(ip, []) if now - t < 600]
        self._fails[ip] = fails
        return len(fails) >= 8

    # ------------------------------------------------------------------ HTTP
    async def _pair_handler(self, request: web.Request) -> web.Response:
        ip = self._client_ip(request)
        if self._blocked(ip):
            return web.json_response({"ok": False, "error": "Trop d'essais. Réessaie dans 10 minutes."}, status=429)
        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"ok": False, "error": "Requête invalide."}, status=400)
        code = self._norm(str(body.get("code", "")))
        name = str(body.get("name") or "Téléphone")[:40]
        p = self._pair
        if not p or p["expires"] < time.time() or not hmac.compare_digest(code, p["code"]):
            self._fails.setdefault(ip, []).append(time.time())
            return web.json_response({"ok": False, "error": "Code invalide ou expiré."}, status=403)
        self._pair = None                                   # à usage unique
        token = secrets.token_urlsafe(32)
        dev = {"id": secrets.token_hex(4), "name": name, "hash": _hash(token), "created": int(time.time()), "last_seen": int(time.time())}
        self._devices.append(dev)
        self._save()
        return web.json_response({"ok": True, "token": token, "id": dev["id"]})

    async def _ping_handler(self, request: web.Request) -> web.Response:
        from version import __version__
        return web.json_response({"app": "Jimmy", "version": __version__})

    def _auth(self, request: web.Request):
        h = request.headers.get("Authorization", "")
        token = h[7:] if h.startswith("Bearer ") else ""
        return self._device_for(token)

    async def _state_handler(self, request: web.Request) -> web.Response:
        if not self._auth(request):
            return web.json_response({"ok": False}, status=401)
        return web.json_response({"ok": True, "state": self.h.remote_snapshot()})

    # ------------------------------------------------------------- WebSocket
    async def _ws_handler(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=64 * 1024)
        await ws.prepare(request)
        try:
            first = await asyncio.wait_for(ws.receive(), timeout=8)
        except asyncio.TimeoutError:
            await ws.close()
            return ws
        dev = None
        if first.type == WSMsgType.TEXT:
            try:
                msg = json.loads(first.data)
                if msg.get("type") == "auth":
                    dev = self._device_for(str(msg.get("token", "")))
            except ValueError:
                pass
        if not dev:
            await ws.send_json({"type": "denied"})
            await ws.close()
            return ws
        ws._dev_id = dev["id"]
        dev["last_seen"] = int(time.time())
        self._clients.add(ws)
        if self.on_change:
            self.on_change()
        try:
            await ws.send_json({"type": "hello", "device": dev["name"], "state": self.h.remote_snapshot(),
                                "history": list(self._history)})
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(m.data)
                except ValueError:
                    continue
                self._command(data, dev)
        finally:
            self._clients.discard(ws)
            if self.on_change:
                self.on_change()
        return ws

    def _command(self, data: dict, dev: dict) -> None:
        t = data.get("type")
        if t == "send":
            text = str(data.get("text", "")).strip()[:MAX_TEXT]
            if text:
                self.h.remote_send(text)
        elif t == "stop":
            self.h.remote_stop()
        elif t == "new":
            self.h.remote_new()
        elif t == "switch":
            sid = str(data.get("id", ""))[:80]
            if sid:
                self.h.remote_switch(sid)
        dev["last_seen"] = int(time.time())

    # ----------------------------------------------- événements vers les téléphones
    def emit(self, event: dict) -> None:
        """Envoie un événement à tous les téléphones (appelable depuis n'importe quel thread)."""
        if event.get("type") in ("message", "system"):
            self._history.append(event)
        elif event.get("type") == "clear":
            self._history.clear()
        loop = self._loop
        if not loop or not self.running:
            return
        payload = json.dumps(event, ensure_ascii=False)

        async def _send():
            for ws in list(self._clients):
                try:
                    await ws.send_str(payload)
                except Exception:  # noqa: BLE001
                    self._clients.discard(ws)

        asyncio.run_coroutine_threadsafe(_send(), loop)

    def client_count(self) -> int:
        return len(self._clients)

    # --------------------------------------------------------------- démarrage
    def _app(self) -> web.Application:
        @web.middleware
        async def headers(request, handler):
            resp = await handler(request)
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("Referrer-Policy", "no-referrer")
            if request.path.startswith("/api"):
                resp.headers["Cache-Control"] = "no-store"
            return resp

        app = web.Application(middlewares=[headers])
        app.router.add_get("/api/ping", self._ping_handler)
        app.router.add_post("/api/pair", self._pair_handler)
        app.router.add_get("/api/state", self._state_handler)
        app.router.add_get("/ws", self._ws_handler)
        md = mobile_dir()

        async def index(request):
            return web.FileResponse(md / "index.html", headers={"Cache-Control": "no-cache"})

        app.router.add_get("/", index)
        if md.is_dir():
            app.router.add_static("/", md, show_index=False)
        return app

    def start(self, bind_all: bool = True) -> bool:
        if self.running:
            return True
        self.error = ""
        ready = threading.Event()

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def boot():
                self._runner = web.AppRunner(self._app(), access_log=None)
                await self._runner.setup()
                site = web.TCPSite(self._runner, "0.0.0.0" if bind_all else "127.0.0.1", self.port)
                await site.start()

            try:
                loop.run_until_complete(boot())
                self.running = True
            except OSError as e:
                self.error = f"Port {self.port} indisponible : {e}"
                ready.set()
                return
            ready.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self._shutdown())
                loop.close()

        self._thread = threading.Thread(target=run, daemon=True, name="jimmy-remote")
        self._thread.start()
        ready.wait(10)
        return self.running

    async def _shutdown(self) -> None:
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._runner:
            await self._runner.cleanup()

    def stop(self) -> None:
        if self._loop and self.running:
            self.running = False
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=3)
        self._loop = None
