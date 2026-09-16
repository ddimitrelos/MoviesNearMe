# MovieNearMe

Find what movies are playing near you in Athens — on **one map screen**. Tap a
cinema pin to see its showtimes, pick a movie to see every cinema showing it, or
filter to screenings in the next few hours. Built because doing this on
athinorama.gr is painful.

```
┌─────────────────────────┐        ┌──────────────────────────┐
│   Android app (Kotlin)  │  HTTP  │   Backend (FastAPI)      │
│   Jetpack Compose        │ ─────► │   scraper + SQLite       │
│   OpenStreetMap map      │ ◄───── │   REST API               │
│   GPS location           │  JSON  │   athinorama.gr scraper  │
└─────────────────────────┘        └──────────────────────────┘
```

- **`backend/`** — Python + FastAPI. Scrapes athinorama cinema-hall pages
  (name, address, coordinates, showtimes) into SQLite and serves a REST API.
  Ships with a **committed snapshot of real listings** (refreshed daily by CI)
  so even a freshly restarted instance serves real cinemas immediately — see
  [Data freshness](#data-freshness).
- **`android/`** — Native Kotlin app (Jetpack Compose). Map with cinema pins,
  GPS auto-location (defaults to Athens), filter by movie, filter by time
  window, and a bottom sheet of showtimes per cinema. Uses **OpenStreetMap**
  (osmdroid) so **no Google Maps API key is required**.

---

## 1. Run the backend

Requirements: Python 3.10+ (tested on 3.14).

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# Git Bash:            source .venv/Scripts/activate
pip install -r requirements.txt

# Start the API on 0.0.0.0:8000 so the emulator/device can reach it.
# On first run it loads the committed snapshot of real listings, then scrapes
# athinorama in the background — no manual data step needed.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Check it works: open <http://localhost:8000/health> — you should see cinema /
movie / screening counts. Interactive API docs are at
<http://localhost:8000/docs>.

### Endpoints the app uses

| Endpoint | What it returns |
|---|---|
| `GET /movies?query=` | Movies currently showing (optional title search) |
| `GET /cinemas?movie_id=&within_hours=&lat=&lng=` | Cinemas with the screenings matching the filters; sorted by distance and given a `distance_km` when `lat`/`lng` are supplied |
| `GET /cinemas/{id}/screenings` | Full upcoming schedule for one cinema |
| `GET /health` | Counts, `status` (`ok`/`degraded`), last-scrape result, snapshot age, DB location |
| `POST /admin/scrape?limit=&sync=` | Trigger a live scrape (background, or `sync=true` to wait for the summary) |
| `POST /admin/seed` | Invented sample data — **local only**, needs `ALLOW_SEED=1` |

### Live data from athinorama.gr

```bash
# Scrape everything into the local DB (~30s; halls are fetched concurrently):
python -m app.scraper
# Rewrite the committed cold-start snapshot from a live scrape:
python -m app.snapshot
# or a quick sample of 5 halls:
curl -X POST "http://localhost:8000/admin/scrape?limit=5"
```

The scraper (`app/scraper.py`) parses the **schema.org JSON-LD** that athinorama
embeds on every hall page — a `MovieTheater` object (name, address, geo, phone)
plus one `ScreeningEvent` per showing (ISO `startDate`, and a nested `Movie`
with Greek `name` + English `alternateName`). This is far more robust than
scraping markup. A full run currently yields ~111 cinemas and ~3,000 screenings.
Parsing is best-effort: a malformed JSON-LD block is skipped, never fatal.

### Data freshness

The app once showed only **11 cinemas** after a restart: Render's free tier has
no persistent disk, so every restart began with an empty database, which the
old startup code filled with `seed.py` — eleven invented cinemas — and served
as if real while the (then ~2 minute, sequential) scrape ran. If that scrape
failed, the next attempt was 24 hours away.

Four rules now keep that from recurring:

1. **Never serve invented data.** Startup loads
   `app/data/cinemas_snapshot.json.gz` — the last real scrape, refreshed daily
   by `.github/workflows/snapshot.yml`. `seed.py` is local-only (`ALLOW_SEED=1`).
   A snapshot whose showtimes have all passed is skipped rather than loaded.
2. **A bad scrape can't shrink the dataset.** `scraper.replace_decision` only
   allows a wipe-and-replace when the run looks complete (≥30 halls, ≥60% of
   those discovered, ≥70% of what's already stored). Anything less merges, and
   past screenings are pruned so nothing stale accumulates. The write happens
   in one transaction, so clients never see a half-populated database.
3. **Self-healing refresh.** A supervisor thread re-scrapes whenever fewer than
   30 cinemas carry listings for today, the data is over 4 hours old, or the
   last run failed (with backoff) — instead of sleeping for a day. "For today"
   rather than "from now" on purpose: athinorama publishes one week at a time
   (Thu–Wed), so on the last night of a week everything it listed is already
   past, and measuring from the clock would read that as a failure and re-scrape
   every five minutes for hours.
4. **Failure is visible.** `/health` returns `status: "degraded"` whenever the
   map would look thin, and reports the last scrape, snapshot age, and whether
   the database is on a persistent disk. The keep-alive workflow fails on a
   sustained `degraded`, so it surfaces instead of going unnoticed.

Halls are fetched concurrently (6 workers), cutting a full refresh to ~30s.

---

## 2. Build & run the Android app

Open **`android/`** in **Android Studio** (Ladybug / 2024.2 or newer) and let it
sync, then Run ▶ on an emulator or device. That's the whole flow — Studio brings
its own Gradle and Android SDK.

Command line alternative:

```bash
cd android
./gradlew :app:assembleDebug        # Windows: .\gradlew.bat :app:assembleDebug
# APK: android/app/build/outputs/apk/debug/app-debug.apk
```

### Pointing the app at your backend

The base URL is a `buildConfigField` in `android/app/build.gradle.kts`:

| Where the app runs | `API_BASE_URL` |
|---|---|
| **Android emulator** (default) | `http://10.0.2.2:8000/` — `10.0.2.2` is the emulator's alias for your laptop's `localhost` |
| **Physical device** on the same Wi‑Fi | `http://<your-laptop-LAN-IP>:8000/` (e.g. `http://192.168.1.78:8000/`) |

After changing it, rebuild. Cleartext HTTP to these hosts is already allowed for
development (`usesCleartextTraffic="true"`).

### Using the app

1. On first launch it asks for location permission. Grant it to center on you;
   deny it and it falls back to central Athens (Syntagma).
2. The map shows red pins for cinemas that match the current filters, and a blue
   dot for you.
3. **Movie filter** (dropdown): pick a movie → only cinemas showing it remain.
4. **Time filter** (chips): Any / Next 3h / Next 6h / Today.
5. **Tap a pin** → a sheet slides up with that cinema's address, distance, and
   showtimes grouped by movie.

---

## Swapping OpenStreetMap for Google Maps (optional)

The app uses OSM so it runs with zero setup. If you'd rather use Google Maps:

1. Create a key: Google Cloud Console → enable **Maps SDK for Android** →
   Credentials → **Create API key** → restrict it to your app's package
   (`com.movienearme`) and SHA‑1.
2. Add `com.google.maps.android:maps-compose` +
   `com.google.android.gms:play-services-maps` to `app/build.gradle.kts` and
   remove the `osmdroid` dependency.
3. Put the key in `AndroidManifest.xml`:
   ```xml
   <meta-data android:name="com.google.android.geo.API_KEY"
              android:value="YOUR_KEY_HERE" />
   ```
4. Replace `ui/OsmMap.kt` with a `GoogleMap { ... }` composable — the rest of the
   app (filters, sheet, view model) is map-agnostic and stays the same.

---

## Project layout

```
MovieNearMe/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app + endpoints
│   │   ├── models.py      # SQLAlchemy: Cinema, Movie, Screening
│   │   ├── schemas.py     # Pydantic response models
│   │   ├── scraper.py     # athinorama.gr scraper (+ Greek date parsing)
│   │   ├── snapshot.py    # cold-start dataset: read/write/refresh
│   │   ├── data/          # cinemas_snapshot.json.gz (committed, daily refresh)
│   │   ├── seed.py        # invented sample data — local development only
│   │   └── database.py
│   └── requirements.txt
└── android/
    ├── app/src/main/
    │   ├── java/com/movienearme/
    │   │   ├── MainActivity.kt          # entry, location permission
    │   │   ├── data/model/Models.kt     # API models (Moshi)
    │   │   ├── data/api/                 # Retrofit service + client
    │   │   ├── location/LocationHelper.kt
    │   │   └── ui/
    │   │       ├── MapViewModel.kt       # state + API calls
    │   │       ├── MainScreen.kt         # filters + cinema sheet
    │   │       └── OsmMap.kt             # OpenStreetMap view
    │   └── AndroidManifest.xml
    └── build.gradle.kts
```
