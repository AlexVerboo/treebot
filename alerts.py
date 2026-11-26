"""
Alerts to a private Discord channel (#bot-alerts) through a webhook.

- Uses only the standard library, so it works even if `pip install` failed.
- Never raises: an alert that cannot be sent must not break the bot.
- Does nothing if DISCORD_ALERT_WEBHOOK is not set.

From code:
    import alerts
    alerts.send("Halo login failed", key="halo-login")

From a workflow (step with `if: failure()`):
    python alerts.py "Workflow X failed: <link>"
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# The same alert (same key) is sent at most once per MIN_INTERVAL seconds,
# so a broken spreadsheet does not flood the channel with one alert per message.
MIN_INTERVAL = int(os.getenv("ALERT_MIN_INTERVAL", "600"))
_last_sent = {}
_lock = threading.Lock()


def _webhook():
    return (os.getenv("DISCORD_ALERT_WEBHOOK") or "").strip()


def _should_send(key, now):
    if not key:
        return True
    with _lock:
        last = _last_sent.get(key)
        if last is not None and now - last < MIN_INTERVAL:
            return False
        _last_sent[key] = now
        return True


def send(text, key=None, source=None):
    """Sends `text` to Discord. Returns True if it was sent."""
    url = _webhook()
    if not url:
        return False
    if not _should_send(key, time.time()):
        return False
    source = source or os.getenv("ALERT_SOURCE") or ("GitHub Actions" if os.getenv("GITHUB_ACTIONS") else "Render bot")
    content = f"**[{source}]** {text}"[:1900]  # Discord limit: 2000 characters
    body = json.dumps({"content": content, "username": "TreeBot Alerts",
                       "allowed_mentions": {"parse": []}}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "treebot-alerts"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10):
                return True
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                print(f"alerts: Discord answered {e.code}", flush=True)
                return False
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"alerts: could not reach Discord ({e})", flush=True)
        time.sleep(2 * (attempt + 1))
    return False


if __name__ == "__main__":
    message = " ".join(sys.argv[1:]).strip() or "Something failed (no details)."
    ok = send(message)
    print("alert sent" if ok else "alert not sent (no webhook or Discord error)")
