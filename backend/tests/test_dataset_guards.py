"""
Regression tests for the "production shows only 11 cinemas" incident.

Two independent things went wrong, and each gets a guard here:
  * a thin or partial scrape must never replace/shrink the live dataset;
  * the merge fallback must not leave yesterday's showtimes behind.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from app import models, scraper

from conftest import make_hall, make_halls


# --- replace_decision: the shrink guard --------------------------------------

def test_complete_run_may_replace():
    may, reason = scraper.replace_decision(parsed=109, discovered=109, existing=109)
    assert may is True
    assert reason == "complete run"


def test_eleven_halls_may_not_replace_a_full_dataset():
    """The exact shape of the incident: a handful of halls must not win."""
    may, reason = scraper.replace_decision(parsed=11, discovered=109, existing=109)
    assert may is False
    assert "floor" in reason


def test_partial_run_may_not_replace():
    may, reason = scraper.replace_decision(parsed=40, discovered=109, existing=109)
    assert may is False
    assert "partial run" in reason


def test_run_that_would_shrink_the_dataset_is_refused():
    """Discovery itself can come back short; compare against what we already have."""
    may, reason = scraper.replace_decision(parsed=45, discovered=45, existing=109)
    assert may is False
    assert "shrink" in reason


def test_empty_run_may_not_replace():
    assert scraper.replace_decision(0, 109, 109) == (False, "no halls parsed")


def test_first_ever_run_may_replace_an_empty_database():
    may, _ = scraper.replace_decision(parsed=109, discovered=109, existing=0)
    assert may is True


# --- publish -----------------------------------------------------------------

def test_publish_replace_swaps_the_whole_dataset(populated_db):
    db = populated_db
    scraper.publish(db, make_halls(80, "fresh"), replace=True)
    slugs = {c.slug for c in db.query(models.Cinema).all()}
    assert len(slugs) == 80
    assert not any(s.startswith("existing-") for s in slugs), "old rows must be gone"


def test_publish_merge_keeps_existing_cinemas(populated_db):
    db = populated_db
    scraper.publish(db, make_halls(5, "extra"), replace=False)
    assert db.query(models.Cinema).count() == 105


def test_publish_is_idempotent(populated_db):
    """Re-publishing the same halls must not duplicate screenings."""
    db = populated_db
    before = db.query(models.Screening).count()
    scraper.publish(db, make_halls(100, "existing"), replace=False)
    assert db.query(models.Screening).count() == before


def test_merge_prunes_screenings_that_already_happened(db):
    past = datetime.now() - timedelta(days=3)
    future = datetime.now() + timedelta(hours=5)
    scraper.publish(db, [make_hall("a", when=past)], replace=True)
    assert db.query(models.Screening).count() == 1

    scraper.publish(db, [make_hall("b", when=future)], replace=False)
    remaining = db.query(models.Screening).all()
    assert len(remaining) == 1, "the past screening should have been pruned"
    assert remaining[0].start_time == future


def test_prune_past_screenings_counts_deletions(db):
    past = datetime.now() - timedelta(days=1)
    scraper.publish(db, [make_hall("old", when=past)], replace=True)
    assert scraper.prune_past_screenings(db) == 1
    db.commit()
    assert db.query(models.Screening).count() == 0


# --- run_scrape end to end (no network) --------------------------------------

def _run_scrape_against(db, halls, discovered):
    """Run run_scrape with the network stubbed and the session pinned to `db`."""
    with (
        patch.object(scraper, "scrape_halls", return_value=(halls, discovered, 0)),
        patch.object(scraper, "SessionLocal", return_value=db),
        patch.object(db, "close"),
    ):
        return scraper.run_scrape()


def test_thin_scrape_does_not_wipe_production(populated_db):
    """The core regression: a scrape that returns 11 halls keeps the 100 we had."""
    db = populated_db
    summary = _run_scrape_against(db, make_halls(11, "thin"), discovered=109)

    assert summary["replaced"] is False
    assert db.query(models.Cinema).count() == 111, "existing cinemas must survive"
    assert db.query(models.Cinema).filter_by(slug="existing-0").one_or_none()


def test_failed_scrape_leaves_data_untouched(populated_db):
    db = populated_db
    summary = _run_scrape_against(db, [], discovered=109)

    assert summary["halls"] == 0
    assert summary["replaced"] is False
    assert db.query(models.Cinema).count() == 100


def test_healthy_scrape_replaces_the_dataset(populated_db):
    db = populated_db
    summary = _run_scrape_against(db, make_halls(109, "fresh"), discovered=109)

    assert summary["replaced"] is True
    assert db.query(models.Cinema).count() == 109
    assert db.query(models.Cinema).filter_by(slug="existing-0").one_or_none() is None


def test_scrape_records_status_for_health(populated_db):
    _run_scrape_against(populated_db, make_halls(109, "fresh"), discovered=109)
    last = scraper.last_run()
    assert last["ok"] is True
    assert last["halls"] == 109
    assert last["replaced"] is True
    assert last["consecutive_failures"] == 0
    assert last["finished_at"]


def test_scrape_error_is_recorded_and_counted(populated_db):
    with (
        patch.object(scraper, "scrape_halls", side_effect=RuntimeError("boom")),
        patch.object(scraper, "SessionLocal", return_value=populated_db),
    ):
        scraper.run_scrape()
        first = scraper.last_run()["consecutive_failures"]
        scraper.run_scrape()
        second = scraper.last_run()["consecutive_failures"]

    assert scraper.last_run()["ok"] is False
    assert second == first + 1, "repeated failures must escalate the backoff"
    assert populated_db.query(models.Cinema).count() == 100


# --- progressive bootstrap ---------------------------------------------------
# Context: a cold start whose snapshot had expired (new programme week) showed
# "0 cinemas" for the ~3 minutes a full scrape takes on the free instance,
# because nothing was written until the very end.

def test_scrape_halls_hands_back_batches_as_they_arrive():
    urls = [f"https://example.test/{i}" for i in range(20)]
    batches = []

    with (
        patch.object(scraper, "discover_hall_urls", return_value=urls),
        patch.object(
            scraper, "_fetch_and_parse", side_effect=lambda c, u: make_hall(u)
        ),
    ):
        halls, discovered, errors = scraper.scrape_halls(
            on_batch=batches.append, batch_size=6
        )

    assert (len(halls), discovered, errors) == (20, 20, 0)
    assert [len(b) for b in batches] == [6, 6, 6, 2], "final partial batch too"


def test_failed_halls_are_counted_and_never_published():
    urls = [f"https://example.test/{i}" for i in range(10)]
    batches = []

    def flaky(_client, url):
        return None if url.endswith(("1", "3", "5")) else make_hall(url)

    with (
        patch.object(scraper, "discover_hall_urls", return_value=urls),
        patch.object(scraper, "_fetch_and_parse", side_effect=flaky),
    ):
        halls, discovered, errors = scraper.scrape_halls(
            on_batch=batches.append, batch_size=3
        )

    assert (len(halls), discovered, errors) == (7, 10, 3)
    assert sum(len(b) for b in batches) == 7
    assert all(h is not None for b in batches for h in b)


def test_empty_database_is_filled_progressively(db):
    """The fix for "0 cinemas": cinemas appear while the scrape is still running."""
    halls = make_halls(24, "boot")
    visible_during_run = []

    def fake_scrape(limit=None, on_batch=None, batch_size=8):
        assert on_batch is not None, "an empty DB must publish as it goes"
        for start in range(0, len(halls), 8):
            on_batch(halls[start:start + 8])
            visible_during_run.append(db.query(models.Cinema).count())
        return halls, 24, 0

    with (
        patch.object(scraper, "scrape_halls", side_effect=fake_scrape),
        patch.object(scraper, "SessionLocal", return_value=db),
        patch.object(db, "close"),
    ):
        summary = scraper.run_scrape()

    assert summary["bootstrapped"] is True
    assert visible_during_run == [8, 16, 24], visible_during_run


def test_a_healthy_database_still_gets_one_atomic_write(populated_db):
    """With good data in place there is something to protect: no partial writes."""
    captured = {}

    def fake_scrape(limit=None, on_batch=None, batch_size=8):
        captured["on_batch"] = on_batch
        return make_halls(100, "fresh"), 100, 0

    with (
        patch.object(scraper, "scrape_halls", side_effect=fake_scrape),
        patch.object(scraper, "SessionLocal", return_value=populated_db),
        patch.object(populated_db, "close"),
    ):
        summary = scraper.run_scrape()

    assert captured["on_batch"] is None
    assert summary["bootstrapped"] is False
    assert summary["replaced"] is True


def test_a_bad_bootstrap_batch_does_not_abort_the_run(db):
    """One unwritable batch must not cost us the rest of the scrape."""
    halls = make_halls(16, "boot")

    def fake_scrape(limit=None, on_batch=None, batch_size=8):
        on_batch(["not-a-hall"])          # would raise inside publish
        on_batch(halls[:8])
        return halls, 16, 0

    with (
        patch.object(scraper, "scrape_halls", side_effect=fake_scrape),
        patch.object(scraper, "SessionLocal", return_value=db),
        patch.object(db, "close"),
    ):
        summary = scraper.run_scrape()

    assert summary["halls"] == 16


def test_current_cinema_count_ignores_yesterday(db):
    day = datetime(2026, 9, 17)
    scraper.publish(
        db, [make_hall(f"c-{i}", when=day.replace(hour=20)) for i in range(5)],
        replace=True,
    )
    assert scraper.current_cinema_count(db, now=day.replace(hour=23)) == 5
    assert scraper.current_cinema_count(db, now=day + timedelta(days=1)) == 0
