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
import androidx.compose.material.icons.filled.NearMe
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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

    // Swipe down to reload. Because the map consumes drag gestures for panning,
    // the gesture is most reliable over the top filter bar; the refresh button
    // works everywhere.
    PullToRefreshBox(
        isRefreshing = state.loading,
        onRefresh = { vm.refresh() },
        modifier = Modifier.fillMaxSize(),
    ) {
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
                summerOnly = state.summerOnly,
                nearMe = state.nearMe,
                resultCount = state.cinemas.size,
                onMovieSelected = vm::selectMovie,
                onTimeWindowSelected = vm::selectTimeWindow,
                onToggleSummer = vm::toggleSummerOnly,
                onToggleNearMe = vm::toggleNearMe,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .statusBarsPadding()
                    .padding(12.dp),
            )

            FloatingActionButton(
                onClick = { vm.refresh() },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .navigationBarsPadding()
                    .padding(16.dp),
            ) {
                if (state.loading) {
                    CircularProgressIndicator(
                        Modifier.size(24.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                } else {
                    Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                }
            }

            state.loadingMessage?.let { msg ->
                Surface(
                    color = MaterialTheme.colorScheme.tertiaryContainer,
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(16.dp),
                    shape = RoundedCornerShape(20.dp),
                    shadowElevation = 6.dp,
                ) {
                    Row(
                        Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        CircularProgressIndicator(
                            Modifier.size(20.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onTertiaryContainer,
                        )
                        Text(msg, color = MaterialTheme.colorScheme.onTertiaryContainer)
                    }
                }
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
    summerOnly: Boolean,
    nearMe: Boolean,
    resultCount: Int,
    onMovieSelected: (Movie?) -> Unit,
    onTimeWindowSelected: (TimeWindow) -> Unit,
    onToggleSummer: () -> Unit,
    onToggleNearMe: () -> Unit,
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
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = summerOnly,
                    onClick = onToggleSummer,
                    label = { Text("Summer") },
                    leadingIcon = {
                        Icon(Icons.Filled.WbSunny, contentDescription = null,
                            modifier = Modifier.size(18.dp))
                    },
                )
                FilterChip(
                    selected = nearMe,
                    onClick = onToggleNearMe,
                    label = { Text("Near me") },
                    leadingIcon = {
                        Icon(Icons.Filled.NearMe, contentDescription = null,
                            modifier = Modifier.size(18.dp))
                    },
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = "$resultCount cinemas" +
                    (if (summerOnly) " · summer" else "") +
                    (if (nearMe) " · near me" else "") +
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(cinema.name, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        if (cinema.isSummer) {
                            Spacer(Modifier.width(8.dp))
                            Surface(
                                color = Color(0xFF00BFA5),
                                shape = RoundedCornerShape(6.dp),
                            ) {
                                Row(
                                    Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                                ) {
                                    Icon(
                                        Icons.Filled.WbSunny, contentDescription = null,
                                        tint = Color.White,
                                        modifier = Modifier.size(14.dp),
                                    )
                                    Text(
                                        "Open-air",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        color = Color.White,
                                    )
                                }
                            }
                        }
                    }
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
                    Column(
                        Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            formatShowtime(s.startTime),
                            fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                        s.hall?.let { hall ->
                            Text(
                                hall,
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.onSecondaryContainer
                                    .copy(alpha = 0.7f),
                            )
                        }
                    }
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
