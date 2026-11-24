"""Runs every source on its own interval (with jitter) on one background thread, and decides when to alert."""
import logging
import random
import threading
import time

from . import notify
from .checkers import REGISTRY
from .fetch import FetchError

log = logging.getLogger("godeye")
MAX_BACKOFF_MIN = 120


def _jitter(minutes: float) -> float:
    return minutes * 60 * random.uniform(0.8, 1.2)


class Scheduler:
    def __init__(self, cfg: dict, state):
        self.cfg, self.state = cfg, state
        self.sources = cfg["sources"]
        self.backoff_min: dict[str, float] = {}
        self.running: str | None = None
        self.heartbeat: float | None = None   # updated every loop; lets the dashboard spot a stuck checker
        self._wake = threading.Event()
        now = time.time()
        # Stagger start-up so two sources on the same store don't fire at the same moment.
        self.next_run = {s["id"]: now + i * 8 for i, s in enumerate(self.sources)}

    def request_check(self, sid: str) -> bool:
        if sid not in self.next_run:
            return False
        self.next_run[sid] = 0
        self._wake.set()
        return True

    def run_forever(self):
        while True:
            self.heartbeat = time.time()
            for src in self.sources:
                if self.next_run[src["id"]] <= time.time():
                    self.run_one(src)
            self._wake.wait(timeout=2)
            self._wake.clear()

    def run_one(self, src: dict, alerts: bool = True):
        sid, interval = src["id"], src["interval_minutes"]
        checker = REGISTRY.get(src["type"])
        now = time.time()
        self.running = sid
        try:
            if checker is None:
                raise FetchError(f"Unknown source type '{src['type']}'")
            result = checker.fn(src, self.cfg["target"])
        except Exception as e:
            msg = str(e) if isinstance(e, FetchError) else f"{e.__class__.__name__}: {e}"
            self.state.record_error(sid, msg, now)
            if getattr(e, "status", None) == 429:
                self.backoff_min[sid] = min(max(self.backoff_min.get(sid, 0) * 2, interval * 2), MAX_BACKOFF_MIN)
                self.next_run[sid] = now + self.backoff_min[sid] * 60
            else:
                self.next_run[sid] = now + _jitter(interval)
            log.warning("%s: %s", src["name"], msg)
            return None
        finally:
            self.running = None

        prev = self.state.get(sid)
        new_hot = [i for i in result.items if i.hot and i.id not in prev.get("hot_ids", [])]
        first_run = not prev.get("baselined")
        self.state.record_success(sid, result, now, [i.id for i in result.items if i.hot])
        self.backoff_min.pop(sid, None)
        self.next_run[sid] = now + _jitter(interval)
        log.info("%s: %s — %s", src["name"], result.status, result.summary)

        if alerts and new_hot and not (first_run and checker.baseline_first_run):
            self._alert(src, result, new_hot)
        return result

    def _alert(self, src, result, new_hot):
        name = self.cfg["target"]["name"]
        title = f"{name}: new mention" if result.status == "match" else f"IN STOCK: {name}"
        message = f"{src['name']}: " + "; ".join(i.title for i in new_hot[:3])
        notify.send(self.cfg, title, message, new_hot[0].url or result.link)
