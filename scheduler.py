"""
Daily trigger for "Update Halo records", started by the bot itself.

Why: GitHub's cron was starting the job 8-12 hours late. The bot stays awake
thanks to the uptime monitor (ping every 5 minutes), so on any request it checks:
  - is it already past DAILY_RUN_UTC today? (06:17 UTC = 00:17 Mexico City)
  - has the workflow not run since then?
If both are true, it starts the workflow through the GitHub API (workflow_dispatch),
with the same GH_DISPATCH_TOKEN that "ggs" uses. The GitHub cron stays as a backup,
and the workflow skips itself if it already ran today.
"""

import datetime as dt
import os
import threading
import time

import requests

import alerts

GH_REPO = os.getenv("GH_REPO", "AlexVerboo/treebot")
WORKFLOW = os.getenv("DAILY_WORKFLOW", "update-records.yml")
DAILY_RUN_UTC = os.getenv("DAILY_RUN_UTC", "06:17")
CHECK_EVERY = 300  # seconds between checks against the GitHub API

_state = {"done_date": None, "last_check": 0.0}
_lock = threading.Lock()


def _log(msg):
    print(msg, flush=True)


def target_for(now):
    """Today's scheduled time (UTC) for `now`."""
    hh, mm = (int(x) for x in DAILY_RUN_UTC.split(":"))
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _headers(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def runs_since(token, since, http=requests):
    """Runs of the workflow created since `since` (any trigger), not counting cancelled ones."""
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{WORKFLOW}/runs"
    r = http.get(url, headers=_headers(token), timeout=10,
                 params={"created": ">=" + since.strftime("%Y-%m-%dT%H:%M:%SZ"), "per_page": 10})
    r.raise_for_status()
    return [run for run in r.json().get("workflow_runs", [])
            if run.get("conclusion") != "cancelled"]


def dispatch(token, http=requests):
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{WORKFLOW}/dispatches"
    r = http.post(url, headers=_headers(token), json={"ref": "master"}, timeout=10)
    r.raise_for_status()


def maybe_run(now=None, token=None, http=requests, clock=time.time):
    """Starts the daily workflow if it is due and has not run. Returns what it did
    (useful for tests and logs). Never raises."""
    token = (token if token is not None else os.getenv("GH_DISPATCH_TOKEN") or "").strip()
    if not token:
        return "no-token"
    now = now or dt.datetime.now(dt.timezone.utc)
    if not _lock.acquire(blocking=False):
        return "busy"
    try:
        if _state["done_date"] == now.date():
            return "done"
        target = target_for(now)
        if now < target:
            return "not-due"
        if clock() - _state["last_check"] < CHECK_EVERY:
            return "wait"
        _state["last_check"] = clock()
        try:
            if runs_since(token, target, http=http):
                _state["done_date"] = now.date()
                return "already-ran"
            dispatch(token, http=http)
        except requests.exceptions.RequestException as e:
            _log(f"scheduler: GitHub API error: {e!r}")
            alerts.send(f"Could not start the daily records job from the bot ({type(e).__name__}). "
                        "GitHub's cron will still try later.", key="scheduler")
            return "error"
        _state["done_date"] = now.date()
        _log("scheduler: started the daily 'Update Halo records' workflow")
        return "dispatched"
    finally:
        _lock.release()


def reset():
    """Only for tests."""
    _state.update({"done_date": None, "last_check": 0.0})
