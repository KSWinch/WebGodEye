"""python -m godeye              run the watcher + dashboard (opens your browser)
python -m godeye --once       check every source once, print results, no alerts
python -m godeye --test-notify  send a test alert to every configured channel
python -m godeye --make-image URL  make assets/target.png (transparent product picture) from a photo
"""
import argparse
import logging
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler

from . import config, notify, web
from .checkers import load_all
from .scheduler import Scheduler
from .state import State


def setup_logging(console: bool = True):
    config.DATA_DIR.mkdir(exist_ok=True)
    handlers = [RotatingFileHandler(config.DATA_DIR / "godeye.log", maxBytes=1_000_000, backupCount=1,
                                    encoding="utf-8")]
    if console and sys.stdout:  # pythonw has no console
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", handlers=handlers)


def main():
    ap = argparse.ArgumentParser(prog="godeye")
    ap.add_argument("--once", action="store_true", help="check every source once and print results")
    ap.add_argument("--test-notify", action="store_true", help="send a test alert to every channel")
    ap.add_argument("--make-image", metavar="URL_OR_FILE", help="build assets/target.png from a product photo")
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard on start")
    args = ap.parse_args()

    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.make_image:
        from .imagetool import make
        print("Saved", make(args.make_image))
        return

    setup_logging(console=not args.once)
    cfg = config.load()
    load_all()
    url = f"http://127.0.0.1:{cfg['settings']['port']}"

    if args.test_notify:
        ok = notify.send(cfg, f"WebGodEye test: {cfg['target']['name']}",
                         "If you can see this, alerts work.", [("Open dashboard", url)])
        print("Delivered via:", ", ".join(ok) or "nothing")
        if cfg["notify"].get("ntfy_topic"):
            print(f"Phone: install the ntfy app and subscribe to topic  {cfg['notify']['ntfy_topic']}")
        return

    state = State()
    sched = Scheduler(cfg, state)

    if args.once:
        for src in cfg["sources"]:
            r = sched.run_one(src, alerts=False)
            print(f"\n[{src['name']}]")
            if r is None:
                print("  ERROR:", state.get(src["id"]).get("error"))
                continue
            print(f"  {r.status}: {r.summary}\n  {r.link}")
            for i in r.items[:8]:
                print(f"    {'*' if i.hot else '-'} {i.title}  {i.note}")
        return

    try:
        server = web.make_server(cfg, state, sched)
    except OSError:  # already running: just show the existing dashboard
        webbrowser.open(url)
        return
    threading.Thread(target=sched.run_forever, daemon=True, name="scheduler").start()
    logging.getLogger("godeye").info("WebGodEye watching %s — dashboard at %s", cfg["target"]["name"], url)
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
