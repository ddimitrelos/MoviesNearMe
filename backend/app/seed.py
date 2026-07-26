"""
Seed the database with real Athens cinemas and a few days of sample
screenings, so the app is fully demoable before the live scraper is tuned.

Run:  python -m app.seed
Coordinates are approximate but real, so the map pins land in the right place.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, date

from .database import SessionLocal, engine, Base
from . import models

CINEMAS = [
    dict(slug="aello-cinemax", name="Αελλώ Cinemax", address="Πατησίων 140, Αθήνα",
         phone="2108259974", lat=37.999418, lng=23.733404, region="Κέντρο"),
    dict(slug="danaos", name="Δαναός", address="Λεωφ. Κηφισίας 109, Αμπελόκηποι",
         phone="2106922655", lat=37.9871, lng=23.7746, region="Αμπελόκηποι"),
    dict(slug="odeon-opera", name="Odeon Όπερα", address="Ακαδημίας 57, Αθήνα",
         phone="2103622683", lat=37.9836, lng=23.7345, region="Κέντρο"),
    dict(slug="astor", name="Άστορ", address="Σταδίου 28, Αθήνα",
         phone="2103211950", lat=37.9793, lng=23.7327, region="Κέντρο"),
    dict(slug="ideal", name="Ideal", address="Πανεπιστημίου 46, Αθήνα",
         phone="2103826720", lat=37.9819, lng=23.7327, region="Κέντρο"),
    dict(slug="trianon", name="Τριανόν", address="Κοδριγκτώνος 21, Αθήνα",
         phone="2108222702", lat=37.9967, lng=23.7330, region="Κέντρο"),
    dict(slug="village-mall", name="Village Cinemas The Mall Athens",
         address="Α. Παπανδρέου 35, Μαρούσι",
         phone="2118009000", lat=38.0448, lng=23.7906, region="Μαρούσι"),
    dict(slug="village-metro-mall", name="Village Cinemas Athens Metro Mall",
         address="Λεωφ. Βουλιαγμένης 276, Άγ. Δημήτριος",
         phone="2118009000", lat=37.9375, lng=23.7440, region="Άγ. Δημήτριος"),
    dict(slug="cine-paris", name="Cine Paris", address="Κυδαθηναίων 22, Πλάκα",
         phone="2103222071", lat=37.9725, lng=23.7300, region="Πλάκα"),
    dict(slug="cinobo-opera", name="Cinobo Όπερα", address="Ακαδημίας 57, Αθήνα",
         phone="2103622683", lat=37.9838, lng=23.7347, region="Κέντρο"),
]

MOVIES = [
    dict(slug="dune-part-three", title="Dune: Part Three",
         original_title="Dune: Part Three", genre="Sci-Fi", duration_min=165),
    dict(slug="the-odyssey", title="The Odyssey",
         original_title="The Odyssey", genre="Adventure", duration_min=150),
    dict(slug="poor-things-2", title="Poor Things II",
         original_title="Poor Things II", genre="Drama", duration_min=140),
    dict(slug="a-quiet-place-birth", title="A Quiet Place: Birth",
         original_title="A Quiet Place: Birth", genre="Horror", duration_min=100),
    dict(slug="past-lives-forward", title="Past Lives Forward",
         original_title="Past Lives Forward", genre="Romance", duration_min=115),
    dict(slug="mikri-anglia", title="Μικρή Αγγλία (επανέκδοση)",
         original_title="Little England", genre="Drama", duration_min=118),
    dict(slug="the-batman-2", title="The Batman Part II",
         original_title="The Batman Part II", genre="Action", duration_min=155),
    dict(slug="inside-out-3", title="Inside Out 3",
         original_title="Inside Out 3", genre="Animation", duration_min=100),
]

SHOWTIMES = ["17.30", "18.00", "19.45", "20.15", "22.00", "22.30"]


def _dt(d: date, hhmm: str) -> datetime:
    h, m = hhmm.split(".")
    return datetime(d.year, d.month, d.day, int(h), int(m))


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # wipe existing rows for a clean, repeatable seed
        db.query(models.Screening).delete()
        db.query(models.Movie).delete()
        db.query(models.Cinema).delete()
        db.commit()

        cinemas = []
        for c in CINEMAS:
            obj = models.Cinema(**c, source_url="seed")
            db.add(obj)
            cinemas.append(obj)

        movies = []
        for m in MOVIES:
            obj = models.Movie(**m, source_url="seed")
            db.add(obj)
            movies.append(obj)
        db.flush()

        rng = random.Random(42)
        today = date.today()
        count = 0
        # next 4 days
        for day_offset in range(4):
            d = today + timedelta(days=day_offset)
            for cinema in cinemas:
                # each cinema shows 2-4 of the movies on a given day
                shown = rng.sample(movies, rng.randint(2, 4))
                for idx, movie in enumerate(shown):
                    times = rng.sample(SHOWTIMES, rng.randint(1, 3))
                    for t in times:
                        db.add(
                            models.Screening(
                                cinema_id=cinema.id,
                                movie_id=movie.id,
                                start_time=_dt(d, t),
                                hall=f"Αίθουσα {idx + 1}",
                            )
                        )
                        count += 1
        db.commit()
        print(f"Seeded {len(cinemas)} cinemas, {len(movies)} movies, "
              f"{count} screenings.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
