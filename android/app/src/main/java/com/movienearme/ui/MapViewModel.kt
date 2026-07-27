package com.movienearme.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.movienearme.data.AppSettings
import com.movienearme.data.Poi
import com.movienearme.data.SettingsStore
import com.movienearme.data.api.ApiClient
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.location.LatLng
import java.util.UUID
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Which time window is selected. Hours for the two quick filters come from settings. */
enum class TimeFilter { ANY, QUICK_A, QUICK_B, TODAY }

fun TimeFilter.hours(settings: AppSettings): Double? = when (this) {
    TimeFilter.ANY -> null
    TimeFilter.TODAY -> 24.0
    TimeFilter.QUICK_A -> settings.filterAHours.toDouble()
    TimeFilter.QUICK_B -> settings.filterBHours.toDouble()
}

data class MapUiState(
    val loading: Boolean = false,
    val waking: Boolean = false,
    val error: Boolean = false,
    val movies: List<Movie> = emptyList(),
    val cinemas: List<Cinema> = emptyList(),
    val selectedMovie: Movie? = null,
    val timeFilter: TimeFilter = TimeFilter.TODAY,
    val summerOnly: Boolean = false,
    val nearMe: Boolean = false,
    val userLocation: LatLng? = null,
    val selectedCinema: Cinema? = null,
    val settings: AppSettings = AppSettings(),
    val showSettings: Boolean = false,
    val showPoiPicker: Boolean = false,
)

class MapViewModel(app: Application) : AndroidViewModel(app) {

    private val api = ApiClient.service
    private val store = SettingsStore(app)

    private val _state = MutableStateFlow(MapUiState(settings = store.load()))
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    // The in-flight cinemas request, cancelled when a newer one starts so a slow
    // stale response can't overwrite the latest filters.
    private var refreshJob: Job? = null

    fun setUserLocation(loc: LatLng) {
        _state.value = _state.value.copy(userLocation = loc)
        refresh()
    }

    fun loadMovies() {
        viewModelScope.launch {
            // Retry through a cold start so the dropdown gets the real list, not
            // the seed fallback that a sleeping server briefly returns.
            repeat(5) { attempt ->
                try {
                    val movies = api.getMovies()
                    _state.value = _state.value.copy(movies = movies)
                    return@launch
                } catch (e: Exception) {
                    if (attempt < 4) delay(6000L)
                }
            }
        }
    }

    fun selectMovie(movie: Movie?) {
        _state.value = _state.value.copy(selectedMovie = movie)
        refresh()
    }

    fun selectTimeFilter(filter: TimeFilter) {
        _state.value = _state.value.copy(timeFilter = filter)
        refresh()
    }

    fun toggleSummerOnly() {
        _state.value = _state.value.copy(summerOnly = !_state.value.summerOnly)
        refresh()
    }

    fun toggleNearMe() {
        _state.value = _state.value.copy(nearMe = !_state.value.nearMe)
        refresh()
    }

    fun selectCinema(cinema: Cinema?) {
        _state.value = _state.value.copy(selectedCinema = cinema)
    }

    fun openSettings(open: Boolean) {
        _state.value = _state.value.copy(showSettings = open)
    }

    fun openPoiPicker(open: Boolean) {
        _state.value = _state.value.copy(showPoiPicker = open)
    }

    fun addPoi(label: String, lat: Double, lng: Double) {
        val poi = Poi(id = UUID.randomUUID().toString(), label = label.trim(), lat = lat, lng = lng)
        val s = _state.value.settings
        updateSettings(s.copy(pois = s.pois + poi))
    }

    fun removePoi(id: String) {
        val s = _state.value.settings
        val newOrigin = if (s.nearMeOriginId == id) null else s.nearMeOriginId
        updateSettings(s.copy(pois = s.pois.filterNot { it.id == id }, nearMeOriginId = newOrigin))
    }

    fun setNearMeOrigin(id: String?) {
        // Choosing a POI as the origin means "show cinemas near here", so turn
        // the Near me filter on automatically.
        if (id != null) _state.value = _state.value.copy(nearMe = true)
        updateSettings(_state.value.settings.copy(nearMeOriginId = id))
    }

    fun updateSettings(settings: AppSettings) {
        store.save(settings)
        val prev = _state.value
        // If the selected quick filter got disabled, fall back to Today.
        val newFilter = when {
            prev.timeFilter == TimeFilter.QUICK_A && !settings.filterAEnabled -> TimeFilter.TODAY
            prev.timeFilter == TimeFilter.QUICK_B && !settings.filterBEnabled -> TimeFilter.TODAY
            else -> prev.timeFilter
        }
        _state.value = prev.copy(settings = settings, timeFilter = newFilter)
        refresh()
    }

    fun refresh() {
        val s = _state.value
        // Also refresh the movie list, so a manual refresh heals a dropdown that
        // was loaded during a cold start (seed data).
        loadMovies()
        // Cancel any in-flight request so its (stale) result can't win a race.
        refreshJob?.cancel()
        refreshJob = viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = false)
            // The cloud backend may be asleep (free tier) and take up to ~50s to
            // wake. Retry a few times with backoff, showing a friendly message,
            // before giving up.
            // "Near me" measures from the chosen POI origin if one is selected,
            // otherwise from the user's GPS location.
            val originPoi = s.settings.nearMeOriginId
                ?.let { id -> s.settings.pois.find { it.id == id } }
            val originLat = if (s.nearMe && originPoi != null) originPoi.lat else s.userLocation?.lat
            val originLng = if (s.nearMe && originPoi != null) originPoi.lng else s.userLocation?.lng

            val attempts = 5
            for (attempt in 0 until attempts) {
                try {
                    val cinemas = api.getCinemas(
                        movieId = s.selectedMovie?.id,
                        withinHours = s.timeFilter.hours(s.settings),
                        lat = originLat,
                        lng = originLng,
                        summerOnly = s.summerOnly,
                        maxKm = if (s.nearMe) s.settings.nearMeKm.toDouble() else null,
                    )
                    _state.value = _state.value.copy(
                        loading = false, waking = false, error = false, cinemas = cinemas,
                    )
                    return@launch
                } catch (e: Exception) {
                    if (attempt < attempts - 1) {
                        _state.value = _state.value.copy(waking = true)
                        delay(6000L)
                    }
                }
            }
            _state.value = _state.value.copy(loading = false, waking = false, error = true)
        }
    }
}
