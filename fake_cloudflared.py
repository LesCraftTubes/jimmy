"""Faux « cloudflared » pour les tests (jamais publié, jamais utilisé en vrai) : imite login / list / create / route dns / run."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

args = sys.argv[1:]
log = os.environ.get("FAKE_CF_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")
cert = Path(os.environ.get("TUNNEL_ORIGIN_CERT", ""))

if args[:2] == ["tunnel", "login"]:
    print("Please open the following URL and log in with your Cloudflare account: https://dash.cloudflare.com/argotunnel?fake", flush=True)
    time.sleep(1.2)
    cert.write_text("FAKE CERT", encoding="utf-8")
    print("You have successfully logged in.", flush=True)
elif args[:2] == ["tunnel", "list"]:
    print("[]")
elif args[:2] == ["tunnel", "create"]:
    path = Path(args[args.index("--credentials-file") + 1])
    tid = str(uuid.uuid4())
    path.write_text(json.dumps({"TunnelID": tid, "TunnelName": args[-1]}), encoding="utf-8")
    print(f"Tunnel credentials written to {path}.")
    print(f"Created tunnel {args[-1]} with id {tid}")
elif args[:3] == ["tunnel", "route", "dns"]:
    print(f"2026-11-16T12:00:00Z INF Added CNAME {args[-1]} which will route to this tunnel")
elif "run" in args:
    print("2026-11-16T12:00:00Z INF Starting tunnel", flush=True)
    time.sleep(0.5)
    print("2026-11-16T12:00:01Z INF Registered tunnel connection connIndex=0 location=cdg", flush=True)
    time.sleep(60)
else:
    print("fake cloudflared : commande inconnue", args)
    sys.exit(2)
