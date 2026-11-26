import datetime as dt

import pytest
import requests

import scheduler

UTC = dt.timezone.utc


class FakeGitHub:
    def __init__(self, runs=None, fail=False):
        self.runs = runs or []
        self.fail = fail
        self.dispatched = 0

    def get(self, url, **kw):
        if self.fail:
            raise requests.exceptions.ConnectionError("down")
        return _Resp({"workflow_runs": self.runs})

    def post(self, url, **kw):
        self.dispatched += 1
        return _Resp({}, 204)


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _reset():
    scheduler.reset()
    yield
    scheduler.reset()


def at(h, m):
    return dt.datetime(2026, 11, 27, h, m, tzinfo=UTC)


def test_no_token_does_nothing():
    assert scheduler.maybe_run(at(7, 0), token="") == "no-token"


def test_not_due_before_target():
    gh = FakeGitHub()
    assert scheduler.maybe_run(at(6, 0), token="t", http=gh) == "not-due"
    assert gh.dispatched == 0


def test_dispatches_once_per_day():
    gh = FakeGitHub()
    assert scheduler.maybe_run(at(6, 20), token="t", http=gh, clock=lambda: 1000) == "dispatched"
    assert scheduler.maybe_run(at(6, 30), token="t", http=gh, clock=lambda: 2000) == "done"
    assert gh.dispatched == 1


def test_skips_if_already_ran():
    gh = FakeGitHub(runs=[{"id": 1, "conclusion": "success"}])
    assert scheduler.maybe_run(at(9, 0), token="t", http=gh) == "already-ran"
    assert gh.dispatched == 0


def test_cancelled_runs_do_not_count():
    gh = FakeGitHub(runs=[{"id": 1, "conclusion": "cancelled"}])
    assert scheduler.maybe_run(at(9, 0), token="t", http=gh) == "dispatched"


def test_api_error_alerts_and_waits(sent_alerts):
    gh = FakeGitHub(fail=True)
    assert scheduler.maybe_run(at(9, 0), token="t", http=gh, clock=lambda: 1000) == "error"
    assert sent_alerts and sent_alerts[0][1] == "scheduler"
    # Does not hammer the API: waits CHECK_EVERY seconds before trying again
    assert scheduler.maybe_run(at(9, 1), token="t", http=gh, clock=lambda: 1060) == "wait"


def test_new_day_runs_again():
    gh = FakeGitHub()
    scheduler.maybe_run(at(6, 20), token="t", http=gh, clock=lambda: 1000)
    next_day = at(6, 20) + dt.timedelta(days=1)
    assert scheduler.maybe_run(next_day, token="t", http=gh, clock=lambda: 90000) == "dispatched"
    assert gh.dispatched == 2
