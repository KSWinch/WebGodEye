"""Tiny dashboard server (standard library only), bound to localhost."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import ROOT

INDEX = Path(__file__).parent / "static" / "index.html"


def make_server(cfg: dict, state, scheduler) -> ThreadingHTTPServer:
    image = cfg["target"].get("image", "")
    image_file = None if image.startswith(("http://", "https://", "//")) or not image else ROOT / image
    image_url = "/target-image" if image_file else image

    def status_payload() -> dict:
        snap = state.snapshot()
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
        return {"target": cfg["target"]["name"], "image": image_url, "now": now, "sources": rows,
                "heartbeat_age": now - scheduler.heartbeat if scheduler.heartbeat else None,
                "ntfy_topic": cfg.get("notify", {}).get("ntfy_topic", "")}

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
                self._send(200, json.dumps(status_payload()).encode(), "application/json")
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

    return ThreadingHTTPServer(("127.0.0.1", cfg["settings"]["port"]), Handler)
