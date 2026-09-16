"""
MovieNearMe API.

Endpoints the Android app uses:
  GET /health
  GET /movies                       -> list movies (optional ?query= search)
  GET /cinemas                      -> cinemas, each with the screenings that
                                       match the given filters
      query params:
        movie_id   : only screenings of this movie
        from_time  : ISO datetime, only screenings at/after this (default: now)
        to_time    : ISO datetime, only screenings before this
        within_hours : convenience, overrides to_time = now + N hours
        lat,lng    : if given, results are sorted by distance and each cinema
                     gets a distance_km field
  GET /cinemas/{id}/screenings      -> full screening list for one cinema
  POST /admin/scrape                -> trigger a live scrape (background or ?sync)
  POST /admin/seed                  -> sample data, local development only

Data availability
-----------------
The service must never serve invented listings. On a cold start (Render's free
tier loses the SQLite file on every restart) the database is filled from the
committed snapshot of the last real scrape, then a live scrape refreshes it.
A supervisor thread re-scrapes whenever the data is thin, stale, or overdue,
and /health reports exactly which of those is true.
"""

from __future__ import annotations

import math
import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, Query, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .database import Base, engine, get_db, SessionLocal, DB_PATH, DB_IS_PERSISTENT
from . import models, schemas, scraper, snapshot, seed as seed_module

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

# --- Data freshness policy ---------------------------------------------------
# How often the supervisor wakes up to check the data.
CHECK_INTERVAL_SECONDS = 300
# A dataset older than this is refreshed even if it still looks healthy.
REFRESH_AFTER_HOURS = 6
# Fewer cinemas than this showing anything upcoming means something is wrong;
# refresh immediately instead of waiting for the next daily window. The old
# 24h sleep is why a bad scrape could leave production broken for a full day.
MIN_HEALTHY_CINEMAS = 30
# Wait between retries after consecutive failures (seconds), last value repeats.
FAILURE_BACKOFF = (300, 900, 1800, 3600)

# Only one scrape at a time: the supervisor and /admin/scrape share this.
_scrape_lock = threading.Lock()

app = FastAPI(title="MovieNearMe API", version="1.1.0")

# The Android emulator reaches the host at 10.0.2.2; allow everything in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Data-state helpers ------------------------------------------------------

