"""Persists results to data/state.json so restarts don't re-alert, plus a history of in-stock windows."""
import json
import os
import threading
import time
from dataclasses import asdict

from .config import DATA_DIR

STATE_PATH = DATA_DIR / "state.json"
MAX_HISTORY = 100
_lock = threading.Lock()


class State:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            raw = {}
        if "sources" not in raw:  # older format: the whole file was the per-source dict
            raw = {"sources": raw}
        self.sources: dict[str, dict] = raw["sources"]
        # Each entry: {source, item, url, start, end}. end = None while still in stock.
        self.history: list[dict] = raw.get("history", [])
        self.since: float = raw.get("since") or time.time()
        self.meta: dict = raw.get("meta", {})   # app-wide bits, e.g. date of the last daily summary

    def get(self, sid: str) -> dict:
        return self.sources.setdefault(sid, {})

    def record_success(self, sid: str, result, when: float, hot_ids: list[str]):
        with _lock:
            s = self.get(sid)
            s.update(status=result.status, summary=result.summary, link=result.link,
                     items=[asdict(i) for i in result.items], last_check=when, last_ok=when,
                     error=None, consecutive_errors=0, hot_ids=hot_ids, baselined=True,
                     failing_since=None, fail_alerted=False)
            self._save()

    def record_error(self, sid: str, message: str, when: float):
        with _lock:
            s = self.get(sid)
            s.update(error=message, last_check=when, consecutive_errors=s.get("consecutive_errors", 0) + 1,
                     failing_since=s.get("failing_since") or when)
            self._save()

    def record_availability(self, sid: str, source_name: str, started: list, ended_ids: list[str], when: float):
        """Open a history entry for each item that just came in stock; close entries for ones that sold out."""
        if not started and not ended_ids:
            return
        with _lock:
            for item in started:
                self.history.append({"sid": sid, "item_id": item.id, "source": source_name, "item": item.title,
                                     "url": item.url, "start": when, "end": None})
            for h in self.history:
                if h["sid"] == sid and h["item_id"] in ended_ids and h["end"] is None:
                    h["end"] = when
            self.history = self.history[-MAX_HISTORY:]
            self._save()

    def mark(self, sid: str | None = None, **fields):
        """Set a few fields on a source (or on the app-wide meta when sid is None) and save."""
        with _lock:
            (self.meta if sid is None else self.get(sid)).update(fields)
            self._save()

    def snapshot(self) -> dict:
        with _lock:
            return json.loads(json.dumps({"sources": self.sources, "history": self.history, "since": self.since}))

    def _save(self):
        tmp = STATE_PATH.with_suffix(".tmp")
        data = {"since": self.since, "meta": self.meta, "sources": self.sources, "history": self.history}
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, STATE_PATH)
