package com.movienearme.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.movienearme.data.api.ApiClient
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.location.LatLng
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Time-window options for the showtime filter. */
enum class TimeWindow(val label: String, val hours: Double?) {
    ANY("Any time", null),
    NEXT_3H("Next 3h", 3.0),
    NEXT_6H("Next 6h", 6.0),
    TODAY("Today", 24.0),
}

data class MapUiState(
    val loading: Boolean = false,
    val loadingMessage: String? = null,
    val error: String? = null,
    val movies: List<Movie> = emptyList(),
    val cinemas: List<Cinema> = emptyList(),
    val selectedMovie: Movie? = null,
    val timeWindow: TimeWindow = TimeWindow.TODAY,
    val summerOnly: Boolean = false,
    val nearMe: Boolean = false,
    val userLocation: LatLng? = null,
    val selectedCinema: Cinema? = null,
)

// Radius (km) used by the "Near me" filter.
private const val NEAR_ME_KM = 5.0

class MapViewModel : ViewModel() {

    private val api = ApiClient.service

    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

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

    fun selectTimeWindow(window: TimeWindow) {
        _state.value = _state.value.copy(timeWindow = window)
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

    fun refresh() {
        val s = _state.value
        // Also refresh the movie list, so a manual refresh heals a dropdown that
        // was loaded during a cold start (seed data).
        loadMovies()
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            // The cloud backend may be asleep (free tier) and take up to ~50s to
            // wake. Retry a few times with backoff, showing a friendly message,
            // before giving up.
            var lastError: Exception? = null
            val attempts = 5
            for (attempt in 0 until attempts) {
                try {
                    val cinemas = api.getCinemas(
                        movieId = s.selectedMovie?.id,
                        withinHours = s.timeWindow.hours,
                        lat = s.userLocation?.lat,
                        lng = s.userLocation?.lng,
                        summerOnly = s.summerOnly,
                        maxKm = if (s.nearMe) NEAR_ME_KM else null,
                    )
                    _state.value = _state.value.copy(
                        loading = false, loadingMessage = null,
                        error = null, cinemas = cinemas,
                    )
                    return@launch
                } catch (e: Exception) {
                    lastError = e
                    if (attempt < attempts - 1) {
                        _state.value = _state.value.copy(
                            loadingMessage = "Waking up the server…",
                        )
                        delay(6000L)
                    }
                }
            }
            _state.value = _state.value.copy(
                loading = false, loadingMessage = null, error = friendly(lastError),
            )
        }
    }

    private fun friendly(e: Exception?): String =
        "Can't reach the server. Check your connection and tap refresh. " +
            "(${e?.message ?: "unknown error"})"
}
