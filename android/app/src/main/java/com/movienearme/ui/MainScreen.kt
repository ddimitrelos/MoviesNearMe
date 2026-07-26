package com.movienearme.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.data.model.ScreeningBrief
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: MapViewModel) {
    val state by vm.state.collectAsState()

    Box(Modifier.fillMaxSize()) {
        OsmMap(
            cinemas = state.cinemas,
            userLocation = state.userLocation,
            selectedCinemaId = state.selectedCinema?.id,
            onCinemaClick = { vm.selectCinema(it) },
            modifier = Modifier.fillMaxSize(),
        )

        FilterBar(
            movies = state.movies,
            selectedMovie = state.selectedMovie,
            timeWindow = state.timeWindow,
            resultCount = state.cinemas.size,
            onMovieSelected = vm::selectMovie,
            onTimeWindowSelected = vm::selectTimeWindow,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .statusBarsPadding()
                .padding(12.dp),
        )

        if (state.loading) {
            LinearProgressIndicator(
                Modifier
                    .align(Alignment.TopCenter)
                    .fillMaxWidth()
                    .statusBarsPadding()
            )
        }

        state.error?.let { msg ->
            Surface(
                color = MaterialTheme.colorScheme.errorContainer,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp),
                shape = RoundedCornerShape(12.dp),
            ) {
                Text(
                    msg,
                    Modifier.padding(16.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        }
    }

    state.selectedCinema?.let { cinema ->
        CinemaSheet(cinema = cinema, onDismiss = { vm.selectCinema(null) })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterBar(
    movies: List<Movie>,
    selectedMovie: Movie?,
    timeWindow: TimeWindow,
    resultCount: Int,
    onMovieSelected: (Movie?) -> Unit,
    onTimeWindowSelected: (TimeWindow) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        tonalElevation = 4.dp,
        shadowElevation = 8.dp,
    ) {
        Column(Modifier.padding(12.dp)) {
            MovieDropdown(movies, selectedMovie, onMovieSelected)
            Spacer(Modifier.height(8.dp))
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                TimeWindow.entries.forEach { w ->
                    FilterChip(
                        selected = timeWindow == w,
                        onClick = { onTimeWindowSelected(w) },
                        label = { Text(w.label) },
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = "$resultCount cinemas" +
                    (selectedMovie?.let { " · ${it.title}" } ?: ""),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MovieDropdown(
    movies: List<Movie>,
    selected: Movie?,
    onSelected: (Movie?) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it },
    ) {
        OutlinedTextField(
            value = selected?.title ?: "All movies",
            onValueChange = {},
            readOnly = true,
            leadingIcon = { Icon(Icons.Filled.Movie, contentDescription = null) },
            trailingIcon = { Icon(Icons.Filled.ArrowDropDown, contentDescription = null) },
            label = { Text("Movie") },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text("All movies") },
                onClick = { onSelected(null); expanded = false },
            )
            movies.forEach { movie ->
                DropdownMenuItem(
                    text = { Text(movie.title) },
                    onClick = { onSelected(movie); expanded = false },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CinemaSheet(cinema: Cinema, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.LocationOn, contentDescription = null, tint = Color(0xFFE50914))
                Spacer(Modifier.width(8.dp))
                Column {
                    Text(cinema.name, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    val sub = buildString {
                        cinema.address?.let { append(it) }
                        cinema.distanceKm?.let { append("  ·  %.1f km away".format(it)) }
                    }
                    if (sub.isNotBlank()) {
                        Text(sub, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))

            if (cinema.screenings.isEmpty()) {
                Text("No screenings match your filters.")
            } else {
                groupByMovie(cinema.screenings).forEach { (movie, showtimes) ->
                    MovieShowtimes(movie.title, movie.genre, showtimes)
                    Spacer(Modifier.height(14.dp))
                }
            }
        }
    }
}

@Composable
private fun MovieShowtimes(title: String, genre: String?, screenings: List<ScreeningBrief>) {
    Column {
        Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        genre?.let {
            Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(6.dp))
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            screenings.forEach { s ->
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.secondaryContainer,
                ) {
                    Text(
                        formatShowtime(s.startTime),
                        Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                    )
                }
            }
        }
    }
}

// --- helpers ---------------------------------------------------------------

private fun groupByMovie(screenings: List<ScreeningBrief>): List<Pair<Movie, List<ScreeningBrief>>> =
    screenings
        .groupBy { it.movie.id }
        .map { (_, list) -> list.first().movie to list.sortedBy { it.startTime } }
        .sortedBy { it.first.title }

private val outFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

private fun formatShowtime(iso: String): String =
    try {
        val dt = LocalDateTime.parse(iso)
        val today = LocalDateTime.now().toLocalDate()
        val day = if (dt.toLocalDate() == today) {
            ""
        } else {
            dt.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault()) + " "
        }
        day + dt.format(outFmt)
    } catch (e: Exception) {
        iso
    }
