"""Loads watch.toml and normalises it into plain dicts the rest of the app uses."""
from datetime import datetime
import re
import secrets
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "watch.toml"
DATA_DIR = ROOT / "data"


class ConfigError(Exception):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "source"


def _ensure_ntfy_topic(cfg: dict) -> None:
    """Give the user a private, hard-to-guess ntfy topic on first run and save it to watch.toml."""
    notify = cfg.setdefault("notify", {})
    if notify.get("ntfy_topic"):
        return
    topic = "godeye-" + secrets.token_hex(6)
    text = CONFIG_PATH.read_text(encoding="utf-8")
    new_text, n = re.subn(r'(?m)^(\s*ntfy_topic\s*=\s*)""', rf'\g<1>"{topic}"', text, count=1)
    if n:
        CONFIG_PATH.write_text(new_text, encoding="utf-8")
        notify["ntfy_topic"] = topic


def load() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError(f"Missing {CONFIG_PATH}")
    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)

    target = cfg.get("target") or {}
    if not target.get("name"):
        raise ConfigError("[target] needs a name")
    target["keywords"] = [k.lower() for k in target.get("keywords") or [target["name"]]]
    target["announce_keywords"] = [k.lower() for k in target.get("announce_keywords") or []]
    target.setdefault("image", "")
    target.setdefault("alert_sizes", [])
    cfg["target"] = target

    settings = cfg.setdefault("settings", {})
    settings.setdefault("port", 8765)
    settings.setdefault("default_interval_minutes", 10)
    settings.setdefault("phone_access", False)
    settings.setdefault("alert_after_failing_hours", 3)   # 0 = never warn about a failing source
    settings.setdefault("daily_summary", "09:00")          # "" = off
    if settings["daily_summary"]:
        try:
            settings["daily_summary"] = datetime.strptime(str(settings["daily_summary"]), "%H:%M").strftime("%H:%M")
        except ValueError:
            raise ConfigError(f'daily_summary must look like "09:00", got {settings["daily_summary"]!r}')

    _ensure_ntfy_topic(cfg)

    sources, seen = [], set()
    for raw in cfg.get("source") or []:
        if not raw.get("enabled", True):
            continue
        if "type" not in raw or "name" not in raw:
            raise ConfigError(f"Every [[source]] needs a name and type: {raw}")
        sid = _slug(raw["name"])
        while sid in seen:
            sid += "-2"
        seen.add(sid)
        src = dict(raw)
        src["id"] = sid
        src["interval_minutes"] = float(raw.get("interval_minutes", settings["default_interval_minutes"]))
        sources.append(src)
    cfg["sources"] = sources
    return cfg
