"""
A committed snapshot of real athinorama listings, used as the cold-start
dataset.

Why this exists
---------------
Render's free tier has an ephemeral filesystem, so every restart or deploy
begins with an empty SQLite file. The old behaviour was to fill that gap with
`seed.py` - eleven invented cinemas and made-up movies - and then scrape in the
background. Whenever the scrape was slow or partial, users were left looking at
those eleven fake cinemas and had no way to tell they were fake.

A snapshot of the last known-good *real* scrape is strictly better: it is the
same data shape the scraper produces, it is honest, and it is refreshed daily in
CI so a cold start serves genuine listings for today rather than fiction.

The file stores the exact dicts `scraper.parse_hall` returns (datetimes as ISO
strings), so loading it reuses the scraper's own write path.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from . import models

log = logging.getLogger("snapshot")

SNAPSHOT_PATH = Path(__file__).parent / "data" / "cinemas_snapshot.json.gz"

# A snapshot below this many halls is treated as broken and never written or
# loaded - the same floor the scraper uses before it is allowed to replace data.
MIN_HALLS = 30

FORMAT_VERSION = 1


def _serialise(hall: dict) -> dict:
    out = dict(hall)
    out["screenings"] = [
        {**s, "start_time": s["start_time"].isoformat()}
        for s in hall.get("screenings", [])
    ]
    return out


def _deserialise(hall: dict) -> dict:
    out = dict(hall)
    rows = []
    for s in hall.get("screenings", []):
        s = dict(s)
        try:
            s["start_time"] = datetime.fromisoformat(s["start_time"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(s)
    out["screenings"] = rows
    return out


def write(halls: list, path: Optional[Path] = None,
          generated_at: Optional[datetime] = None) -> dict:
    """Write `halls` to the snapshot file. Refuses to write a thin snapshot."""
    path = Path(path or SNAPSHOT_PATH)
    if len(halls) < MIN_HALLS:
        raise ValueError(
            f"refusing to write a snapshot of only {len(halls)} halls "
            f"(minimum {MIN_HALLS}) - this would poison the cold-start dataset"
        )
    payload = {
        "version": FORMAT_VERSION,
        "generated_at": (generated_at or datetime.now()).isoformat(),
        "source": "athinorama.gr",
        "halls": [_serialise(h) for h in halls],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip bytes stable for identical data, so CI only commits
    # a new snapshot when the listings actually changed.
    with gzip.GzipFile(path, "wb", mtime=0) as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return {"halls": len(halls), "path": str(path),
            "generated_at": payload["generated_at"]}


def read(path: Optional[Path] = None) -> Optional[dict]:
    """Return {"generated_at", "halls": [...]} or None if unusable."""
    path = Path(path or SNAPSHOT_PATH)
    if not path.exists():
        return None
    try:
        with gzip.GzipFile(path, "rb") as fh:
            payload = json.loads(fh.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - a corrupt snapshot must not crash boot
        log.warning("could not read snapshot %s: %s", path, e)
        return None
    halls = [_deserialise(h) for h in payload.get("halls", [])]
    if not halls:
        return None
    return {"generated_at": payload.get("generated_at"), "halls": halls}


def info(path: Optional[Path] = None) -> dict:
    """Small summary for /health - never raises."""
    path = Path(path or SNAPSHOT_PATH)
    if not path.exists():
        return {"present": False}
    data = read(path)
    if not data:
        return {"present": True, "readable": False}
    upcoming = sum(
        1
        for h in data["halls"]
        for s in h["screenings"]
        if s["start_time"] >= datetime.now()
    )
    return {
        "present": True,
        "readable": True,
        "generated_at": data["generated_at"],
        "halls": len(data["halls"]),
        "upcoming_screenings": upcoming,
    }


def load_into(db: Session, path: Optional[Path] = None) -> Optional[dict]:
    """
    Load the snapshot into an empty database.

    Returns a summary, or None when there is no usable snapshot. Import is local
    to avoid a circular import at module load (scraper imports models too).
    """
    from . import scraper  # noqa: PLC0415 - circular import guard

    data = read(path)
    if not data:
        return None
    halls = data["halls"]
    if len(halls) < MIN_HALLS:
        log.warning("ignoring thin snapshot of %d halls", len(halls))
        return None

    # Showtimes perish. Athinorama publishes a whole cinema week (Thu-Wed), so a
    # snapshot is useful for days - but once every screening in it is in the
    # past it is dead weight, and writing it would only put rows in the
    # database that no query can return. Leave the database alone and let the
    # live scrape fill it instead.
    now = datetime.now()
    upcoming = sum(
        1 for h in halls for s in h["screenings"] if s["start_time"] >= now
    )
    if upcoming == 0:
        log.warning(
            "snapshot from %s has no upcoming screenings - skipping load; "
            "the first live scrape will populate the database",
            data["generated_at"],
        )
        return None

    written = scraper.publish(db, halls, replace=True)
    log.info(
        "loaded snapshot: %d cinemas, %d screenings (generated %s)",
        len(halls), written, data["generated_at"],
    )
    return {
        "halls": len(halls),
        "screenings": written,
        "upcoming": upcoming,
        "generated_at": data["generated_at"],
    }


def refresh(path: Optional[Path] = None) -> dict:
    """
    Scrape live and overwrite the snapshot file. Used by the daily CI job.

    Raises if the scrape came back too thin, so CI fails loudly instead of
    committing a snapshot that would make cold starts worse.
    """
    from . import scraper  # noqa: PLC0415 - circular import guard

    halls, discovered, errors = scraper.scrape_halls()
    log.info("snapshot refresh: %d/%d halls, %d errors",
             len(halls), discovered, errors)
    result = write(halls, path)
    result["discovered"] = discovered
    result["errors"] = errors
    return result


def _count_upcoming(db: Session) -> int:
    return (
        db.query(models.Screening)
        .filter(models.Screening.start_time >= datetime.now())
        .count()
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(refresh())
