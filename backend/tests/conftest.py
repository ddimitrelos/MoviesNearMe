"""Shared fixtures: an isolated in-memory database per test."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models

# Fixed once at import so repeated make_hall() calls produce identical rows
# (idempotency tests depend on that).
FUTURE = datetime.now().replace(microsecond=0) + timedelta(hours=3)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_hall(slug, name=None, screenings=None, when=None):
    """Build a hall dict in the shape scraper.parse_hall returns."""
    when = when or FUTURE
    rows = screenings if screenings is not None else [
        {
            "movie_slug": f"movie-{slug}",
            "movie_title": f"Movie {slug}",
            "movie_original": None,
            "movie_duration": 100,
            "movie_genre": None,
            "movie_poster": None,
            "movie_url": None,
            "hall": "Hall 1",
            "start_time": when,
        }
    ]
    return {
        "slug": slug,
        "name": name or f"Cinema {slug}",
        "address": "Somewhere 1",
        "phone": "2100000000",
        "lat": 37.98,
        "lng": 23.73,
        "is_summer": False,
        "source_url": f"https://example.test/{slug}",
        "screenings": rows,
    }


def make_halls(count, prefix="hall"):
    return [make_hall(f"{prefix}-{i}") for i in range(count)]


@pytest.fixture
def populated_db(db):
    """A database holding a healthy dataset, as production normally has."""
    from app import scraper

    scraper.publish(db, make_halls(100, "existing"), replace=True)
    assert db.query(models.Cinema).count() == 100
    return db
