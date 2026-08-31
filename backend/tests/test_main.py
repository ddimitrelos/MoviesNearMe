"""Tests for startup bootstrap and daily scrape scheduling."""

from unittest.mock import patch, MagicMock
from app.main import _daily_scrape_loop


def _run_bootstrap(db_count):
    from app.main import bootstrap_data

    mock_db = MagicMock()
    mock_db.query.return_value.scalar.return_value = db_count

    started_targets = []

    def capture_thread(*args, **kwargs):
        t = MagicMock()
        target = kwargs.get("target") or (args[0] if args else None)
        t.start = lambda: started_targets.append(target)
        return t

    mock_scrape = MagicMock()
    with (
        patch("app.main.SessionLocal", return_value=mock_db),
        patch("app.main.threading.Thread", side_effect=capture_thread),
        patch("app.main.seed_module.seed") as mock_seed,
        patch("app.main.scraper.run_scrape", mock_scrape),
    ):
        bootstrap_data()

    return started_targets, mock_seed, mock_scrape


def test_bootstrap_always_scrapes_on_startup():
    """A scrape is always started at startup so restarts don't leave stale seed data."""
    targets, _, mock_scrape = _run_bootstrap(db_count=42)
    assert mock_scrape in targets, "scraper must start even when DB already has data"
    assert _daily_scrape_loop in targets, "daily scrape loop must always be started"


def test_bootstrap_seeds_when_db_empty():
    """On an empty DB, seed runs immediately and the scraper is also started."""
    targets, mock_seed, mock_scrape = _run_bootstrap(db_count=0)
    mock_seed.assert_called_once()
    assert mock_scrape in targets, "scraper must also start on a fresh DB"
