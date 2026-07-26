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
  Ships with a **seed dataset of real Athens cinemas** so the app works
  immediately.
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

# Load the sample Athens cinemas + a few days of showtimes:
python -m app.seed

# Start the API on 0.0.0.0:8000 so the emulator/device can reach it:
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
| `POST /admin/seed` | Reload the sample data |
| `POST /admin/scrape?limit=` | Trigger a live scrape of athinorama (background) |

### Live data from athinorama.gr

The seed data is there so you can develop without hammering the site. To pull
real listings:

```bash
# Scrape everything (be polite — there is a 1s delay per hall):
python -m app.scraper
# or a quick sample of 5 halls:
curl -X POST "http://localhost:8000/admin/scrape?limit=5"
```

The scraper (`app/scraper.py`) parses the **schema.org JSON-LD** that athinorama
embeds on every hall page — a `MovieTheater` object (name, address, geo, phone)
plus one `ScreeningEvent` per showing (ISO `startDate`, and a nested `Movie`
with Greek `name` + English `alternateName`). This is far more robust than
scraping markup. A full run currently yields ~111 cinemas and ~3,000 screenings.
Parsing is best-effort: a malformed JSON-LD block is skipped, never fatal.

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
│   │   ├── seed.py        # real Athens cinemas + sample showtimes
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
