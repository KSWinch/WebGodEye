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


def windows_toast(title: str, message: str, url: str):
    launch = f' activationType="protocol" launch="{escape(url, {chr(34): "&quot;"})}"' if url else ""
    xml = (f'<toast{launch} scenario="reminder"><visual><binding template="ToastGeneric">'
           f"<text>{escape(title)}</text><text>{escape(message)}</text></binding></visual>"
           f'<actions><action content="Open" activationType="protocol" arguments="{escape(url or "about:blank", {chr(34): "&quot;"})}"/>'
           f'<action content="Dismiss" activationType="system" arguments="dismiss"/></actions>'
           f'<audio src="ms-winsoundevent:Notification.Reminder"/></toast>')
    env = dict(os.environ, GODEYE_TOAST=xml, GODEYE_APPID=_PS_APP_ID)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                   env=env, timeout=30, check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ntfy(topic: str, title: str, message: str, url: str):
    payload = {"topic": topic, "title": title, "message": message, "priority": 5, "tags": ["rotating_light"]}
    if url:
        payload["click"] = url
    _post_json("https://ntfy.sh/", payload)


def discord(webhook: str, title: str, message: str, url: str, role_id: str = ""):
    ping = f"<@&{role_id}> " if role_id else ""
    _post_json(webhook, {
        "content": f"{ping}**{title}**\n{message}" + (f"\n{url}" if url else ""),
        "allowed_mentions": {"parse": [], "roles": [role_id] if role_id else []},  # ping only this role
    })


def send(cfg: dict, title: str, message: str, url: str = "") -> list[str]:
    """Send to every configured channel. Returns the channels that succeeded."""
    n = cfg.get("notify", {})
    channels = []
    if n.get("windows", True):
        channels.append(("windows", lambda: windows_toast(title, message, url)))
    if n.get("ntfy_topic"):
        channels.append(("ntfy", lambda: ntfy(n["ntfy_topic"], title, message, url)))
    if n.get("discord_webhook"):
        channels.append(("discord", lambda: discord(n["discord_webhook"], title, message, url,
                                                         str(n.get("discord_ping_role", "")))))

    ok = []
    for name, fn in channels:
        try:
            fn()
            ok.append(name)
        except Exception as e:
            log.warning("Alert via %s failed: %s", name, e)
    log.info("ALERT sent (%s): %s — %s", ", ".join(ok) or "no channels", title, message)
    return ok
