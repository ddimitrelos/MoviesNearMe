"""
Scraper for athinorama.gr cinema listings.

Athinorama embeds clean schema.org JSON-LD on every hall page, which is far more
reliable than scraping HTML:

  - The cinema landing pages (/cinema/ and /cinema/guide/) link to individual
    halls at /cinema/halls/<slug>-<id>/.
  - Each hall page contains, in <script type="application/ld+json"> blocks:
      * one `MovieTheater`  -> name, address, geo (lat/lng), telephone
      * many `ScreeningEvent` -> startDate/endDate (ISO 8601 with tz) and a
        nested `Movie` (name = Greek title, alternateName = original title,
        url = movie page with slug).

So we parse the JSON-LD instead of guessing at markup or Greek day ranges.
Everything is best-effort: a malformed block is skipped, never fatal.
"""

from __future__ import annotations

import re
import json
import time
import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from .database import SessionLocal
from . import models

log = logging.getLogger("scraper")

BASE = "https://www.athinorama.gr"
# Hall links are discovered from these landing pages (there is no /halls/ index).
LANDING_PAGES = [f"{BASE}/cinema/", f"{BASE}/cinema/guide/"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}

# polite delay between hall requests (seconds)
REQUEST_DELAY = 0.7

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)
HALL_HREF_RE = re.compile(r"/cinema/halls/[^\"'?#\s]+")
MOVIE_SLUG_RE = re.compile(r"/cinema/movie/([^/?#]+)")
HALL_SLUG_RE = re.compile(r"/cinema/halls/([^/?#]+)")


# --- JSON-LD helpers --------------------------------------------------------

def _iter_ld_json(html: str):
    """Yield each parsed JSON-LD object embedded in the page."""
    for raw in LD_JSON_RE.findall(html):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # a block can be a single object or a list of them
        if isinstance(obj, list):
            yield from obj
        else:
            yield obj


def _first_of_type(objects: list[dict], type_name: str) -> Optional[dict]:
    for o in objects:
        if isinstance(o, dict) and o.get("@type") == type_name:
            return o
    return None


def _find_movie(event: dict) -> Optional[dict]:
    """Find the nested Movie object inside a ScreeningEvent."""
    for v in event.values():
        if isinstance(v, dict) and v.get("@type") == "Movie":
            return v
    # some pages use workPresented
    wp = event.get("workPresented")
    if isinstance(wp, dict):
        return wp
    return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "movie"


