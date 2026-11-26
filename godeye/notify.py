"""Alert channels: Windows toast, ntfy.sh phone push, Discord webhook. Each fails independently."""
import json
import logging
import os
import subprocess
import urllib.request
from xml.sax.saxutils import escape

log = logging.getLogger("godeye")

# PowerShell's own registered AppID, so the toast shows without installing anything.
_PS_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_PS_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:GODEYE_TOAST)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:GODEYE_APPID).Show($toast)
"""


def _post_json(url: str, payload: dict):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "WebGodEye"})
    urllib.request.urlopen(req, timeout=15).read()


# How loud each kind of alert is. restock = the real thing; warning = something needs a look;
# info = routine (daily "still watching" message: no desktop popup, no sound on the phone, no role ping).
KINDS = {
    "restock": {"windows": True, "ntfy_priority": 5, "tag": "rotating_light", "ping": True},
    "warning": {"windows": True, "ntfy_priority": 4, "tag": "warning", "ping": False},
    "info":    {"windows": False, "ntfy_priority": 2, "tag": "eyes", "ping": False},
}


def _attr(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def windows_toast(title: str, message: str, links: list[tuple[str, str]], loud: bool):
    url = links[0][1] if links else ""
    launch = f' activationType="protocol" launch="{_attr(url)}"' if url else ""
    buttons = "".join(f'<action content="{_attr(label)}" activationType="protocol" arguments="{_attr(u)}"/>'
                      for label, u in links[:4])
    xml = (f'<toast{launch}{" scenario=\"reminder\"" if loud else ""}><visual><binding template="ToastGeneric">'
           f"<text>{escape(title)}</text><text>{escape(message)}</text></binding></visual>"
           f'<actions>{buttons}<action content="Dismiss" activationType="system" arguments="dismiss"/></actions>'
           f'<audio src="ms-winsoundevent:Notification.{"Reminder" if loud else "Default"}"/></toast>')
    env = dict(os.environ, GODEYE_TOAST=xml, GODEYE_APPID=_PS_APP_ID)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                   env=env, timeout=30, check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ntfy(topic: str, title: str, message: str, links: list[tuple[str, str]], priority: int, tag: str):
    payload = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": [tag]}
    if links:
        payload["click"] = links[0][1]
        payload["actions"] = [{"action": "view", "label": label, "url": u, "clear": True} for label, u in links[:3]]
    _post_json("https://ntfy.sh/", payload)


def discord(webhook: str, title: str, message: str, links: list[tuple[str, str]], role_id: str = ""):
    ping = f"<@&{role_id}> " if role_id else ""
    link_line = " · ".join(f"[{label}](<{u}>)" for label, u in links)  # <> = no big link previews
    _post_json(webhook, {
        "content": f"{ping}**{title}**\n{message}" + (f"\n{link_line}" if link_line else ""),
        "allowed_mentions": {"parse": [], "roles": [role_id] if role_id else []},  # ping only this role
    })


def send(cfg: dict, title: str, message: str, links: list[tuple[str, str]] | None = None,
         kind: str = "restock") -> list[str]:
    """Send to every configured channel. links = [(label, url), ...]; the first is where a tap goes.
    Returns the channels that succeeded."""
    n, k, links = cfg.get("notify", {}), KINDS[kind], [(l, u) for l, u in (links or []) if u]
    channels = []
    if n.get("windows", True) and k["windows"]:
        channels.append(("windows", lambda: windows_toast(title, message, links, kind == "restock")))
    if n.get("ntfy_topic"):
        channels.append(("ntfy", lambda: ntfy(n["ntfy_topic"], title, message, links,
                                              k["ntfy_priority"], k["tag"])))
    if n.get("discord_webhook"):
        role = str(n.get("discord_ping_role", "")) if k["ping"] else ""
        channels.append(("discord", lambda: discord(n["discord_webhook"], title, message, links, role)))

    ok = []
    for name, fn in channels:
        try:
            fn()
            ok.append(name)
        except Exception as e:
            log.warning("Alert via %s failed: %s", name, e)
    log.info("%s sent (%s): %s — %s", kind.upper(), ", ".join(ok) or "no channels", title, message)
    return ok

