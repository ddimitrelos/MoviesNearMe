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
  POST /admin/scrape                -> trigger a live scrape (background)
  POST /admin/seed                  -> load sample data
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, Query, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import time
import threading

from .database import Base, engine, get_db, SessionLocal
from . import models, schemas, scraper, seed as seed_module

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MovieNearMe API", version="1.0.0")

# The Android emulator reaches the host at 10.0.2.2; allow everything in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _daily_scrape_loop() -> None:
    """Re-scrape Athinorama every 24 h so listings never go stale."""
    while True:
        time.sleep(24 * 60 * 60)
        try:
            log.info("daily scrape starting")
            scraper.run_scrape(wipe=True)
        except Exception as e:  # noqa: BLE001
            log.warning("daily scrape failed: %s", e)


@app.on_event("startup")
def bootstrap_data() -> None:
    """
    On a fresh (empty) database — e.g. a cloud instance with an ephemeral disk —
    load the seed data instantly so the API is never empty, then scrape the real
    Athinorama listings in a background thread so startup isn't blocked.

    A daily re-scrape loop is always started so listings stay current even when
    the DB already had data (i.e. the service restarted without a wipe).
    """
    db = SessionLocal()
    try:
        count = db.query(func.count(models.Cinema.id)).scalar() or 0
    finally:
        db.close()
    if count == 0:
        log.info("empty database - loading seed data")
        try:
            seed_module.seed()
        except Exception as e:  # noqa: BLE001
            log.warning("seed failed: %s", e)

    # Always scrape on startup so data is fresh after a restart/redeploy
    # (Render's free tier has an ephemeral disk — the SQLite file is gone after
    # every deploy, so seed data would otherwise linger until the daily loop fires).
    threading.Thread(
        target=scraper.run_scrape, kwargs={"wipe": True}, daemon=True
    ).start()

    threading.Thread(target=_daily_scrape_loop, daemon=True).start()


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "cinemas": db.query(func.count(models.Cinema.id)).scalar(),
        "movies": db.query(func.count(models.Movie.id)).scalar(),
        "screenings": db.query(func.count(models.Screening.id)).scalar(),
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
def trigger_scrape(background: BackgroundTasks, limit: Optional[int] = None):
    background.add_task(scraper.run_scrape, limit)
    return {"status": "scrape started", "limit": limit}


@app.post("/admin/seed")
def trigger_seed():
    seed_module.seed()
    return {"status": "seeded"}
