"""Tiny dashboard server (standard library only). Localhost only unless phone_access is on."""
import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import ROOT

INDEX = Path(__file__).parent / "static" / "index.html"


def lan_ip() -> str:
    """This PC's address on the home network (no traffic is sent; UDP connect just picks a route)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return ""


def make_server(cfg: dict, state, scheduler) -> ThreadingHTTPServer:
    image = cfg["target"].get("image", "")
    image_file = None if image.startswith(("http://", "https://", "//")) or not image else ROOT / image
    image_url = "/target-image" if image_file else image
    port, phone = cfg["settings"]["port"], cfg["settings"]["phone_access"]

    def status_payload(local: bool) -> dict:
        full = state.snapshot()
        snap = full["sources"]
        rows = []
        for src in cfg["sources"]:
            s = snap.get(src["id"], {})
            rows.append({
                "id": src["id"], "name": src["name"], "type": src["type"],
                "link": s.get("link") or src.get("url") or src.get("store") or "",
                "status": s.get("status", "pending"), "summary": s.get("summary", "Waiting for first check…"),
                "items": s.get("items", []), "error": s.get("error"),
                "consecutive_errors": s.get("consecutive_errors", 0),
                "last_check": s.get("last_check"), "last_ok": s.get("last_ok"),
                "next_check": scheduler.next_run.get(src["id"]),
                "checking": scheduler.running == src["id"],
            })
        now = time.time()
        ip = lan_ip() if phone else ""
        return {"phone_url": f"http://{ip}:{port}" if ip else "",
                "target": cfg["target"]["name"], "image": image_url, "now": now, "sources": rows,
                "heartbeat_age": now - scheduler.heartbeat if scheduler.heartbeat else None,
                "history": full["history"][::-1][:25], "watching_since": full["since"],
                # The ntfy topic works like a password for your alerts, so only show it on the PC itself.
                "ntfy_topic": cfg.get("notify", {}).get("ntfy_topic", "") if local else ""}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/target-image" and image_file and image_file.is_file():
                ctype = {".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml"}.get(
                    image_file.suffix.lower(), "image/jpeg")
                self._send(200, image_file.read_bytes(), ctype)
            elif self.path == "/api/status":
                self._send(200, json.dumps(status_payload(self.client_address[0] == "127.0.0.1")).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path.startswith("/api/check/"):
                ok = scheduler.request_check(self.path.rsplit("/", 1)[-1])
                self._send(200 if ok else 404, b"{}", "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args):  # keep the log quiet
            pass

    return ThreadingHTTPServer(("0.0.0.0" if phone else "127.0.0.1", port), Handler)
