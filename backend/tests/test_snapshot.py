"""
The committed snapshot is what a cold-started instance serves before its first
scrape finishes. It replaced the invented sample data, so these tests check it
is present, real, and loadable.
"""

from datetime import datetime, timedelta

import pytest

from app import models, snapshot

from conftest import make_hall, make_halls

# The snapshot is refreshed daily by CI. Athinorama publishes one cinema week
# (Thu-Wed), so a snapshot older than that contains nothing but past showtimes
# and is useless as a cold-start dataset. Failing here is the alarm for "the
# daily refresh job has stopped" - the thing that would quietly bring the
# eleven-cinema problem back.
MAX_SNAPSHOT_AGE_DAYS = 8


def test_committed_snapshot_exists_and_is_readable():
    data = snapshot.read()
    assert data is not None, (
        "backend/app/data/cinemas_snapshot.json.gz is missing - a cold start "
        "would have no data to serve"
    )
    assert len(data["halls"]) >= snapshot.MIN_HALLS


def test_committed_snapshot_holds_real_cinemas():
    """Guards against the fake sample data creeping back in."""
    halls = snapshot.read()["halls"]
    named = [h for h in halls if h.get("name")]
    assert len(named) == len(halls)

    located = [h for h in halls if h.get("lat") and h.get("lng")]
    assert len(located) > len(halls) * 0.8, "most cinemas need map coordinates"

    # Every hall must trace back to athinorama, not to the seed script.
    assert all("athinorama.gr" in (h.get("source_url") or "") for h in halls)

    fake = {"dune-part-three", "the-odyssey", "poor-things-2", "the-batman-2"}
    slugs = {s["movie_slug"] for h in halls for s in h["screenings"]}
    assert not (slugs & fake), "sample movies must never be in the snapshot"


def test_committed_snapshot_is_not_ancient():
    generated = datetime.fromisoformat(snapshot.read()["generated_at"])
    age = datetime.now() - generated
    assert age < timedelta(days=MAX_SNAPSHOT_AGE_DAYS), (
        f"snapshot is {age.days} days old - the daily refresh job has stopped"
    )


def test_committed_snapshot_still_has_showtimes_left():
    """A snapshot with nothing upcoming cannot bootstrap a cold start."""
    assert snapshot.info()["upcoming_screenings"] > 0


def test_a_fully_past_snapshot_is_not_loaded(db, tmp_path):
    """
    Dead showtimes must not be written to the database.

    They would be invisible to every query anyway, and writing them would make
    the data look present in row counts while the map stayed empty.
    """
    path = tmp_path / "old.json.gz"
    stale = datetime.now() - timedelta(days=10)
    snapshot.write(
        [make_hall(f"old-{i}", when=stale) for i in range(40)], path
    )

    assert snapshot.load_into(db, path) is None
    assert db.query(models.Screening).count() == 0
    assert db.query(models.Cinema).count() == 0


def test_a_partly_past_snapshot_is_still_loaded(db, tmp_path):
    """Mid-week snapshots keep the days that have not happened yet."""
    path = tmp_path / "mixed.json.gz"
    halls = [make_hall(f"old-{i}", when=datetime.now() - timedelta(days=2))
             for i in range(39)]
    halls.append(make_hall("future", when=datetime.now() + timedelta(hours=4)))
    snapshot.write(halls, path)

    result = snapshot.load_into(db, path)

    assert result["halls"] == 40
    assert result["upcoming"] == 1


def test_snapshot_round_trip_preserves_screening_times(tmp_path):
    when = datetime(2026, 9, 8, 20, 30)
    path = tmp_path / "snap.json.gz"
    halls = make_halls(snapshot.MIN_HALLS, "rt")
    halls[0] = make_hall("rt-0", when=when)

    snapshot.write(halls, path)
    read_back = snapshot.read(path)

    assert len(read_back["halls"]) == len(halls)
    first = next(h for h in read_back["halls"] if h["slug"] == "rt-0")
    assert first["screenings"][0]["start_time"] == when


def test_write_refuses_a_thin_snapshot(tmp_path):
    """A broken scrape must not overwrite the good cold-start dataset."""
    with pytest.raises(ValueError, match="refusing to write"):
        snapshot.write(make_halls(11, "thin"), tmp_path / "snap.json.gz")


def test_load_into_populates_an_empty_database(db, tmp_path):
    path = tmp_path / "snap.json.gz"
    snapshot.write(make_halls(40, "load"), path)

    result = snapshot.load_into(db, path)

    assert result["halls"] == 40
    assert db.query(models.Cinema).count() == 40
    assert db.query(models.Screening).count() == 40


def test_load_into_is_a_noop_without_a_snapshot(db, tmp_path):
    assert snapshot.load_into(db, tmp_path / "missing.json.gz") is None
    assert db.query(models.Cinema).count() == 0


def test_corrupt_snapshot_does_not_raise(db, tmp_path):
    """A damaged file must degrade to "no snapshot", never crash startup."""
    path = tmp_path / "snap.json.gz"
    path.write_bytes(b"this is not gzip")

    assert snapshot.read(path) is None
    assert snapshot.load_into(db, path) is None
    assert snapshot.info(path) == {"present": True, "readable": False}


def test_info_reports_freshness():
    info = snapshot.info()
    assert info["present"] and info["readable"]
    assert info["halls"] >= snapshot.MIN_HALLS
    assert "generated_at" in info
