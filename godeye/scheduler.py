"""Runs every source on its own interval (with jitter) on one background thread, and decides when to alert.
Also: warns when a source keeps failing, and sends the daily "still watching" message."""
import logging
import random
import threading
import time
from datetime import datetime

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
        self.started = now
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
            self._housekeeping()
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
            if alerts:
                self._maybe_failing_alert(src, msg, now)
            return None
        finally:
            self.running = None

        prev = self.state.get(sid)
        prev_hot = set(prev.get("hot_ids", []))
        hot_ids = [i.id for i in result.items if i.hot]
        new_hot = [i for i in result.items if i.hot and i.id not in prev_hot]
        ended = [i for i in prev_hot if i not in hot_ids]  # was in stock last time, isn't now
        first_run = not prev.get("baselined")
        was_fail_alerted = prev.get("fail_alerted")
        self.state.record_success(sid, result, now, hot_ids)
        self.state.record_availability(sid, src["name"], new_hot, ended, now)
        self.backoff_min.pop(sid, None)
        self.next_run[sid] = now + _jitter(interval)
        log.info("%s: %s — %s", src["name"], result.status, result.summary)

        if alerts and new_hot and not (first_run and checker.baseline_first_run):
            self._alert(src, result, new_hot)
        if alerts and was_fail_alerted:
            notify.send(self.cfg, f"Working again: {src['name']}", "Checks are succeeding again.",
                        [("Open page", result.link)], kind="info")
        return result

    def _alert(self, src, result, new_hot):
        name = self.cfg["target"]["name"]
        title = f"{name}: new mention" if result.status == "match" else f"IN STOCK: {name}"
        message = f"{src['name']}: " + "; ".join(i.title for i in new_hot[:3])
        first = new_hot[0]
        notify.send(self.cfg, title, message, [("Buy now", first.buy_url), ("Product page", first.url or result.link)])

    def _maybe_failing_alert(self, src: dict, msg: str, now: float):
        """One warning when a source has been failing for a while (the store may have moved or blocked it)."""
        hours = self.cfg["settings"]["alert_after_failing_hours"]
        st = self.state.get(src["id"])
        if not hours or st.get("fail_alerted") or now - st.get("failing_since", now) < hours * 3600:
            return
        self.state.mark(src["id"], fail_alerted=True)
        down_h = (now - st["failing_since"]) / 3600
        notify.send(self.cfg, f"Check failing: {src['name']}",
                    f"Hasn't worked for {down_h:.0f} h, so a restock there could be missed.\nLast error: {msg}",
                    [("Open page", src.get("url") or src.get("store", ""))], kind="warning")

    # ── once-a-loop jobs ────────────────────────────────────────────────────
    def _housekeeping(self):
        try:
            self._maybe_daily_summary(time.time())
        except Exception:
            log.exception("Daily summary failed")

    def _maybe_daily_summary(self, now: float):
        at = self.cfg["settings"]["daily_summary"]
        today = datetime.now().strftime("%Y-%m-%d")
        # Wait ~2 min after start-up so every source has had a fresh check first.
        if (not at or datetime.now().strftime("%H:%M") < at or now - self.started < 120
                or self.state.meta.get("last_summary") == today):
            return
        self.state.mark(None, last_summary=today)
        notify.send(self.cfg, f"Still watching {self.cfg['target']['name']}", self.summary_text(now),
                    [("Dashboard", self.phone_url())], kind="info")

    def summary_text(self, now: float) -> str:
        snap = self.state.snapshot()
        checked = [s for s in self.sources if s["type"] != "link"]
        failing = [s["name"] for s in checked if snap["sources"].get(s["id"], {}).get("error")]
        hot = [s["name"] for s in checked if snap["sources"].get(s["id"], {}).get("hot_ids")]
        recent = [h for h in snap["history"] if h["start"] >= now - 86400]
        lines = ["In stock now at: " + ", ".join(hot) if hot else "Nothing in stock right now."]
        if recent:
            lines.append(f"{len(recent)} restock{'s' if len(recent) != 1 else ''} in the last 24 h.")
        lines.append(f"{len(checked) - len(failing)}/{len(checked)} sources checking fine.")
        if failing:
            lines.append("Failing: " + ", ".join(failing))
        return "\n".join(lines)

    def phone_url(self) -> str:
        if not self.cfg["settings"].get("phone_access"):
            return ""
        from .web import lan_ip
        ip = lan_ip()
        return f"http://{ip}:{self.cfg['settings']['port']}" if ip else ""
