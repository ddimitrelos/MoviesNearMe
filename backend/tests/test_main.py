"""Tests for startup bootstrap and daily scrape scheduling."""

from unittest.mock import patch, MagicMock


def test_bootstrap_starts_daily_loop_when_db_has_data():
    """Daily scrape thread is always started, even when the DB is already populated."""
    from app.main import bootstrap_data

    mock_db = MagicMock()
    mock_db.query.return_value.scalar.return_value = 42  # non-empty DB

    started_threads = []

    def capture_thread(*args, **kwargs):
        t = MagicMock()
        t.start = lambda: started_threads.append(kwargs.get("target", args[0] if args else None))
        return t

    with (
        patch("app.main.SessionLocal", return_value=mock_db),
        patch("app.main.threading.Thread", side_effect=capture_thread),
    ):
        bootstrap_data()

    from app.main import _daily_scrape_loop
    assert _daily_scrape_loop in started_threads, "daily scrape loop must be started on startup"


def test_bootstrap_seeds_and_scrapes_when_db_empty():
    """On an empty DB, seed runs immediately and a scrape thread is started."""
    from app.main import bootstrap_data

    mock_db = MagicMock()
    mock_db.query.return_value.scalar.return_value = 0  # empty DB

    started_threads = []

    def capture_thread(*args, **kwargs):
        t = MagicMock()
        t.start = lambda: started_threads.append(kwargs.get("target", args[0] if args else None))
        return t

    with (
        patch("app.main.SessionLocal", return_value=mock_db),
        patch("app.main.threading.Thread", side_effect=capture_thread),
        patch("app.main.seed_module.seed") as mock_seed,
        patch("app.main.scraper.run_scrape"),
    ):
        bootstrap_data()

    mock_seed.assert_called_once()
    from app.main import _daily_scrape_loop
    assert _daily_scrape_loop in started_threads, "daily scrape loop must be started even on fresh DB"