def _data_state(db: Session, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    upcoming = db.query(models.Screening).filter(models.Screening.start_time >= now)
    return {
        "cinemas": db.query(func.count(models.Cinema.id)).scalar() or 0,
        "movies": db.query(func.count(models.Movie.id)).scalar() or 0,
        "screenings": db.query(func.count(models.Screening.id)).scalar() or 0,
        "upcoming_screenings": upcoming.count(),
        "cinemas_with_upcoming": upcoming.with_entities(
            models.Screening.cinema_id
        ).distinct().count(),
    }


def needs_scrape(state: dict, last: dict, now: Optional[datetime] = None) -> tuple:
    """
    Should we scrape right now? Returns (bool, reason).

    Pure function of the data state and the last run, so the policy is testable
    without a network or a clock.
    """
    now = now or datetime.now()
    if state["cinemas_with_upcoming"] < MIN_HEALTHY_CINEMAS:
        return True, "only %d cinemas have upcoming screenings" % (
            state["cinemas_with_upcoming"],
        )
    finished = last.get("finished_at")
    if not last.get("ok") or not finished:
        return True, "no successful scrape yet"
    try:
        age = now - datetime.fromisoformat(finished)
    except (TypeError, ValueError):
        return True, "unknown last-scrape time"
    if age >= timedelta(hours=REFRESH_AFTER_HOURS):
        return True, "last scrape was %.1f h ago" % (age.total_seconds() / 3600.0)
    return False, "data is fresh"


def _backoff_seconds(consecutive_failures: int) -> int:
    if consecutive_failures <= 0:
        return 0
    idx = min(consecutive_failures, len(FAILURE_BACKOFF)) - 1
    return FAILURE_BACKOFF[idx]


def scrape_now(wipe: bool = True) -> dict:
    """Run a scrape unless one is already running."""
    if not _scrape_lock.acquire(blocking=False):
        return {"skipped": "a scrape is already running"}
    try:
        return scraper.run_scrape(wipe=wipe)
    finally:
        _scrape_lock.release()


def _scrape_supervisor() -> None:
    """
    Keep the dataset current, and self-heal when it is not.

    Replaces the old `sleep(24h)` loop, which meant a failed scrape left stale
    or bootstrap data in place until the next day.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                state = _data_state(db)
            finally:
                db.close()
            last = scraper.last_run()
            due, reason = needs_scrape(state, last)
            if due:
                wait = _backoff_seconds(last.get("consecutive_failures", 0))
                finished = last.get("finished_at")
                if wait and finished:
                    try:
                        since = (
                            datetime.now() - datetime.fromisoformat(finished)
                        ).total_seconds()
                    except (TypeError, ValueError):
                        since = wait
                    if since < wait:
                        time.sleep(CHECK_INTERVAL_SECONDS)
                        continue
                log.info("scrape due: %s", reason)
                scrape_now()
        except Exception as e:  # noqa: BLE001 - the supervisor must never die
            log.warning("supervisor iteration failed: %s", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


@app.on_event("startup")
def bootstrap_data() -> None:
    """
    Make sure the API is serving real listings from the very first request.

    On an empty or unusable database (a fresh cloud instance, or one whose data
    is entirely in the past) load the committed snapshot of the last real
    scrape. Never load the invented sample data here - showing eleven fake
    cinemas is worse than showing none, because it looks like it worked.
    """
    db = SessionLocal()
    try:
        state = _data_state(db)
        if state["cinemas_with_upcoming"] < MIN_HEALTHY_CINEMAS:
            log.info(
                "bootstrap: only %d cinemas with upcoming screenings - "
                "loading snapshot", state["cinemas_with_upcoming"],
            )
            try:
                loaded = snapshot.load_into(db)
                if not loaded:
                    log.warning(
                        "no usable snapshot; the API will be empty until the "
                        "first scrape finishes"
                    )
            except Exception as e:  # noqa: BLE001 - never block startup
                log.warning("snapshot load failed: %s", e)
    finally:
        db.close()

    if not DB_IS_PERSISTENT:
        log.info(
            "database at %s is not on a persistent disk - every restart "
            "rebuilds it from the snapshot plus a fresh scrape", DB_PATH,
        )

    # The supervisor scrapes immediately (no successful run recorded yet) and
    # then keeps the data fresh.
    threading.Thread(target=_scrape_supervisor, daemon=True).start()


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """
    Health plus a full data-quality report.

    The counts alone hid the original bug: the service answered "ok" while
    serving eleven fake cinemas. `status` is now "degraded" whenever the map
    would look empty, and the last-scrape block says why.
    """
    state = _data_state(db)
    last = scraper.last_run()
    degraded = state["cinemas_with_upcoming"] < MIN_HEALTHY_CINEMAS
    return {
        "status": "degraded" if degraded else "ok",
        # legacy keys kept for the keep-alive ping and older clients
        "cinemas": state["cinemas"],
        "movies": state["movies"],
        "screenings": state["screenings"],
        "upcoming_screenings": state["upcoming_screenings"],
        "cinemas_with_upcoming": state["cinemas_with_upcoming"],
        "min_healthy_cinemas": MIN_HEALTHY_CINEMAS,
        "last_scrape": last,
        "snapshot": snapshot.info(),
        "db": {"path": DB_PATH, "persistent": DB_IS_PERSISTENT},
    }


@app.get("/movies", response_model=list[schemas.MovieOut])
def list_movies(
    query: Optional[str] = None,
    only_showing: bool = Query(
        True, description="Only movies with an upcoming screening"
    ),
    db: Session = Depends(get_db),
):
    q = db.query(models.Movie)
    if query:
        like = f"%{query.lower()}%"
        q = q.filter(
            func.lower(models.Movie.title).like(like)
            | func.lower(func.coalesce(models.Movie.original_title, "")).like(like)
        )
    if only_showing:
        now = datetime.now()
        sub = (
            db.query(models.Screening.movie_id)
            .filter(models.Screening.start_time >= now)
            .distinct()
        )
        q = q.filter(models.Movie.id.in_(sub))
    return q.order_by(models.Movie.title).all()


@app.get("/cinemas")
def list_cinemas(
    movie_id: Optional[int] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    within_hours: Optional[float] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    summer_only: bool = False,
    max_km: Optional[float] = None,
    db: Session = Depends(get_db),
):
    now = datetime.now()
    start = from_time or now
    end = to_time
    if within_hours is not None:
        end = start + timedelta(hours=within_hours)

    scr_q = db.query(models.Screening).options(
        joinedload(models.Screening.movie)
    ).filter(models.Screening.start_time >= start)
    if end is not None:
        scr_q = scr_q.filter(models.Screening.start_time <= end)
    if movie_id is not None:
        scr_q = scr_q.filter(models.Screening.movie_id == movie_id)

    screenings = scr_q.order_by(models.Screening.start_time).all()

    # group screenings by cinema
    by_cinema: dict[int, list[models.Screening]] = {}
    for s in screenings:
        by_cinema.setdefault(s.cinema_id, []).append(s)

    cinema_q = db.query(models.Cinema).filter(
        models.Cinema.id.in_(by_cinema.keys())
    )
    if summer_only:
        cinema_q = cinema_q.filter(models.Cinema.is_summer.is_(True))
    cinemas = cinema_q.all() if by_cinema else []

    result = []
    for c in cinemas:
        item = {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "address": c.address,
            "phone": c.phone,
            "lat": c.lat,
            "lng": c.lng,
            "region": c.region,
            "is_summer": bool(c.is_summer),
            "screenings": [
                {
                    "id": s.id,
                    "start_time": s.start_time.isoformat(),
                    "hall": s.hall,
                    "movie": schemas.MovieOut.model_validate(s.movie).model_dump(),
                }
                for s in by_cinema[c.id]
            ],
        }
        if lat is not None and lng is not None and c.lat and c.lng:
            item["distance_km"] = round(haversine_km(lat, lng, c.lat, c.lng), 2)
        result.append(item)

    # "Near me": keep only cinemas within max_km of the user (needs a location
    # and a known cinema position).
    if max_km is not None and lat is not None and lng is not None:
        result = [
            x for x in result
            if x.get("distance_km") is not None and x["distance_km"] <= max_km
        ]

    if lat is not None and lng is not None:
        result.sort(key=lambda x: x.get("distance_km", 1e9))

    return result


@app.get("/cinemas/{cinema_id}/screenings", response_model=list[schemas.ScreeningOut])
def cinema_screenings(
    cinema_id: int,
    upcoming_only: bool = True,
    db: Session = Depends(get_db),
):
    c = db.get(models.Cinema, cinema_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cinema not found")
    q = db.query(models.Screening).options(
        joinedload(models.Screening.movie),
        joinedload(models.Screening.cinema),
    ).filter(models.Screening.cinema_id == cinema_id)
    if upcoming_only:
        q = q.filter(models.Screening.start_time >= datetime.now())
    return q.order_by(models.Screening.start_time).all()


@app.post("/admin/scrape")
def trigger_scrape(
    background: BackgroundTasks,
    limit: Optional[int] = None,
    sync: bool = False,
):
    if sync:
        return scraper.run_scrape(limit)
    background.add_task(scraper.run_scrape, limit)
    return {"status": "scrape started", "limit": limit}


@app.post("/admin/seed")
def trigger_seed():
    """
    Load the invented sample dataset.

    Disabled unless ALLOW_SEED=1. This data must never reach production: eleven
    fake cinemas served as if real is the exact failure this codebase had.
    """
    if os.getenv("ALLOW_SEED") != "1":
        raise HTTPException(
            status_code=403,
            detail="seeding is disabled; set ALLOW_SEED=1 for local development",
        )
    seed_module.seed()
    return {"status": "seeded"}