def parse_iso_local(value: str) -> Optional[datetime]:
    """
    "2026-07-23T20:00:00+03:00" -> naive local datetime (tz dropped).

    The site publishes Athens local times; the app and API also work in local
    wall-clock time, so we strip the offset rather than convert to UTC.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


# --- Field extraction -------------------------------------------------------

def _address_str(theater: dict) -> Optional[str]:
    addr = theater.get("address")
    if not isinstance(addr, dict):
        return None
    street = (addr.get("streetAddress") or "").strip()
    locality = (addr.get("addressLocality") or "").strip()
    parts = [p for p in (street, locality) if p and p.lower() != street.lower()]
    if street and locality and street.lower() != locality.lower():
        return f"{street}, {locality}"
    return street or locality or None


def _geo(theater: dict) -> tuple[Optional[float], Optional[float]]:
    geo = theater.get("geo")
    if not isinstance(geo, dict):
        return None, None
    try:
        return float(geo["latitude"]), float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


# --- Network ----------------------------------------------------------------

def fetch(client: httpx.Client, url: str) -> Optional[str]:
    try:
        r = client.get(url, timeout=25.0)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text
    except Exception as e:  # noqa: BLE001 - best-effort scraping
        log.warning("fetch failed %s: %s", url, e)
        return None


def discover_hall_urls(client: httpx.Client) -> list[str]:
    urls: set[str] = set()
    for page in LANDING_PAGES:
        html = fetch(client, page)
        if not html:
            continue
        for href in HALL_HREF_RE.findall(html):
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != "halls":
                urls.add(f"{BASE}/cinema/halls/{slug}/")
    return sorted(urls)


# --- Hall page parsing ------------------------------------------------------

def parse_hall(html: str, url: str) -> Optional[dict]:
    objects = list(_iter_ld_json(html))
    theater = _first_of_type(objects, "MovieTheater")
    if not theater:
        return None

    lat, lng = _geo(theater)
    slug_m = HALL_SLUG_RE.search(url)
    slug = slug_m.group(1) if slug_m else url.rstrip("/").split("/")[-1]

    screenings = []
    for ev in objects:
        if not isinstance(ev, dict) or ev.get("@type") != "ScreeningEvent":
            continue
        start = parse_iso_local(ev.get("startDate", ""))
        if start is None:
            continue
        movie = _find_movie(ev)
        if not movie:
            continue
        title = (movie.get("name") or ev.get("name") or "").strip()
        if not title:
            continue
        original = (movie.get("alternateName") or "").strip() or None
        murl = movie.get("url", "")
        mslug_m = MOVIE_SLUG_RE.search(murl)
        movie_slug = mslug_m.group(1) if mslug_m else _slugify(original or title)

        end = parse_iso_local(ev.get("endDate", ""))
        duration = None
        if end and end > start:
            duration = int((end - start).total_seconds() // 60)

        screenings.append(
            {
                "movie_slug": movie_slug,
                "movie_title": title,
                "movie_original": original,
                "movie_duration": duration,
                "hall": None,  # auditorium isn't published in the structured data
                "start_time": start,
            }
        )

    return {
        "slug": slug,
        "name": (theater.get("name") or "").strip(),
        "address": _address_str(theater),
        "phone": theater.get("telephone"),
        "lat": lat,
        "lng": lng,
        "source_url": url,
        "screenings": screenings,
    }


# --- Persistence ------------------------------------------------------------

def upsert_cinema(db: Session, data: dict) -> models.Cinema:
    cinema = db.query(models.Cinema).filter_by(slug=data["slug"]).one_or_none()
    if cinema is None:
        cinema = models.Cinema(slug=data["slug"])
        db.add(cinema)
    cinema.name = data["name"]
    cinema.address = data.get("address")
    cinema.phone = data.get("phone")
    if data.get("lat") is not None:
        cinema.lat = data["lat"]
    if data.get("lng") is not None:
        cinema.lng = data["lng"]
    cinema.source_url = data.get("source_url")
    db.flush()
    return cinema


def upsert_movie(db: Session, row: dict) -> models.Movie:
    movie = db.query(models.Movie).filter_by(slug=row["movie_slug"]).one_or_none()
    if movie is None:
        movie = models.Movie(slug=row["movie_slug"], title=row["movie_title"])
        db.add(movie)
    movie.title = row["movie_title"]
    if row.get("movie_original"):
        movie.original_title = row["movie_original"]
    if row.get("movie_duration"):
        movie.duration_min = row["movie_duration"]
    db.flush()
    return movie


def save_hall(db: Session, hall: dict) -> None:
    cinema = upsert_cinema(db, hall)
    for row in hall["screenings"]:
        movie = upsert_movie(db, row)
        exists = (
            db.query(models.Screening)
            .filter_by(
                cinema_id=cinema.id,
                movie_id=movie.id,
                start_time=row["start_time"],
                hall=row["hall"],
            )
            .first()
        )
        if exists:
            continue
        db.add(
            models.Screening(
                cinema_id=cinema.id,
                movie_id=movie.id,
                start_time=row["start_time"],
                hall=row["hall"],
            )
        )
    db.commit()


def run_scrape(limit: Optional[int] = None, wipe: bool = True) -> dict:
    """Scrape all halls into the database. Returns a small summary dict."""
    db = SessionLocal()
    summary = {"halls": 0, "screenings": 0, "errors": 0}
    try:
        if wipe:
            db.query(models.Screening).delete()
            db.query(models.Movie).delete()
            db.query(models.Cinema).delete()
            db.commit()

        with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
            urls = discover_hall_urls(client)
            log.info("discovered %d hall urls", len(urls))
            if limit:
                urls = urls[:limit]
            for url in urls:
                html = fetch(client, url)
                if not html:
                    summary["errors"] += 1
                    continue
                hall = parse_hall(html, url)
                if not hall or not hall["name"]:
                    summary["errors"] += 1
                    continue
                save_hall(db, hall)
                summary["halls"] += 1
                summary["screenings"] += len(hall["screenings"])
                time.sleep(REQUEST_DELAY)
    finally:
        db.close()
    log.info("scrape summary: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_scrape())
