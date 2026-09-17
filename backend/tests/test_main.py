"""
Startup bootstrap, the refresh policy, and the health report.

The incident these cover: a cold-started instance served eleven invented
cinemas from seed.py while reporting status "ok", and the next refresh attempt
was a full day away.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from app import main, models, scraper

from conftest import make_hall, make_halls


# --- startup bootstrap -------------------------------------------------------

def _run_bootstrap(db, snapshot_result=None):
    started = []

    def capture_thread(*args, **kwargs):
        t = MagicMock()
        target = kwargs.get("target") or (args[0] if args else None)
        t.start = lambda: started.append(target)
        return t

    with (
        patch.object(main, "SessionLocal", return_value=db),
        patch.object(db, "close"),
        patch.object(main.threading, "Thread", side_effect=capture_thread),
        patch.object(main.seed_module, "seed") as mock_seed,
        patch.object(
            main.snapshot, "load_into", return_value=snapshot_result
        ) as mock_load,
    ):
        main.bootstrap_data()

    return started, mock_seed, mock_load


def test_bootstrap_never_loads_fake_seed_data(db):
    """The regression: an empty database must not be filled with invented cinemas."""
    _, mock_seed, _ = _run_bootstrap(db)
    mock_seed.assert_not_called()


def test_bootstrap_loads_the_snapshot_when_the_database_is_empty(db):
    _, _, mock_load = _run_bootstrap(db, snapshot_result={"halls": 109})
    mock_load.assert_called_once()


def test_bootstrap_loads_the_snapshot_when_all_data_is_in_the_past(db):
    """A restart mid-week must not leave the map empty."""
    scraper.publish(
        db,
        make_halls(50, "stale"),
        replace=True,
    )
    for s in db.query(models.Screening).all():
        s.start_time = datetime.now() - timedelta(days=2)
    db.commit()

    _, _, mock_load = _run_bootstrap(db, snapshot_result={"halls": 109})
    mock_load.assert_called_once()


def test_bootstrap_keeps_healthy_data_instead_of_reloading(db):
    """A restart with a persistent disk should not throw away good live data."""
    scraper.publish(db, make_halls(60, "good"), replace=True)

    _, _, mock_load = _run_bootstrap(db)
    mock_load.assert_not_called()


def test_bootstrap_starts_the_supervisor(db):
    started, _, _ = _run_bootstrap(db)
    assert main._scrape_supervisor in started


def test_bootstrap_survives_a_broken_snapshot(db):
    """A snapshot failure must not stop the API from starting."""
    with (
        patch.object(main, "SessionLocal", return_value=db),
        patch.object(db, "close"),
        patch.object(main.threading, "Thread"),
        patch.object(main.snapshot, "load_into", side_effect=OSError("disk gone")),
    ):
        main.bootstrap_data()  # must not raise


# --- refresh policy ----------------------------------------------------------

FRESH = {"cinemas": 109, "movies": 100, "screenings": 2664,
         "upcoming_screenings": 700, "cinemas_with_upcoming": 104,
         "cinemas_with_current_data": 108}

OK_RUN = {"ok": True, "finished_at": datetime.now().isoformat(),
          "consecutive_failures": 0}


def test_no_scrape_needed_when_data_is_fresh():
    due, reason = main.needs_scrape(FRESH, OK_RUN)
    assert due is False
    assert reason == "data is fresh"


def test_scrape_needed_when_only_a_few_cinemas_have_showtimes():
    """Eleven cinemas must trigger an immediate refresh, not a 24 h wait."""
    thin = {**FRESH, "cinemas_with_current_data": 11}
    due, reason = main.needs_scrape(thin, OK_RUN)
    assert due is True
    assert "11 cinemas" in reason


def test_no_scrape_storm_at_the_end_of_a_programme_week():
    """
    Athinorama publishes one week at a time (Thu-Wed). Late on the last night
    every screening it listed is in the past, which must not be read as a
    failure - otherwise the supervisor re-scrapes every 5 minutes for hours.
    """
    end_of_week = {**FRESH, "upcoming_screenings": 0, "cinemas_with_upcoming": 0}
    due, reason = main.needs_scrape(end_of_week, OK_RUN)
    assert due is False, reason


def test_scrape_needed_before_the_first_successful_run():
    never = {"ok": None, "finished_at": None, "consecutive_failures": 0}
    due, reason = main.needs_scrape(FRESH, never)
    assert due is True
    assert reason == "no successful scrape yet"


def test_scrape_needed_when_the_last_run_is_stale():
    old = {
        "ok": True,
        "finished_at": (
            datetime.now() - timedelta(hours=main.REFRESH_AFTER_HOURS + 1)
        ).isoformat(),
        "consecutive_failures": 0,
    }
    due, reason = main.needs_scrape(FRESH, old)
    assert due is True
    assert "ago" in reason


def test_scrape_needed_after_a_failure():
    failed = {"ok": False, "finished_at": datetime.now().isoformat(),
              "consecutive_failures": 2}
    due, _ = main.needs_scrape(FRESH, failed)
    assert due is True


def test_failure_backoff_grows_then_caps():
    waits = [main._backoff_seconds(n) for n in range(1, 7)]
    assert waits[0] == main.FAILURE_BACKOFF[0]
    assert waits == sorted(waits), "backoff must never shrink"
    assert waits[-1] == main.FAILURE_BACKOFF[-1], "backoff must cap"
    assert main._backoff_seconds(0) == 0


def test_only_one_scrape_runs_at_a_time():
    main._scrape_lock.acquire()
    try:
        assert "skipped" in main.scrape_now()
    finally:
        main._scrape_lock.release()


# --- health ------------------------------------------------------------------

def test_health_is_ok_with_a_full_dataset(db):
    scraper.publish(db, make_halls(60, "ok"), replace=True)
    body = main.health(db)

    assert body["status"] == "ok"
    assert body["cinemas"] == 60
    assert body["cinemas_with_upcoming"] == 60
    assert "last_scrape" in body and "snapshot" in body


def test_health_reports_degraded_when_only_a_few_cinemas_show(db):
    """The old /health said "ok" while serving eleven fake cinemas."""
    scraper.publish(db, make_halls(11, "thin"), replace=True)
    body = main.health(db)

    assert body["status"] == "degraded"
    assert body["cinemas_with_upcoming"] == 11


def test_health_reports_degraded_on_an_empty_database(db):
    assert main.health(db)["status"] == "degraded"


def test_todays_listings_count_even_after_the_last_show(db):
    """
    The end-of-programme-week case, measured against the real database.

    At 23:59 on the last night of a published week nothing is "upcoming", but
    the week's data is present and correct - so this must not read as a failure.
    """
    day = datetime(2026, 9, 16)
    scraper.publish(
        db,
        [make_hall(f"t-{i}", when=day.replace(hour=20)) for i in range(40)],
        replace=True,
    )

    state = main._data_state(db, now=day.replace(hour=23, minute=59))

    assert state["cinemas_with_upcoming"] == 0
    assert state["cinemas_with_current_data"] == 40
    assert main.needs_scrape(state, OK_RUN)[0] is False


def test_yesterdays_listings_do_not_count_as_current(db):
    """The flip side: genuinely stale data must still trigger a refresh."""
    day = datetime(2026, 9, 16)
    scraper.publish(
        db,
        [make_hall(f"t-{i}", when=day.replace(hour=20)) for i in range(40)],
        replace=True,
    )

    state = main._data_state(db, now=day + timedelta(days=1))

    assert state["cinemas_with_current_data"] == 0
    assert main.needs_scrape(state, OK_RUN)[0] is True


def test_health_reports_where_the_database_lives(db):
    body = main.health(db)
    assert "path" in body["db"]
    assert isinstance(body["db"]["persistent"], bool)


# --- admin -------------------------------------------------------------------

def test_seeding_is_refused_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_SEED", raising=False)
    with pytest.raises(HTTPException) as e:
        main.trigger_seed()
    assert e.value.status_code == 403


def test_seeding_is_allowed_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_SEED", "1")
    with patch.object(main.seed_module, "seed") as mock_seed:
        assert main.trigger_seed() == {"status": "seeded"}
    mock_seed.assert_called_once()


# --- uptime checkers ---------------------------------------------------------

def test_health_answers_head_as_well_as_get(db):
    """
    Uptime checkers send HEAD by default.

    A GET-only route answers 405, which reads as "down". The UptimeRobot
    monitor for this service reported down for ~2 months for exactly that
    reason while the API was fine, so the only external alarm was worthless.
    """
    from fastapi.testclient import TestClient

    main.app.dependency_overrides[main.get_db] = lambda: db
    try:
        client = TestClient(main.app)
        assert client.head("/health").status_code == 200
        assert client.get("/health").status_code == 200
    finally:
        main.app.dependency_overrides.clear()
