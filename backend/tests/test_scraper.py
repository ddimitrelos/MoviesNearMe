"""Unit tests for the JSON-LD parsing (no network)."""

from unittest.mock import patch

from app import scraper
from app.scraper import parse_hall

# Minimal hall page: one MovieTheater + one ScreeningEvent carrying a poster
# image and a nested Movie with an athinorama url.
SAMPLE_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"MovieTheater","name":"Test Cinema",
 "geo":{"@type":"GeoCoordinates","latitude":"37.98","longitude":"23.73"},
 "telephone":"2100000000",
 "address":{"@type":"PostalAddress","streetAddress":"Test St 1","addressLocality":"ATHENS"}}
</script>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"ScreeningEvent","name":"The Odyssey",
 "startDate":"2026-07-27T20:00:00+03:00","endDate":"2026-07-27T22:52:00+03:00",
 "image":"https://www.athinorama.gr/Content/ImagesDatabase/p/600x900/x.jpg?quality=81",
 "workPresented":{"@context":"http://schema.org","@type":"Movie","name":"Οδύσσεια",
   "alternateName":"The Odyssey","url":"https://www.athinorama.gr/cinema/movie/odusseia-10091064/"}}
</script>
</head><body></body></html>
"""


def test_parse_hall_extracts_theater_and_geo():
    hall = parse_hall(SAMPLE_HTML, "https://www.athinorama.gr/cinema/halls/test-1/")
    assert hall is not None
    assert hall["name"] == "Test Cinema"
    assert abs(hall["lat"] - 37.98) < 1e-6
    assert abs(hall["lng"] - 23.73) < 1e-6
    assert len(hall["screenings"]) == 1


def test_parse_hall_captures_poster_and_movie_url():
    hall = parse_hall(SAMPLE_HTML, "https://www.athinorama.gr/cinema/halls/test-1/")
    s = hall["screenings"][0]
    assert s["movie_poster"] == "https://www.athinorama.gr/Content/ImagesDatabase/p/600x900/x.jpg?quality=81"
    assert s["movie_url"] == "https://www.athinorama.gr/cinema/movie/odusseia-10091064/"
    assert s["movie_slug"] == "odusseia-10091064"
    assert s["movie_title"] == "Οδύσσεια"
    assert s["movie_original"] == "The Odyssey"
    # duration derived from start/end (172 min)
    assert s["movie_duration"] == 172


# --- discover_hall_urls: a landing page can come back transiently empty -----
# Context: run #68 of refresh-snapshot found only 50/~109 halls with zero
# per-hall errors - the shortfall was upstream, in discovery, not in parsing.
# A landing page that fetch() got a 200 for but held no hall links (a
# transient partial/challenge response) is now retried once before being
# treated as genuinely empty.

GUIDE_HTML = '<a href="/cinema/halls/guide-only-1/">x</a>'


def test_landing_page_with_no_links_is_retried_once():
    # First landing page: empty, then recovers on retry. Second landing page:
    # fine on the first try. Calls per page are counted separately.
    calls: dict[str, int] = {}

    def fake_fetch(_client, page):
        calls[page] = calls.get(page, 0) + 1
        if page == scraper.LANDING_PAGES[0]:
            return GUIDE_HTML if calls[page] > 1 else "<html>no links here</html>"
        return "<html>no links on this page either</html>"

    with (
        patch.object(scraper, "fetch", side_effect=fake_fetch),
        patch.object(scraper.time, "sleep"),
    ):
        urls = scraper.discover_hall_urls(client=None)

    assert urls == ["https://www.athinorama.gr/cinema/halls/guide-only-1/"]
    assert calls[scraper.LANDING_PAGES[0]] == 2, "must retry after an empty result"


def test_landing_page_still_empty_after_retry_yields_nothing_for_that_page():
    with (
        patch.object(scraper, "fetch", return_value=""),
        patch.object(scraper.time, "sleep"),
    ):
        urls = scraper.discover_hall_urls(client=None)

    assert urls == []
