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
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
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

# Hall pages are fetched concurrently. A sequential run with a long politeness
# delay took ~2 minutes, and for that whole time the API kept serving whatever
# was in the database before it. A small worker pool plus a per-request delay
# keeps load on athinorama modest while cutting a full refresh to well under a
# minute, which is what keeps the "stale data" window short.
MAX_WORKERS = 6
# polite delay each worker waits after a hall request (seconds)
REQUEST_DELAY = 0.3

# --- Safety rails for replacing the live dataset -----------------------------
# A scrape may only wipe-and-replace the database when the run looks complete.
# A partial run must degrade to a merge, never a shrink.
MIN_HALLS_FOR_REPLACE = 30          # absolute floor
REPLACE_RATIO_DISCOVERED = 0.6      # vs. hall URLs found on the landing pages
REPLACE_RATIO_EXISTING = 0.7        # vs. cinemas already in the database

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)
HALL_HREF_RE = re.compile(r"/cinema/halls/[^\"'?#\s]+")
MOVIE_SLUG_RE = re.compile(r"/cinema/movie/([^/?#]+)")
HALL_SLUG_RE = re.compile(r"/cinema/halls/([^/?#]+)")

TIME_RE = re.compile(r"\b([0-2]?\d)[.:]([0-5]\d)\b")

# Auditorium ("Αίθουσα") and screening times live only in the visible HTML,
# not the JSON-LD. We parse them and match back to each structured screening by
# movie + weekday + time. Greek weekday tokens, Monday=0..Sunday=6.
GREEK_DAYS = {
    "δευ": 0, "τρι": 1, "τετ": 2, "πεμ": 3, "παρ": 4, "σαβ": 5, "κυρ": 6,
}


def _strip_accents(text: str) -> str:
    return text.translate(str.maketrans("άέήίόύώϊϋΐΰ", "αεηιουωιυιυ"))


def parse_day_range(text: str) -> set[int]:
    """'Πέμ.-Τετ.' -> {3,4,5,6,0,1,2}; 'Σαβ., Κυρ.' -> {5,6}."""
    norm = _strip_accents(text.replace(".", " ").lower())
    days: set[int] = set()
    m = re.search(r"([α-ω]{2,})\s*-\s*([α-ω]{2,})", norm)
    if m:
        a, b = GREEK_DAYS.get(m.group(1)[:3]), GREEK_DAYS.get(m.group(2)[:3])
        if a is not None and b is not None:
            i = a
            for _ in range(7):
                days.add(i)
                if i == b:
                    return days
                i = (i + 1) % 7
    for tok in re.split(r"[,\s]+", norm):
        idx = GREEK_DAYS.get(tok[:3]) if tok else None
        if idx is not None:
            days.add(idx)
    return days


def parse_times(text: str) -> set[tuple[int, int]]:
    out = set()
    for m in TIME_RE.finditer(text):
        h, mm = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23:
            out.add((h, mm))
    return out


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

