"""
Scraper for athinorama.gr cinema hall pages.

Athinorama structure (as of 2026):
  - Halls index:  https://www.athinorama.gr/cinema/halls/
      -> links to individual halls: /cinema/halls/<slug>-<id>/
  - Hall page contains: name (h1), address, phone, a Google Maps link that
    embeds the lat/lng, and a per-auditorium schedule block with Greek day
    ranges (e.g. "Πέμ.-Τετ.: 20.00, 22.15").

The site's markup changes from time to time, so every extractor here is
best-effort and defensive: if a field can't be found it is left empty rather
than crashing the whole run. Parsing helpers are pure functions so they can be
unit-tested against saved HTML fixtures.
"""

from __future__ import annotations

import re
import time
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Iterable

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .database import SessionLocal
from . import models

log = logging.getLogger("scraper")

BASE = "https://www.athinorama.gr"
HALLS_INDEX = f"{BASE}/cinema/halls/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}

# polite delay between hall requests (seconds)
REQUEST_DELAY = 1.0

# --- Greek day parsing -----------------------------------------------------

# canonical order: Monday=0 ... Sunday=6 (matches datetime.weekday())
GREEK_DAYS = {
    "δευ": 0,
    "τρι": 1,
    "τετ": 2,
    "πεμ": 3,
    "παρ": 4,
    "σαβ": 5,
    "κυρ": 6,
}


def _strip_accents(text: str) -> str:
    trans = str.maketrans("άέήίόύώϊϋΐΰ", "αεηιουωιυιυ")
    return text.translate(trans)


def _day_index(token: str) -> Optional[int]:
    key = _strip_accents(token.strip().lower())[:3]
    return GREEK_DAYS.get(key)


def parse_day_range(text: str) -> list[int]:
    """
    "Πέμ.-Τετ." -> [3,4,5,6,0,1,2]   (wraps around the week)
    "Παρ."      -> [4]
    "Σαβ., Κυρ."-> [5, 6]
    Returns weekday indices (Mon=0..Sun=6).

    Accents are stripped up front so accented day names (Πέμ, Τετ, ...) match.
    """
    normalized = _strip_accents(text.replace(".", " ").lower())
    # range form: A - B
    m = re.search(r"([α-ω]{2,})\s*-\s*([α-ω]{2,})", normalized)
    if m:
        a = GREEK_DAYS.get(m.group(1)[:3])
        b = GREEK_DAYS.get(m.group(2)[:3])
        if a is not None and b is not None:
            days = []
            i = a
            while True:
                days.append(i)
                if i == b:
                    break
                i = (i + 1) % 7
                if len(days) > 7:
                    break
            return days
    # list form: A, B, C
    days = []
    for tok in re.split(r"[,\s]+", normalized):
        idx = GREEK_DAYS.get(tok[:3]) if tok else None
        if idx is not None and idx not in days:
            days.append(idx)
    return days


TIME_RE = re.compile(r"\b([0-2]?\d)[.:]([0-5]\d)\b")


def parse_times(text: str) -> list[tuple[int, int]]:
    out = []
    for m in TIME_RE.finditer(text):
        h, mm = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23:
            out.append((h, mm))
    return out


def next_date_for_weekday(weekday: int, ref: Optional[date] = None) -> date:
    """The next calendar date (today or later, within 7 days) for a weekday."""
    ref = ref or date.today()
    delta = (weekday - ref.weekday()) % 7
    return ref + timedelta(days=delta)


# --- Coordinate / field extraction -----------------------------------------

COORD_RE = re.compile(r"(-?\d{1,2}\.\d{3,})[,\s]+(-?\d{1,3}\.\d{3,})")


def extract_coords(html: str) -> tuple[Optional[float], Optional[float]]:
    """
    Pull lat,lng out of any embedded Google Maps URL or data attribute.
    Athens lies roughly at lat 37-38, lng 23-24, so we sanity-check the pair.
    """
    for m in COORD_RE.finditer(html):
        try:
            lat, lng = float(m.group(1)), float(m.group(2))
        except ValueError:
            continue
        if 34.0 <= lat <= 42.0 and 19.0 <= lng <= 28.0:
            return lat, lng
    return None, None


