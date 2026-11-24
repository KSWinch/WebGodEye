"""Persists the latest result of every source to data/state.json so restarts don't re-alert."""
import json
import os
import threading
from dataclasses import asdict

from .config import DATA_DIR

STATE_PATH = DATA_DIR / "state.json"
_lock = threading.Lock()


class State:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        try:
            self.sources: dict[str, dict] = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.sources = {}

    def get(self, sid: str) -> dict:
        return self.sources.setdefault(sid, {})

    def record_success(self, sid: str, result, when: float, hot_ids: list[str]):
        with _lock:
            s = self.get(sid)
            s.update(status=result.status, summary=result.summary, link=result.link,
                     items=[asdict(i) for i in result.items], last_check=when, last_ok=when,
                     error=None, consecutive_errors=0, hot_ids=hot_ids, baselined=True)
            self._save()

    def record_error(self, sid: str, message: str, when: float):
        with _lock:
            s = self.get(sid)
            s.update(error=message, last_check=when, consecutive_errors=s.get("consecutive_errors", 0) + 1)
            self._save()

    def snapshot(self) -> dict:
        with _lock:
            return json.loads(json.dumps(self.sources))

    def _save(self):
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.sources, indent=1), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
