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