def _slug_from_href(href: str) -> Optional[str]:
    m = re.search(r"/cinema/halls/([^/?#]+)", href)
    return m.group(1) if m else None


# --- Network ----------------------------------------------------------------

def fetch(client: httpx.Client, url: str) -> Optional[str]:
    try:
        r = client.get(url, timeout=20.0)
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001 - best-effort scraping
        log.warning("fetch failed %s: %s", url, e)
        return None


def discover_hall_urls(client: httpx.Client) -> list[str]:
    html = fetch(client, HALLS_INDEX)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    urls: set[str] = set()
    for a in soup.select('a[href*="/cinema/halls/"]'):
        href = a.get("href", "")
        slug = _slug_from_href(href)
        if not slug:
            continue
        full = href if href.startswith("http") else BASE + href
        urls.add(full.split("?")[0])
    return sorted(urls)


# --- Hall page parsing ------------------------------------------------------

def parse_hall(html: str, url: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")

    name_el = soup.select_one("h1")
    name = name_el.get_text(strip=True) if name_el else None
    if not name:
        return None

    lat, lng = extract_coords(html)

    # Address / phone are usually near the top of the page. We look for a
    # phone pattern and grab a nearby address-looking line as a heuristic.
    text = soup.get_text("\n", strip=True)
    phone = None
    pm = re.search(r"\b(2\d{9})\b", text)
    if pm:
        phone = pm.group(1)

    address = None
    addr_el = soup.find(class_=re.compile(r"address", re.I))
    if addr_el:
        address = addr_el.get_text(" ", strip=True)

    slug = _slug_from_href(url) or url.rstrip("/").split("/")[-1]

    screenings = parse_schedule(soup)

    return {
        "slug": slug,
        "name": name,
        "address": address,
        "phone": phone,
        "lat": lat,
        "lng": lng,
        "source_url": url,
        "screenings": screenings,
    }


def parse_schedule(soup: BeautifulSoup) -> list[dict]:
    """
    Extract (movie_title, hall, day_range_text, times) rows.

    Athinorama renders each film with an auditorium + day-range + times line.
    We look for anchors to /cinema/movie/ (the film) and, for the surrounding
    block, pull the day range and time tokens.
    """
    rows: list[dict] = []
    for a in soup.select('a[href*="/cinema/movie/"]'):
        title = a.get_text(strip=True)
        if not title:
            continue
        movie_slug = None
        m = re.search(r"/cinema/movie/([^/?#]+)", a.get("href", ""))
        if m:
            movie_slug = m.group(1)

        block = a.find_parent(["li", "tr", "div"])
        block_text = block.get_text(" ", strip=True) if block else ""

        hall_m = re.search(r"Αίθουσα\s*([\wΑ-Ω\d]+)", block_text)
        hall = hall_m.group(1) if hall_m else None

        days = parse_day_range(block_text)
        times = parse_times(block_text)
        if not times:
            continue
        if not days:
            days = [date.today().weekday()]

        for wd in days:
            d = next_date_for_weekday(wd)
            for (h, mm) in times:
                rows.append(
                    {
                        "movie_title": title,
                        "movie_slug": movie_slug or _slugify(title),
                        "hall": hall,
                        "start_time": datetime(d.year, d.month, d.day, h, mm),
                    }
                )
    return rows


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "movie"


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


def upsert_movie(db: Session, slug: str, title: str) -> models.Movie:
    movie = db.query(models.Movie).filter_by(slug=slug).one_or_none()
    if movie is None:
        movie = models.Movie(slug=slug, title=title)
        db.add(movie)
        db.flush()
    return movie


def save_hall(db: Session, hall: dict) -> None:
    cinema = upsert_cinema(db, hall)
    for row in hall["screenings"]:
        movie = upsert_movie(db, row["movie_slug"], row["movie_title"])
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


def run_scrape(limit: Optional[int] = None) -> dict:
    """Scrape all halls. Returns a small summary dict."""
    db = SessionLocal()
    summary = {"halls": 0, "screenings": 0, "errors": 0}
    try:
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
                if not hall:
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
