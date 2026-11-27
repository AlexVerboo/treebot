"""
Daily triggers for GitHub workflows, started by the bot itself.

Why: GitHub's cron starts jobs 8-12 hours late (the 01:47 "Ingest matches" of Nov 27 started
at 11:39 Mexico City). The bot stays awake thanks to the uptime monitor (ping every 5 minutes),
so on any request it checks, for each job:
  - is it already past its time today (UTC)?
  - has the workflow not run since then?
If both are true, it starts the workflow through the GitHub API (workflow_dispatch), with the
same GH_DISPATCH_TOKEN that "ggs" uses. The GitHub cron stays as a backup.

Jobs:
  daily  "Update Halo records"  DAILY_RUN_UTC  (default 06:17 UTC = 00:17 Mexico City).
         The workflow skips itself if it already ran today.
  night  "Ingest matches" with source=night, which then posts the Night awards
         NIGHT_RUN_UTC (default 07:47 UTC = 01:47 Mexico City, after the session).
         Set NIGHT_RUN_UTC=off to turn it off. awards.py never posts the same night twice.
"""

import datetime as dt
import os
import threading
import time

import requests

import alerts

GH_REPO = os.getenv("GH_REPO", "AlexVerboo/treebot")
CHECK_EVERY = 300  # seconds between checks against the GitHub API (per job)


class Job:
    def __init__(self, name, workflow, at_utc, inputs=None, label=None):
        self.name, self.workflow, self.at_utc = name, workflow, at_utc
        self.inputs = inputs or {}
        self.label = label or workflow
        self.done_date = None
        self.last_check = 0.0
        self.lock = threading.Lock()

    def target_for(self, now):
        hh, mm = (int(x) for x in self.at_utc.split(":"))
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _jobs():
    jobs = [Job("daily", os.getenv("DAILY_WORKFLOW", "update-records.yml"),
                os.getenv("DAILY_RUN_UTC", "06:17"), label="Update Halo records")]
    night = (os.getenv("NIGHT_RUN_UTC") or "07:47").strip()
    if night.lower() not in ("off", "0", "no", "false"):
        jobs.append(Job("night", os.getenv("NIGHT_WORKFLOW", "ingest.yml"), night,
                        inputs={"source": "night"}, label="Ingest matches (night)"))
    return {j.name: j for j in jobs}


JOBS = _jobs()

# Kept for older callers/tests
WORKFLOW = JOBS["daily"].workflow
DAILY_RUN_UTC = JOBS["daily"].at_utc


def _log(msg):
    print(msg, flush=True)


def target_for(now, job="daily"):
    """Today's scheduled time (UTC) for `now`."""
    return JOBS[job].target_for(now)


def _headers(token):
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def runs_since(token, since, http=requests, workflow=None):
    """Runs of the workflow created since `since` (any trigger), not counting cancelled ones."""
    workflow = workflow or JOBS["daily"].workflow
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{workflow}/runs"
    r = http.get(url, headers=_headers(token), timeout=10,
                 params={"created": ">=" + since.strftime("%Y-%m-%dT%H:%M:%SZ"), "per_page": 10})
    r.raise_for_status()
    return [run for run in r.json().get("workflow_runs", [])
            if run.get("conclusion") != "cancelled"]


def dispatch(token, http=requests, workflow=None, inputs=None):
    workflow = workflow or JOBS["daily"].workflow
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{workflow}/dispatches"
    body = {"ref": "master"}
    if inputs:
        body["inputs"] = inputs
    r = http.post(url, headers=_headers(token), json=body, timeout=10)
    r.raise_for_status()


def maybe_run(now=None, token=None, http=requests, clock=time.time, job="daily"):
    """Starts one job's workflow if it is due and has not run. Returns what it did
    (useful for tests and logs). Never raises."""
    j = JOBS.get(job)
    if j is None:
        return "no-job"
    token = (token if token is not None else os.getenv("GH_DISPATCH_TOKEN") or "").strip()
    if not token:
        return "no-token"
    now = now or dt.datetime.now(dt.timezone.utc)
    if not j.lock.acquire(blocking=False):
        return "busy"
    try:
        if j.done_date == now.date():
            return "done"
        target = j.target_for(now)
        if now < target:
            return "not-due"
        if clock() - j.last_check < CHECK_EVERY:
            return "wait"
        j.last_check = clock()
        try:
            if runs_since(token, target, http=http, workflow=j.workflow):
                j.done_date = now.date()
                return "already-ran"
            dispatch(token, http=http, workflow=j.workflow, inputs=j.inputs)
        except requests.exceptions.RequestException as e:
            _log(f"scheduler: GitHub API error ({j.name}): {e!r}")
            alerts.send(f"Could not start '{j.label}' from the bot ({type(e).__name__}). "
                        "GitHub's cron will still try later.", key=f"scheduler-{j.name}")
            return "error"
        j.done_date = now.date()
        _log(f"scheduler: started '{j.label}'")
        return "dispatched"
    finally:
        j.lock.release()


def maybe_run_all(**kwargs):
    """Checks every job. {job name: result}."""
    return {name: maybe_run(job=name, **kwargs) for name in JOBS}


def reset():
    """Only for tests."""
    global JOBS
    JOBS = _jobs()
