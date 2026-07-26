package com.movienearme.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.movienearme.data.api.ApiClient
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.location.LatLng
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
    val error: String? = null,
    val movies: List<Movie> = emptyList(),
    val cinemas: List<Cinema> = emptyList(),
    val selectedMovie: Movie? = null,
    val timeWindow: TimeWindow = TimeWindow.ANY,
    val userLocation: LatLng? = null,
    val selectedCinema: Cinema? = null,
)

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
            try {
                val movies = api.getMovies()
                _state.value = _state.value.copy(movies = movies)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = friendly(e))
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

    fun selectCinema(cinema: Cinema?) {
        _state.value = _state.value.copy(selectedCinema = cinema)
    }

    fun refresh() {
        val s = _state.value
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val cinemas = api.getCinemas(
                    movieId = s.selectedMovie?.id,
                    withinHours = s.timeWindow.hours,
                    lat = s.userLocation?.lat,
                    lng = s.userLocation?.lng,
                )
                _state.value = _state.value.copy(loading = false, cinemas = cinemas)
            } catch (e: Exception) {
                _state.value = _state.value.copy(loading = false, error = friendly(e))
            }
        }
    }

    private fun friendly(e: Exception): String =
        "Can't reach the server. Is the backend running? (${e.message})"
}