def fetch(client: httpx.Client, url: str, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            r = client.get(url, timeout=25.0)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except Exception as e:  # noqa: BLE001 - best-effort scraping
            if attempt + 1 < retries:
                time.sleep(1.0 + attempt)  # brief backoff for transient DNS/net
                continue
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

def parse_room_index(soup: BeautifulSoup) -> dict[str, dict]:
    """
    Build {movie_slug: {"genre": str|None, "rows": [(room, days, times)]}}
    from the visible schedule so screenings can be tagged with an auditorium.
    """
    index: dict[str, dict] = {}
    # A movie can appear in several blocks on the same page (its program entry
    # plus sidebar promos). Merge them: accumulate schedule rows, keep the first
    # genre found — never let an empty sidebar block clobber a real one.
    for item in soup.select(".item-description"):
        a = item.select_one('h3 a[href*="/cinema/movie/"]')
        if not a:
            continue
        m = MOVIE_SLUG_RE.search(a.get("href", ""))
        if not m:
            continue
        slug = m.group(1)
        entry = index.setdefault(slug, {"genre": None, "rows": []})

        if entry["genre"] is None:
            tag = item.select_one(".tags li span")
            if tag:
                entry["genre"] = tag.get_text(strip=True) or None

        for p in item.select("p.schedule-box"):
            strong = p.select_one(".room-box")
            room_txt = strong.get_text(" ", strip=True) if strong else ""
            rm = re.search(r"Αίθουσα\s*\S+", room_txt)
            room = rm.group(0).strip() if rm else (room_txt or None)
            if room and "Θερινός" in room_txt and "Θερινός" not in room:
                room += " – Θερινός"
            text = p.get_text(" ", strip=True)
            days = parse_day_range(text)
            times = parse_times(text)
            if times:
                entry["rows"].append((room, days, times))
    return index


def _match_room(info: Optional[dict], start: datetime) -> Optional[str]:
    if not info or not info["rows"]:
        return None
    # If the movie only ever shows in one auditorium here, use it for every
    # screening (covers the common single-room case regardless of how the
    # day/time text is worded).
    rooms = {r for r, _, _ in info["rows"] if r}
    if len(rooms) == 1:
        return next(iter(rooms))
    # Otherwise disambiguate by weekday + time.
    wd, hm = start.weekday(), (start.hour, start.minute)
    for room, days, times in info["rows"]:
        if hm in times and (not days or wd in days):
            return room
    return None


def parse_hall(html: str, url: str) -> Optional[dict]:
    objects = list(_iter_ld_json(html))
    theater = _first_of_type(objects, "MovieTheater")
    if not theater:
        return None

    lat, lng = _geo(theater)
    slug_m = HALL_SLUG_RE.search(url)
    slug = slug_m.group(1) if slug_m else url.rstrip("/").split("/")[-1]

    room_index = parse_room_index(BeautifulSoup(html, "lxml"))

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

        info = room_index.get(movie_slug)
        screenings.append(
            {
                "movie_slug": movie_slug,
                "movie_title": title,
                "movie_original": original,
                "movie_duration": duration,
                "movie_genre": info["genre"] if info else None,
                "movie_poster": (ev.get("image") or "").strip() or None,
                "movie_url": (movie.get("url") or "").strip() or None,
                "hall": _match_room(info, start),
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
        # athinorama renders a "summerRoom.png" icon next to open-air screens;
        # its presence means this venue offers open-air (θερινό) screenings.
        "is_summer": "summerRoom.png" in html,
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
    cinema.is_summer = bool(data.get("is_summer"))
    cinema.source_url = data.get("source_url")
    db.flush()
    return cinema


def upsert_movie(db: Session, row: dict, cache: Optional[dict] = None) -> models.Movie:
    slug = row["movie_slug"]
    movie = cache.get(slug) if cache is not None else None
    if movie is None:
        movie = db.query(models.Movie).filter_by(slug=slug).one_or_none()
    if movie is None:
        movie = models.Movie(slug=slug, title=row["movie_title"])
        db.add(movie)
    movie.title = row["movie_title"]
    if row.get("movie_original"):
        movie.original_title = row["movie_original"]
    if row.get("movie_duration"):
        movie.duration_min = row["movie_duration"]
    if row.get("movie_genre"):
        movie.genre = row["movie_genre"]
    if row.get("movie_poster"):
        movie.poster_url = row["movie_poster"]
    if row.get("movie_url"):
        movie.source_url = row["movie_url"]
    db.flush()
    if cache is not None:
        cache[slug] = movie
    return movie


def save_hall(db: Session, hall: dict, cache: Optional[dict] = None,
              *, table_is_empty: bool = False, commit: bool = True) -> int:
    """Write one hall and its screenings. Returns the rows inserted."""
    cinema = upsert_cinema(db, hall)
    written = 0
    seen: set = set()
    for row in hall["screenings"]:
        movie = upsert_movie(db, row, cache)
        key = (cinema.id, movie.id, row["start_time"], row["hall"])
        if key in seen:
            continue
        seen.add(key)
        if not table_is_empty:
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
        written += 1
    if commit:
        db.commit()
    return written


def prune_past_screenings(db: Session, before: Optional[datetime] = None) -> int:
    """
    Drop screenings that already happened.

    Only the replace path clears the table wholesale, so without this the merge
    path used by partial runs accumulates dead showtimes forever.
    """
    cutoff = before or datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    deleted = (
        db.query(models.Screening)
        .filter(models.Screening.start_time < cutoff)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def replace_decision(parsed: int, discovered: int, existing: int) -> tuple:
    """
    Decide whether a scrape result is allowed to replace the whole dataset.

    Returns (may_replace, reason). A refusal is not an error - the caller merges
    the partial result instead, so the API keeps serving a full listing.
    """
    if parsed <= 0:
        return False, "no halls parsed"
    if parsed < MIN_HALLS_FOR_REPLACE:
        return False, "only %d halls, floor is %d" % (parsed, MIN_HALLS_FOR_REPLACE)
    if discovered and parsed < discovered * REPLACE_RATIO_DISCOVERED:
        return False, "partial run (%d/%d halls)" % (parsed, discovered)
    if existing and parsed < existing * REPLACE_RATIO_EXISTING:
        return False, "would shrink dataset (%d halls vs %d cinemas)" % (
            parsed, existing,
        )
    return True, "complete run"


def publish(db: Session, halls: list, *, replace: bool) -> int:
    """
    Write `halls` in a single transaction.

    Nothing is committed until every hall is written, so readers see either the
    old dataset or the new one - never a half-populated database.
    """
    if replace:
        db.query(models.Screening).delete(synchronize_session=False)
        db.query(models.Movie).delete(synchronize_session=False)
        db.query(models.Cinema).delete(synchronize_session=False)
        db.flush()
    cache: dict = {}
    written = 0
    for hall in halls:
        written += save_hall(db, hall, cache, table_is_empty=replace, commit=False)
    if not replace:
        prune_past_screenings(db)
    db.commit()
    return written


# --- Scraping ---------------------------------------------------------------

def _fetch_and_parse(client: httpx.Client, url: str) -> Optional[dict]:
    html = fetch(client, url)
    if not html:
        return None
    hall = parse_hall(html, url)
    time.sleep(REQUEST_DELAY)
    if not hall or not hall["name"]:
        return None
    return hall


def scrape_halls(limit: Optional[int] = None) -> tuple:
    """Fetch and parse every hall concurrently -> (halls, discovered, errors)."""
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        urls = discover_hall_urls(client)
        log.info("discovered %d hall urls", len(urls))
        discovered = len(urls)
        if limit:
            urls = urls[:limit]
        if not urls:
            return [], discovered, 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = list(pool.map(lambda u: _fetch_and_parse(client, u), urls))
    halls = [h for h in results if h]
    # When a limit is set, judge completeness against the limited set.
    expected = len(urls) if limit else discovered
    return halls, expected, len(results) - len(halls)


# --- Run status (surfaced on /health) ---------------------------------------

_status_lock = threading.Lock()
LAST_RUN: dict = {
    "started_at": None,
    "finished_at": None,
    "ok": None,
    "halls": 0,
    "discovered": 0,
    "screenings": 0,
    "errors": 0,
    "replaced": None,
    "reason": None,
    "consecutive_failures": 0,
}


def last_run() -> dict:
    with _status_lock:
        return dict(LAST_RUN)


def _record(**fields) -> None:
    with _status_lock:
        LAST_RUN.update(fields)


def run_scrape(limit: Optional[int] = None, wipe: bool = True) -> dict:
    """
    Scrape all halls into the database. Returns a small summary dict.

    Halls are parsed into memory first and written in a single transaction. The
    destructive replace only runs when `replace_decision` says the result looks
    complete, so a flaky network can never shrink or empty production.
    """
    started = datetime.now()
    _record(started_at=started.isoformat(), ok=None, reason="running")
    summary = {
        "halls": 0, "screenings": 0, "errors": 0,
        "discovered": 0, "replaced": False, "reason": "",
    }
    try:
        halls, discovered, errors = scrape_halls(limit)
    except Exception as e:  # noqa: BLE001 - scraping is best-effort
        log.warning("scrape failed: %s", e)
        with _status_lock:
            fails = LAST_RUN.get("consecutive_failures", 0) + 1
        _record(
            finished_at=datetime.now().isoformat(), ok=False,
            reason="scrape error: %s" % e, consecutive_failures=fails,
        )
        summary["reason"] = "scrape error: %s" % e
        return summary

    summary["halls"] = len(halls)
    summary["discovered"] = discovered
    summary["errors"] = errors

    db = SessionLocal()
    try:
        existing = db.query(models.Cinema).count()
        may_replace, reason = replace_decision(len(halls), discovered, existing)
        replace = bool(wipe and may_replace)
        if wipe and not may_replace:
            log.warning("not replacing dataset - %s; merging instead", reason)
        summary["screenings"] = publish(db, halls, replace=replace)
        summary["replaced"] = replace
        summary["reason"] = reason
    finally:
        db.close()

    ok = summary["halls"] > 0
    with _status_lock:
        fails = 0 if ok else LAST_RUN.get("consecutive_failures", 0) + 1
    _record(
        finished_at=datetime.now().isoformat(), ok=ok,
        halls=summary["halls"], discovered=discovered,
        screenings=summary["screenings"], errors=errors,
        replaced=summary["replaced"], reason=summary["reason"],
        consecutive_failures=fails,
    )
    log.info("scrape summary: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_scrape())
